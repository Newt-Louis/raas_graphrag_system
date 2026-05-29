from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

from app.ai_gateway.base_rotator import RotationResult
from app.graphrag.graph_database import (
    GraphChunkContext,
    GraphContextResult,
    GraphDatabaseScope,
    GraphDocumentChunkStats,
)
from app.graphrag.vector_database import (
    InMemoryPrecomputedVectorStore,
    PrecomputedVectorRecord,
)
from app.models.ai_gateway import EmbeddingModelProfile
from app.schemas.visualize import VectorHealthRequest, VectorSearchDebugRequest
from app.services.visualize import VectorVisualizationService


class FakeScalarResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, profiles=None) -> None:
        self.profiles = profiles or []

    def scalars(self, statement):
        return FakeScalarResult(self.profiles)


class FakeEmbeddingGateway:
    async def embed(self, texts, **kwargs):
        return RotationResult(
            success=True,
            data=[[1.0, 0.0, 0.0]],
            profile_id=kwargs.get("profile_id") or "runtime-embedding-pool",
            used_model="fake-embedding-model",
            used_key_id="fake-key",
            used_provider="fake-provider",
        )


class FakeGraphStore:
    def document_chunk_stats(self, *, scope, document_id=None):
        stats = {
            "policy": GraphDocumentChunkStats(
                document_id="policy",
                chunk_count=3,
                embeddable_chunk_count=3,
            )
        }
        if document_id:
            return {key: value for key, value in stats.items() if key == document_id}
        return stats

    def chunk_context(self, *, scope: GraphDatabaseScope, chunk_ids: list[str]):
        return GraphContextResult(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
            chunks=[
                GraphChunkContext(
                    document_id="policy",
                    chunk_id="refund-policy",
                    text="Refund policy allows eligible refunds within 30 days.",
                    chunk_index=0,
                    next_chunk_id="refund-policy-2",
                )
            ],
        )


class VectorVisualizationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_debug_returns_ranked_matches_with_graph_context(self) -> None:
        store = InMemoryPrecomputedVectorStore()
        store.add_records(
            [
                PrecomputedVectorRecord(
                    vector_id="policy-refund",
                    vector=[1.0, 0.0, 0.0],
                    text="Refund policy allows eligible refunds within 30 days.",
                    tenant_id="tenant-a",
                    app_id="app-a",
                    collection_id="docs",
                    document_id="policy",
                    chunk_id="refund-policy",
                    chunk_index=0,
                    embedding_profile_id="embedding-profile",
                    embedding_model="fake-embedding-model",
                    metadata={"filename": "policy.txt"},
                )
            ]
        )
        service = VectorVisualizationService(
            db=FakeSession(),
            vector_store=store,
            graph_store=FakeGraphStore(),
        )

        with patch("app.services.visualize.vector.build_embedding_gateway", return_value=FakeEmbeddingGateway()):
            response = await service.search_debug(
                VectorSearchDebugRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    collection_id="docs",
                    query="refund",
                    top_k=3,
                )
            )

        self.assertEqual(response.matches[0].rank, 1)
        self.assertEqual(response.matches[0].chunk_id, "refund-policy")
        self.assertEqual(response.matches[0].graph_context.next_chunk_id, "refund-policy-2")
        self.assertEqual(response.embedding_model, "fake-embedding-model")

    async def test_embedding_health_groups_by_document_profile_and_dimension(self) -> None:
        profile_id = uuid4()
        profile = EmbeddingModelProfile(
            id=profile_id,
            provider_id=uuid4(),
            api_key_id=uuid4(),
            profile_name="Embedding Profile",
            model_name="text-embedding-test",
            embedding_dimensions=3,
            timeout_seconds=60,
        )
        store = InMemoryPrecomputedVectorStore()
        store.add_records(
            [
                PrecomputedVectorRecord(
                    vector_id="policy-refund",
                    vector=[1.0, 0.0, 0.0],
                    text="Refund policy.",
                    tenant_id="tenant-a",
                    app_id="app-a",
                    collection_id="docs",
                    document_id="policy",
                    chunk_id="refund-policy",
                    chunk_index=0,
                    embedding_profile_id=str(profile_id),
                    embedding_model="text-embedding-test",
                    metadata={"filename": "policy.txt"},
                ),
                PrecomputedVectorRecord(
                    vector_id="policy-window",
                    vector=[0.8, 0.1, 0.0],
                    text="Refund window.",
                    tenant_id="tenant-a",
                    app_id="app-a",
                    collection_id="docs",
                    document_id="policy",
                    chunk_id="refund-window",
                    chunk_index=1,
                    embedding_profile_id=str(profile_id),
                    embedding_model="text-embedding-test",
                    metadata={"filename": "policy.txt"},
                ),
            ]
        )
        service = VectorVisualizationService(
            db=FakeSession([profile]),
            vector_store=store,
            graph_store=FakeGraphStore(),
        )

        response = service.embedding_health(
            VectorHealthRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                collection_id="docs",
            )
        )

        self.assertEqual(response.total_embedded_chunks, 2)
        self.assertEqual(len(response.documents), 1)
        item = response.documents[0]
        self.assertEqual(item.embedding_profile_name, "Embedding Profile")
        self.assertEqual(item.expected_dimension, 3)
        self.assertEqual(item.vector_dimension, 3)
        self.assertEqual(item.dimension_status, "ok")
        self.assertEqual(item.embedded_chunk_count, 2)
        self.assertEqual(item.graph_embeddable_chunk_count, 3)
        self.assertEqual(item.missing_embedding_count, 1)

    async def test_embedding_health_includes_graph_only_documents(self) -> None:
        service = VectorVisualizationService(
            db=FakeSession(),
            vector_store=InMemoryPrecomputedVectorStore(),
            graph_store=FakeGraphStore(),
        )

        response = service.embedding_health(
            VectorHealthRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                collection_id="docs",
            )
        )

        self.assertEqual(response.total_embedded_chunks, 0)
        self.assertEqual(len(response.documents), 1)
        self.assertEqual(response.documents[0].document_id, "policy")
        self.assertEqual(response.documents[0].embedded_chunk_count, 0)
        self.assertEqual(response.documents[0].missing_embedding_count, 3)


if __name__ == "__main__":
    unittest.main()
