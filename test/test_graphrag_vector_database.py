from __future__ import annotations

import unittest

from app.ai_gateway.base_rotator import RotationResult
from app.graphrag.vector_database import (
    GraphRAGVectorDatabasePipeline,
    InMemoryPrecomputedVectorStore,
    VectorDatabaseScope,
    VectorDocumentChunk,
    VectorIngestRequest,
    VectorQueryRequest,
)


class FakeEmbeddingAIClient:
    async def embed_documents(self, texts: list[str], **kwargs):
        return RotationResult(
            success=True,
            data=[self._embed(text) for text in texts],
            profile_id=kwargs.get("profile_id") or "embedding-profile",
            used_model="fake-embedding-model",
            used_key_id="fake-key",
            used_provider="fake-provider",
        )

    async def embed_query(self, query: str, **kwargs):
        return RotationResult(
            success=True,
            data=[self._embed(query)],
            profile_id=kwargs.get("profile_id") or "embedding-profile",
            used_model="fake-embedding-model",
            used_key_id="fake-key",
            used_provider="fake-provider",
        )

    def _embed(self, text: str) -> list[float]:
        normalized = text.lower()
        if "refund" in normalized:
            return [1.0, 0.0, 0.0]
        if "warehouse" in normalized:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


class GraphRAGVectorDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_ingest_uses_embedding_gateway_and_query_returns_cosine_similarity(self) -> None:
        pipeline = GraphRAGVectorDatabasePipeline(
            ai_client=FakeEmbeddingAIClient(),
            vector_store=InMemoryPrecomputedVectorStore(table_name="test_chunks"),
        )
        scope = VectorDatabaseScope(
            tenant_id="tenant-a",
            app_id="support",
            collection_id="docs",
        )

        ingest_result = await pipeline.ingest(
            VectorIngestRequest(
                scope=scope,
                embedding_profile_id="embedding-profile",
                chunks=[
                    VectorDocumentChunk(
                        document_id="policy",
                        chunk_id="refund-policy",
                        chunk_index=0,
                        text="Refund policy allows eligible refunds within 30 days.",
                    ),
                    VectorDocumentChunk(
                        document_id="ops",
                        chunk_id="warehouse-schedule",
                        chunk_index=1,
                        text="Warehouse shift schedules are managed by operations.",
                    ),
                ],
            )
        )

        query_result = await pipeline.query(
            VectorQueryRequest(
                scope=scope,
                query="refund window",
                top_k=2,
            )
        )

        self.assertEqual(ingest_result.embedded_count, 2)
        self.assertEqual(ingest_result.stored_count, 2)
        self.assertEqual(query_result.embedding_model, "fake-embedding-model")
        self.assertEqual(query_result.matches[0].chunk_id, "refund-policy")
        self.assertGreater(query_result.matches[0].similarity, query_result.matches[1].similarity)

    async def test_query_is_scoped_by_tenant_app_collection(self) -> None:
        pipeline = GraphRAGVectorDatabasePipeline(
            ai_client=FakeEmbeddingAIClient(),
            vector_store=InMemoryPrecomputedVectorStore(table_name="test_chunks"),
        )

        await pipeline.ingest(
            VectorIngestRequest(
                scope=VectorDatabaseScope("tenant-a", "support", "docs"),
                chunks=[
                    VectorDocumentChunk(
                        document_id="policy-a",
                        chunk_id="refund-a",
                        text="Refund policy for tenant A.",
                    )
                ],
            )
        )
        await pipeline.ingest(
            VectorIngestRequest(
                scope=VectorDatabaseScope("tenant-b", "support", "docs"),
                chunks=[
                    VectorDocumentChunk(
                        document_id="policy-b",
                        chunk_id="refund-b",
                        text="Refund policy for tenant B.",
                    )
                ],
            )
        )

        query_result = await pipeline.query(
            VectorQueryRequest(
                scope=VectorDatabaseScope("tenant-a", "support", "docs"),
                query="refund",
                top_k=10,
            )
        )

        self.assertEqual([match.chunk_id for match in query_result.matches], ["refund-a"])


if __name__ == "__main__":
    unittest.main()
