from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

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
    def __init__(self) -> None:
        self.document_inputs: list[Any] = []

    async def embed_documents(self, texts: list[Any], **kwargs):
        self.document_inputs = texts
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

    def _embed(self, text: Any) -> list[float]:
        normalized = str(text).lower()
        if "refund" in normalized:
            return [1.0, 0.0, 0.0]
        if "image_url" in normalized:
            return [0.5, 0.5, 0.0]
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

    async def test_delete_document_removes_only_matching_scope_records(self) -> None:
        store = InMemoryPrecomputedVectorStore(table_name="test_chunks")
        pipeline = GraphRAGVectorDatabasePipeline(
            ai_client=FakeEmbeddingAIClient(),
            vector_store=store,
        )
        scope = VectorDatabaseScope("tenant-a", "support", "docs")
        await pipeline.ingest(
            VectorIngestRequest(
                scope=scope,
                chunks=[
                    VectorDocumentChunk(document_id="policy-a", chunk_id="refund-a", text="Refund policy."),
                    VectorDocumentChunk(document_id="policy-b", chunk_id="refund-b", text="Refund policy."),
                ],
            )
        )

        deleted = store.delete_document(scope=scope, document_id="policy-a")
        remaining = store.list_records(scope=scope)

        self.assertEqual(deleted, 1)
        self.assertEqual([record.document_id for record in remaining], ["policy-b"])

    async def test_image_chunks_are_sent_to_embedding_gateway_as_data_url_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "photo.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

            ai_client = FakeEmbeddingAIClient()
            pipeline = GraphRAGVectorDatabasePipeline(
                ai_client=ai_client,
                vector_store=InMemoryPrecomputedVectorStore(table_name="test_chunks"),
            )

            result = await pipeline.ingest(
                VectorIngestRequest(
                    scope=VectorDatabaseScope("tenant-a", "support", "images"),
                    chunks=[
                        VectorDocumentChunk(
                            document_id="photo",
                            chunk_id="photo-image",
                            text="[Image: photo.png]",
                            metadata={
                                "media": [
                                    {
                                        "type": "image",
                                        "stored_path": str(image_path),
                                        "content_type": "image/png",
                                    }
                                ]
                            },
                        )
                    ],
                )
            )

        self.assertEqual(result.stored_count, 1)
        self.assertIsInstance(ai_client.document_inputs[0], list)
        image_part = ai_client.document_inputs[0][1]
        self.assertEqual(image_part["type"], "image_url")
        self.assertTrue(image_part["image_url"]["url"].startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
