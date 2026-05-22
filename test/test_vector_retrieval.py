from __future__ import annotations

import unittest

from app.services.ingestion.models import VectorRecord
from app.services.retrieval.models import RetrievalRequest
from app.services.retrieval.orchestrator import RetrievalOrchestrator
from app.services.vector import HashingTextEmbeddingService, InMemoryVectorStore


class VectorRetrievalTests(unittest.TestCase):
    def test_hashing_embedding_is_deterministic_and_normalized(self) -> None:
        embedder = HashingTextEmbeddingService(dimensions=64)

        first = embedder.embed_text("Refund policy allows returns.")
        second = embedder.embed_text("Refund policy allows returns.")

        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(value * value for value in first), 1.0)

    def test_vector_retrieval_is_scoped_by_tenant_and_app(self) -> None:
        embedder = HashingTextEmbeddingService(dimensions=128)
        store = InMemoryVectorStore(embedder)
        store.add_records(
            [
                VectorRecord(
                    vector_id="chunk-a",
                    text="Refunds are available within 30 days for eligible orders.",
                    metadata={
                        "tenant_id": "tenant-a",
                        "app_id": "support",
                        "collection_id": "docs",
                        "document_id": "doc-a",
                        "chunk_id": "chunk-a",
                    },
                ),
                VectorRecord(
                    vector_id="chunk-b",
                    text="Warehouse shift schedules are managed by operations.",
                    metadata={
                        "tenant_id": "tenant-b",
                        "app_id": "support",
                        "collection_id": "docs",
                        "document_id": "doc-b",
                        "chunk_id": "chunk-b",
                    },
                ),
            ]
        )

        result = RetrievalOrchestrator(store).retrieve(
            RetrievalRequest(
                tenant_id="tenant-a",
                app_id="support",
                collection_id="docs",
                query="What is the refund window?",
                top_k=5,
            )
        )

        self.assertEqual(len(result.contexts), 1)
        self.assertEqual(result.contexts[0].chunk_id, "chunk-a")
        self.assertEqual(result.contexts[0].source, "vector")
        self.assertEqual(result.strategy, "vector_only")

    def test_vector_retrieval_orders_by_cosine_score(self) -> None:
        embedder = HashingTextEmbeddingService(dimensions=128)
        store = InMemoryVectorStore(embedder)
        store.add_records(
            [
                VectorRecord(
                    vector_id="least-related",
                    text="Admins can configure widget colors and launch position.",
                    metadata={
                        "tenant_id": "tenant-a",
                        "app_id": "support",
                        "document_id": "doc-ui",
                        "chunk_id": "least-related",
                    },
                ),
                VectorRecord(
                    vector_id="most-related",
                    text="The refund policy allows refunds within 30 days.",
                    metadata={
                        "tenant_id": "tenant-a",
                        "app_id": "support",
                        "document_id": "doc-policy",
                        "chunk_id": "most-related",
                    },
                ),
            ]
        )

        result = RetrievalOrchestrator(store).retrieve(
            RetrievalRequest(
                tenant_id="tenant-a",
                app_id="support",
                query="refund policy",
                top_k=1,
            )
        )

        self.assertEqual([context.chunk_id for context in result.contexts], ["most-related"])


if __name__ == "__main__":
    unittest.main()
