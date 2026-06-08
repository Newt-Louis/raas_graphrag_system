from __future__ import annotations

import inspect
import math
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from app.ai_gateway.base_rotator import RotationResult
from app.api.v1.chat import _chat_sse_events
from app.api.v1.ingest import ingest_document
from app.graphrag.graph_database import (
    GraphChunkContext,
    GraphContextResult,
    GraphEntityContext,
    GraphTraversalResult,
)
from app.graphrag.vector_database import (
    InMemoryPrecomputedVectorStore,
    PrecomputedVectorRecord,
)
from app.models.documents import Document
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.core.config import settings
from app.services.chat.completion import (
    ChatCompletionService,
    _ContextBlock,
    _compact_context_blocks,
)
from app.services.chat.behavior import DEFAULT_CHAT_BEHAVIOR
from app.services.chat.policy import chat_response_messages, parse_chat_response


TEST_REFUSAL = "Fixed refusal."
TEST_BEHAVIOR = replace(DEFAULT_CHAT_BEHAVIOR, refusal_responses=(TEST_REFUSAL,))


class FakeSession:
    def get(self, model, record_id):
        return None


class FakeScalarResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeProfileSession(FakeSession):
    def __init__(self, *retrieval_top_k_values) -> None:
        self.retrieval_top_k_values = retrieval_top_k_values

    def scalars(self, statement):
        return FakeScalarResult(
            [
                SimpleNamespace(retrieval_top_k=retrieval_top_k)
                for retrieval_top_k in self.retrieval_top_k_values
            ]
        )


class FakeDocumentSession(FakeSession):
    def __init__(self, documents) -> None:
        self.documents = documents

    def scalars(self, statement):
        if "embedding_model_profiles" in str(statement):
            return FakeScalarResult([])
        return FakeScalarResult(self.documents)


class FakeEmbeddingGateway:
    async def embed(self, texts, **kwargs):
        return RotationResult(
            success=True,
            data=[[1.0, 0.0, 0.0]],
            profile_id="embedding-profile",
            used_model="gemini-embedding-2",
        )


class FakeLLMGateway:
    def __init__(self, *outputs) -> None:
        self.calls = []
        self.outputs = list(outputs or [_grounded_answer()])

    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return RotationResult(
            success=True,
            data=self.outputs.pop(0),
            profile_id="llm-profile",
            used_model="gemini-2.5-flash",
            usage={"total_tokens": 42},
        )


class FakeGraphStore:
    def semantic_context_for_chunks(self, *, scope, chunk_ids, hops):
        return GraphTraversalResult(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
            entities=[
                GraphEntityContext(
                    entity_id="entity-lancedb",
                    entity_type="Technology",
                    name="LanceDB",
                )
            ],
            chunk_ids=list(chunk_ids),
        )

    def chunk_context(self, *, scope, chunk_ids):
        return GraphContextResult(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
            chunks=[
                GraphChunkContext(
                    document_id="policy",
                    chunk_id="recommendation-system",
                    text="The recommendation system uses LanceDB for vector retrieval.",
                    chunk_index=0,
                )
            ],
        )


class ParentChildGraphStore:
    def semantic_context_for_chunks(self, *, scope, chunk_ids, hops):
        return GraphTraversalResult(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
        )

    def chunk_context(self, *, scope, chunk_ids):
        contexts = {
            "recommendation-system": GraphChunkContext(
                document_id="policy",
                chunk_id="recommendation-system",
                text="LanceDB is used.",
                chunk_index=1,
                parent_chunk_id="architecture-parent",
                metadata={"chunk_role": "child"},
            ),
            "architecture-parent": GraphChunkContext(
                document_id="policy",
                chunk_id="architecture-parent",
                text="The complete architecture section explains that LanceDB is used for vector retrieval.",
                chunk_index=0,
                metadata={"chunk_role": "parent"},
            ),
        }
        return GraphContextResult(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
            chunks=[contexts[chunk_id] for chunk_id in chunk_ids if chunk_id in contexts],
        )


class ChatCompletionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_completion_uses_vector_graph_context_and_llm_synthesis(self) -> None:
        store = _vector_store()
        llm_gateway = FakeLLMGateway()
        service = ChatCompletionService(
            FakeSession(),
            vector_store=store,
            graph_store=FakeGraphStore(),
            behavior=TEST_BEHAVIOR,
        )

        with (
            patch("app.services.chat.completion.build_embedding_gateway", return_value=FakeEmbeddingGateway()),
            patch("app.services.chat.completion.build_llm_gateway", return_value=llm_gateway),
        ):
            response = await service.complete(
                ChatCompletionRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    collection_id="docs",
                    message="Which technology is used?",
                )
            )

        self.assertEqual(response.strategy, "vector_semantic_graph")
        self.assertEqual(response.response_type, "grounded_answer")
        self.assertEqual(response.citations[0].filename, "architecture.txt")
        self.assertEqual(response.usage["total_tokens"], 42)
        self.assertIn("LanceDB", llm_gateway.calls[-1]["messages"][-1]["content"])
        self.assertIn("Chỉ trả về JSON hợp lệ", llm_gateway.calls[-1]["messages"][0]["content"])

    async def test_social_message_embeds_first_then_uses_one_llm_call(self) -> None:
        llm_gateway = FakeLLMGateway(
            '{"decision":"social","answer":"Xin chào. Hôm nay tôi có thể giúp gì cho bạn?",'
            '"used_references":[],'
            '"self_check":"pass"}'
        )
        service = ChatCompletionService(
            FakeSession(),
            vector_store=InMemoryPrecomputedVectorStore(),
            graph_store=FakeGraphStore(),
            behavior=TEST_BEHAVIOR,
        )

        with (
            patch("app.services.chat.completion.build_embedding_gateway", return_value=FakeEmbeddingGateway()),
            patch("app.services.chat.completion.build_llm_gateway", return_value=llm_gateway),
        ):
            response = await service.complete(
                ChatCompletionRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    message="Xin chào",
                )
            )

        self.assertEqual(response.strategy, "embedding_first_social")
        self.assertEqual(response.response_type, "social")
        self.assertIn("Xin chào", response.answer)
        self.assertEqual(len(llm_gateway.calls), 1)

    async def test_parent_context_is_prioritized_before_matched_child_for_synthesis(self) -> None:
        llm_gateway = FakeLLMGateway()
        service = ChatCompletionService(
            FakeSession(),
            vector_store=_vector_store(),
            graph_store=ParentChildGraphStore(),
            behavior=TEST_BEHAVIOR,
        )

        with (
            patch("app.services.chat.completion.build_embedding_gateway", return_value=FakeEmbeddingGateway()),
            patch("app.services.chat.completion.build_llm_gateway", return_value=llm_gateway),
        ):
            response = await service.complete(
                ChatCompletionRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    collection_id="docs",
                    message="Which database is used?",
                )
            )

        rendered_prompt = llm_gateway.calls[-1]["messages"][-1]["content"]
        self.assertEqual(response.citations[0].chunk_id, "architecture-parent")
        self.assertLess(rendered_prompt.index("architecture-parent"), rendered_prompt.index("recommendation-system"))

    async def test_restricted_topic_is_rejected_before_any_model_call(self) -> None:
        service = ChatCompletionService(
            FakeSession(),
            vector_store=InMemoryPrecomputedVectorStore(),
            graph_store=FakeGraphStore(),
            behavior=TEST_BEHAVIOR,
        )

        with (
            patch("app.services.chat.completion.build_embedding_gateway", side_effect=AssertionError),
            patch("app.services.chat.completion.build_llm_gateway", side_effect=AssertionError),
        ):
            response = await service.complete(
                ChatCompletionRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    message="Bạn nghĩ gì về chính phủ?",
                )
            )

        self.assertEqual(response.strategy, "policy_refusal")
        self.assertEqual(response.answer, TEST_REFUSAL)

    async def test_no_retrieval_context_allows_one_llm_call_to_refuse(self) -> None:
        service = ChatCompletionService(
            FakeSession(),
            vector_store=InMemoryPrecomputedVectorStore(),
            graph_store=FakeGraphStore(),
            behavior=TEST_BEHAVIOR,
        )
        llm_gateway = FakeLLMGateway(_refusal())

        with (
            patch("app.services.chat.completion.build_embedding_gateway", return_value=FakeEmbeddingGateway()),
            patch("app.services.chat.completion.build_llm_gateway", return_value=llm_gateway),
        ):
            response = await service.complete(
                ChatCompletionRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    message="Explain backpropagation.",
                )
            )

        self.assertEqual(response.strategy, "embedding_first_no_context")
        self.assertEqual(response.response_type, "refusal")
        self.assertEqual(response.answer, TEST_REFUSAL)
        self.assertEqual(len(llm_gateway.calls), 1)

    async def test_document_inventory_question_uses_document_registry_context(self) -> None:
        document = Document(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            filename="customer-guide.pdf",
            extension=".pdf",
            byte_size=100,
            sha256="a" * 64,
            status="ready",
            chunk_count=7,
            vector_record_count=7,
            graph_record_count=14,
            metadata_json={
                "scope": {
                    "tenant_id": "tenant-a",
                    "app_id": "app-a",
                    "collection_id": "docs",
                }
            },
        )
        llm_gateway = FakeLLMGateway(
            '{"decision":"grounded_answer","answer":"Tôi đang có tài liệu customer-guide.pdf. [1]",'
            '"used_references":[1],"self_check":"pass"}'
        )
        service = ChatCompletionService(
            FakeDocumentSession([document]),
            vector_store=InMemoryPrecomputedVectorStore(),
            graph_store=FakeGraphStore(),
            behavior=TEST_BEHAVIOR,
        )

        with (
            patch("app.services.chat.completion.build_embedding_gateway", return_value=FakeEmbeddingGateway()),
            patch("app.services.chat.completion.build_llm_gateway", return_value=llm_gateway),
        ):
            response = await service.complete(
                ChatCompletionRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    collection_id="docs",
                    message="bạn đang nắm giữ thông tin tài liệu gì?",
                )
            )

        rendered_prompt = llm_gateway.calls[-1]["messages"][-1]["content"]
        self.assertEqual(response.strategy, "document_registry")
        self.assertEqual(response.response_type, "grounded_answer")
        self.assertEqual(response.citations[0].source, "document_registry")
        self.assertIn("customer-guide.pdf", rendered_prompt)

    async def test_chat_grounding_threshold_rejects_weak_match(self) -> None:
        service = ChatCompletionService(
            FakeSession(),
            vector_store=_weak_vector_store(),
            graph_store=FakeGraphStore(),
            behavior=TEST_BEHAVIOR,
        )
        llm_gateway = FakeLLMGateway(_refusal())

        with (
            patch("app.services.chat.completion.build_embedding_gateway", return_value=FakeEmbeddingGateway()),
            patch("app.services.chat.completion.build_llm_gateway", return_value=llm_gateway),
        ):
            response = await service.complete(
                ChatCompletionRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    collection_id="docs",
                    message="Explain an unrelated topic.",
                )
            )

        self.assertEqual(response.strategy, "embedding_first_no_context")
        self.assertEqual(response.answer, TEST_REFUSAL)

    async def test_llm_answer_without_valid_references_is_rejected(self) -> None:
        service = ChatCompletionService(
            FakeSession(),
            vector_store=_vector_store(),
            graph_store=FakeGraphStore(),
            behavior=TEST_BEHAVIOR,
        )
        llm_gateway = FakeLLMGateway(
            '{"decision":"grounded_answer","answer":"Unsupported answer.",'
            '"used_references":[],"self_check":"pass"}'
        )

        with (
            patch("app.services.chat.completion.build_embedding_gateway", return_value=FakeEmbeddingGateway()),
            patch("app.services.chat.completion.build_llm_gateway", return_value=llm_gateway),
        ):
            response = await service.complete(
                ChatCompletionRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    collection_id="docs",
                    message="Which technology is used?",
                )
            )

        self.assertEqual(response.response_type, "refusal")
        self.assertEqual(response.answer, TEST_REFUSAL)
        self.assertEqual(response.citations, [])

    def test_context_compaction_deduplicates_chunks_and_applies_budget(self) -> None:
        blocks = [
            _ContextBlock("vector", "doc", "chunk-a", "A" * 20),
            _ContextBlock("graph", "doc", "chunk-a", "duplicate"),
            _ContextBlock("graph", "doc", "chunk-b", "B" * 20),
        ]

        compacted = _compact_context_blocks(
            blocks,
            total_char_limit=15,
            per_chunk_char_limit=12,
        )

        self.assertEqual([block.chunk_id for block in compacted], ["chunk-a", "chunk-b"])
        self.assertEqual(sum(len(block.text) for block in compacted), 15)

    def test_ingest_disables_semantic_graph_extraction_by_default(self) -> None:
        parameter = inspect.signature(ingest_document).parameters["extract_semantic_graph"]

        self.assertFalse(parameter.default.default)

    def test_chat_response_parser_rejects_non_json_output(self) -> None:
        decision = parse_chat_response(
            "A plausible but unstructured answer.",
            valid_references={1},
            allow_grounded_answer=True,
            behavior=TEST_BEHAVIOR,
        )

        self.assertEqual(decision.response_type, "refusal")
        self.assertEqual(decision.answer, TEST_REFUSAL)

    def test_chat_response_parser_rejects_unknown_inline_citation(self) -> None:
        decision = parse_chat_response(
            '{"decision":"grounded_answer","answer":"Unsupported citation [999]",'
            '"used_references":[1],"self_check":"pass"}',
            valid_references={1},
            allow_grounded_answer=True,
            behavior=TEST_BEHAVIOR,
        )

        self.assertEqual(decision.response_type, "refusal")

    def test_chat_response_parser_accepts_valid_inline_citation_when_used_references_missing(self) -> None:
        decision = parse_chat_response(
            '{"decision":"grounded_answer","answer":"Khách hàng mới được tạo từ menu Khách Hàng. [2]",'
            '"used_references":[],"self_check":"pass"}',
            valid_references={1, 2},
            allow_grounded_answer=True,
            behavior=TEST_BEHAVIOR,
        )

        self.assertEqual(decision.response_type, "grounded_answer")
        self.assertEqual(decision.references, [2])

    def test_chat_response_parser_rejects_social_answer_when_self_check_fails(self) -> None:
        decision = parse_chat_response(
            '{"decision":"social","answer":"Winter flowers always bloom.",'
            '"used_references":[],"self_check":"fail"}',
            valid_references=set(),
            allow_grounded_answer=False,
            behavior=TEST_BEHAVIOR,
        )

        self.assertEqual(decision.response_type, "refusal")

    def test_retrieval_top_k_uses_embedding_profile_value(self) -> None:
        service = ChatCompletionService(
            FakeProfileSession(9),
            behavior=TEST_BEHAVIOR,
        )

        self.assertEqual(service._retrieval_top_k(), 9)

    def test_retrieval_top_k_falls_back_when_profile_value_is_zero(self) -> None:
        service = ChatCompletionService(
            FakeProfileSession(0),
            behavior=TEST_BEHAVIOR,
        )

        self.assertEqual(service._retrieval_top_k(), TEST_BEHAVIOR.default_retrieval_top_k)

    def test_retrieval_top_k_does_not_reuse_older_profile_value(self) -> None:
        service = ChatCompletionService(
            FakeProfileSession(None, 20),
            behavior=TEST_BEHAVIOR,
        )

        self.assertEqual(service._retrieval_top_k(), TEST_BEHAVIOR.default_retrieval_top_k)

    def test_chat_response_parser_rejects_social_answer_that_contains_restricted_topic(self) -> None:
        decision = parse_chat_response(
            '{"decision":"social","answer":"Hãy bàn thêm về chính phủ.",'
            '"used_references":[],"self_check":"pass"}',
            valid_references=set(),
            allow_grounded_answer=False,
            behavior=TEST_BEHAVIOR,
        )

        self.assertEqual(decision.response_type, "refusal")

    def test_chat_response_parser_rejects_grounded_answer_without_context(self) -> None:
        decision = parse_chat_response(
            _grounded_answer(),
            valid_references=set(),
            allow_grounded_answer=False,
            behavior=TEST_BEHAVIOR,
        )

        self.assertEqual(decision.response_type, "refusal")

    def test_default_chat_similarity_threshold_uses_settings(self) -> None:
        self.assertEqual(DEFAULT_CHAT_BEHAVIOR.grounded_min_similarity, settings.CHAT_MIN_GROUNDED_SIMILARITY)

    def test_prompt_treats_paraphrased_workflow_questions_as_groundable(self) -> None:
        messages = chat_response_messages(
            question="luồng đăng ký khách hàng mới?",
            history=[],
            rendered_context="[1] Quy trình tạo khách hàng mới gồm mở menu Khách Hàng và bấm Lưu.",
            rendered_entities="",
            has_document_context=True,
            behavior=TEST_BEHAVIOR,
        )

        self.assertIn("gần nghĩa", messages[0]["content"])

    async def test_chat_sse_stream_emits_metadata_character_deltas_and_done(self) -> None:
        response = ChatCompletionResponse(
            tenant_id="tenant-a",
            app_id="app-a",
            session_id="session-a",
            answer="Ổn",
            strategy="embedding_first_social",
            response_type="social",
        )

        events = [event async for event in _chat_sse_events(response)]

        self.assertIn("event: metadata", events[0])
        self.assertNotIn('"answer"', events[0])
        self.assertEqual(events[1], 'event: delta\ndata: {"text":"Ổ"}\n\n')
        self.assertEqual(events[2], 'event: delta\ndata: {"text":"n"}\n\n')
        self.assertEqual(events[3], 'event: done\ndata: {"finish_reason":"stop"}\n\n')


def _vector_store(vector: list[float] | None = None) -> InMemoryPrecomputedVectorStore:
    store = InMemoryPrecomputedVectorStore()
    store.add_records(
        [
            PrecomputedVectorRecord(
                vector_id="recommendation-system",
                vector=vector or [1.0, 0.0, 0.0],
                text="The recommendation system uses LanceDB for vector retrieval.",
                tenant_id="tenant-a",
                app_id="app-a",
                collection_id="docs",
                document_id="policy",
                chunk_id="recommendation-system",
                chunk_index=0,
                embedding_profile_id="embedding-profile",
                embedding_model="gemini-embedding-2",
                metadata={"filename": "architecture.txt"},
            )
        ]
    )
    return store


def _weak_vector_store() -> InMemoryPrecomputedVectorStore:
    return _vector_store([0.49, math.sqrt(1 - 0.49**2), 0.0])


def _grounded_answer() -> str:
    return (
        '{"decision":"grounded_answer","answer":"The recommendation system uses LanceDB. [1]",'
        '"used_references":[1],"self_check":"pass"}'
    )


def _refusal() -> str:
    return '{"decision":"refuse","answer":"","used_references":[],"self_check":"pass"}'


if __name__ == "__main__":
    unittest.main()
