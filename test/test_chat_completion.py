from __future__ import annotations

import inspect
import math
import unittest
from unittest.mock import patch

from app.ai_gateway.base_rotator import RotationResult
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
from app.schemas.chat import ChatCompletionRequest
from app.services.chat.completion import (
    ChatCompletionService,
    _ContextBlock,
    _compact_context_blocks,
)
from app.services.chat.behavior import REFUSAL_MESSAGE
from app.services.chat.policy import parse_grounded_answer


class FakeSession:
    def get(self, model, record_id):
        return None


class FakeEmbeddingGateway:
    async def embed(self, texts, **kwargs):
        return RotationResult(
            success=True,
            data=[[1.0, 0.0, 0.0]],
            profile_id="embedding-profile",
            used_model="gemini-embedding-2",
        )


class FakeLLMGateway:
    def __init__(self, data=None) -> None:
        self.messages = []
        self.data = data or (
            '{"decision":"answer","answer":"The recommendation system uses LanceDB. [1]",'
            '"used_references":[1]}'
        )

    async def complete(self, messages, **kwargs):
        self.messages = messages
        return RotationResult(
            success=True,
            data=self.data,
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


class ChatCompletionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_completion_uses_vector_graph_context_and_llm_synthesis(self) -> None:
        store = _vector_store()
        llm_gateway = FakeLLMGateway()
        service = ChatCompletionService(
            FakeSession(),
            vector_store=store,
            graph_store=FakeGraphStore(),
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
        self.assertIn("LanceDB", llm_gateway.messages[-1]["content"])
        self.assertIn("Return only valid JSON", llm_gateway.messages[0]["content"])

    async def test_social_message_does_not_call_embedding_or_llm(self) -> None:
        service = ChatCompletionService(
            FakeSession(),
            vector_store=InMemoryPrecomputedVectorStore(),
            graph_store=FakeGraphStore(),
        )

        with (
            patch("app.services.chat.completion.build_embedding_gateway", side_effect=AssertionError),
            patch("app.services.chat.completion.build_llm_gateway", side_effect=AssertionError),
        ):
            response = await service.complete(
                ChatCompletionRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    message="Xin chào",
                )
            )

        self.assertEqual(response.strategy, "social")
        self.assertEqual(response.response_type, "social")
        self.assertIn("Xin chào", response.answer)

    async def test_no_retrieval_context_returns_exact_refusal_without_llm(self) -> None:
        service = ChatCompletionService(
            FakeSession(),
            vector_store=InMemoryPrecomputedVectorStore(),
            graph_store=FakeGraphStore(),
        )

        with (
            patch("app.services.chat.completion.build_embedding_gateway", return_value=FakeEmbeddingGateway()),
            patch("app.services.chat.completion.build_llm_gateway", side_effect=AssertionError),
        ):
            response = await service.complete(
                ChatCompletionRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    message="Explain backpropagation.",
                )
            )

        self.assertEqual(response.strategy, "no_context")
        self.assertEqual(response.response_type, "refusal")
        self.assertEqual(response.answer, REFUSAL_MESSAGE)

    async def test_chat_grounding_threshold_rejects_weak_match(self) -> None:
        service = ChatCompletionService(
            FakeSession(),
            vector_store=_weak_vector_store(),
            graph_store=FakeGraphStore(),
        )

        with (
            patch("app.services.chat.completion.build_embedding_gateway", return_value=FakeEmbeddingGateway()),
            patch("app.services.chat.completion.build_llm_gateway", side_effect=AssertionError),
        ):
            response = await service.complete(
                ChatCompletionRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    collection_id="docs",
                    message="Explain an unrelated topic.",
                    min_similarity=0.1,
                )
            )

        self.assertEqual(response.strategy, "no_context")
        self.assertEqual(response.answer, REFUSAL_MESSAGE)

    async def test_llm_answer_without_valid_references_is_rejected(self) -> None:
        service = ChatCompletionService(
            FakeSession(),
            vector_store=_vector_store(),
            graph_store=FakeGraphStore(),
        )
        llm_gateway = FakeLLMGateway(
            '{"decision":"answer","answer":"Unsupported answer.","used_references":[]}'
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
        self.assertEqual(response.answer, REFUSAL_MESSAGE)
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

    def test_ingest_enables_semantic_graph_extraction_by_default(self) -> None:
        parameter = inspect.signature(ingest_document).parameters["extract_semantic_graph"]

        self.assertTrue(parameter.default.default)

    def test_grounded_answer_parser_rejects_non_json_output(self) -> None:
        decision = parse_grounded_answer("A plausible but unstructured answer.", valid_references={1})

        self.assertEqual(decision.response_type, "refusal")
        self.assertEqual(decision.answer, REFUSAL_MESSAGE)

    def test_grounded_answer_parser_rejects_unknown_inline_citation(self) -> None:
        decision = parse_grounded_answer(
            '{"decision":"answer","answer":"Unsupported citation [999]","used_references":[1]}',
            valid_references={1},
        )

        self.assertEqual(decision.response_type, "refusal")


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
    return _vector_store([0.5, math.sqrt(0.75), 0.0])


if __name__ == "__main__":
    unittest.main()
