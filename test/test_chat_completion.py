from __future__ import annotations

import inspect
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
    def __init__(self) -> None:
        self.messages = []

    async def complete(self, messages, **kwargs):
        self.messages = messages
        return RotationResult(
            success=True,
            data="The recommendation system uses LanceDB. [1]",
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
        store = InMemoryPrecomputedVectorStore()
        store.add_records(
            [
                PrecomputedVectorRecord(
                    vector_id="recommendation-system",
                    vector=[1.0, 0.0, 0.0],
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
        self.assertEqual(response.citations[0].filename, "architecture.txt")
        self.assertEqual(response.usage["total_tokens"], 42)
        self.assertIn("LanceDB", llm_gateway.messages[-1]["content"])

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


if __name__ == "__main__":
    unittest.main()
