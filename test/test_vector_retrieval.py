from __future__ import annotations

import unittest
from typing import Any

from app.ai_gateway.base_rotator import RotationResult
from app.graphrag.graph_database import (
    GraphContextResult,
    GraphEntityContext,
    GraphTraversalResult,
)
from app.graphrag.vector_database import (
    InMemoryPrecomputedVectorStore,
    PrecomputedVectorRecord,
    VectorDatabaseScope,
)
from app.services.retrieval import GraphRAGRetrievalService


class FakeEmbeddingAIClient:
    """Embeds the query into the same toy space used by the stored vectors."""

    async def embed_query(self, query: str, **kwargs: Any) -> RotationResult:
        return RotationResult(
            success=True,
            data=[self._embed(query)],
            profile_id="embedding-profile",
            used_model="fake-embedding-model",
        )

    def _embed(self, text: str) -> list[float]:
        normalized = str(text).lower()
        if "refund" in normalized:
            return [1.0, 0.0, 0.0]
        if "warehouse" in normalized:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


class NoGraphStore:
    def semantic_context_for_chunks(self, *, scope, chunk_ids, hops):
        return GraphTraversalResult(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
        )

    def chunk_context(self, *, scope, chunk_ids):
        return GraphContextResult(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
            chunks=[],
        )


class SemanticGraphStore(NoGraphStore):
    def semantic_context_for_chunks(self, *, scope, chunk_ids, hops):
        return GraphTraversalResult(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
            entities=[GraphEntityContext(entity_id="e1", entity_type="Policy", name="Refund policy")],
            chunk_ids=list(chunk_ids),
        )


def _record(
    *,
    vector_id: str,
    text: str,
    vector: list[float],
    tenant_id: str,
    app_id: str,
    collection_id: str | None = None,
    document_id: str,
) -> PrecomputedVectorRecord:
    return PrecomputedVectorRecord(
        vector_id=vector_id,
        vector=vector,
        text=text,
        tenant_id=tenant_id,
        app_id=app_id,
        collection_id=collection_id,
        document_id=document_id,
        chunk_id=vector_id,
        chunk_index=0,
        embedding_profile_id="embedding-profile",
        embedding_model="fake-embedding-model",
        metadata={"document_id": document_id, "chunk_id": vector_id},
    )


def _service(store: InMemoryPrecomputedVectorStore, graph_store=None) -> GraphRAGRetrievalService:
    return GraphRAGRetrievalService(
        db=None,
        vector_store=store,
        graph_store=graph_store or NoGraphStore(),
        embedding_ai_client=FakeEmbeddingAIClient(),
    )


class GraphRAGRetrievalServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_retrieval_is_scoped_by_tenant_and_app(self) -> None:
        store = InMemoryPrecomputedVectorStore()
        store.add_records(
            [
                _record(
                    vector_id="chunk-a",
                    text="Refunds are available within 30 days for eligible orders.",
                    vector=[1.0, 0.0, 0.0],
                    tenant_id="tenant-a",
                    app_id="support",
                    collection_id="docs",
                    document_id="doc-a",
                ),
                _record(
                    vector_id="chunk-b",
                    text="Warehouse shift schedules are managed by operations.",
                    vector=[0.0, 1.0, 0.0],
                    tenant_id="tenant-b",
                    app_id="support",
                    collection_id="docs",
                    document_id="doc-b",
                ),
            ]
        )

        retrieval = await _service(store).retrieve(
            scope=VectorDatabaseScope(tenant_id="tenant-a", app_id="support", collection_id="docs"),
            query="What is the refund window?",
            top_k=5,
            min_similarity=0.0,
        )

        self.assertEqual([match.chunk_id for match in retrieval.vector_matches], ["chunk-a"])
        self.assertEqual(retrieval.strategy, "vector_only")

    async def test_retrieval_orders_by_cosine_score(self) -> None:
        store = InMemoryPrecomputedVectorStore()
        store.add_records(
            [
                _record(
                    vector_id="least-related",
                    text="Admins can configure widget colors and launch position.",
                    vector=[0.0, 0.0, 1.0],
                    tenant_id="tenant-a",
                    app_id="support",
                    document_id="doc-ui",
                ),
                _record(
                    vector_id="most-related",
                    text="The refund policy allows refunds within 30 days.",
                    vector=[1.0, 0.0, 0.0],
                    tenant_id="tenant-a",
                    app_id="support",
                    document_id="doc-policy",
                ),
            ]
        )

        retrieval = await _service(store).retrieve(
            scope=VectorDatabaseScope(tenant_id="tenant-a", app_id="support"),
            query="refund policy",
            top_k=1,
            min_similarity=0.0,
        )

        self.assertEqual([match.chunk_id for match in retrieval.vector_matches], ["most-related"])

    async def test_min_similarity_filters_weak_matches(self) -> None:
        store = InMemoryPrecomputedVectorStore()
        store.add_records(
            [
                _record(
                    vector_id="unrelated",
                    text="Widget launch position settings.",
                    vector=[0.0, 0.0, 1.0],
                    tenant_id="tenant-a",
                    app_id="support",
                    document_id="doc-ui",
                )
            ]
        )

        retrieval = await _service(store).retrieve(
            scope=VectorDatabaseScope(tenant_id="tenant-a", app_id="support"),
            query="refund policy",
            top_k=5,
            min_similarity=0.5,
        )

        self.assertEqual(retrieval.vector_matches, [])
        self.assertEqual(retrieval.strategy, "no_context")

    async def test_semantic_graph_expansion_sets_strategy(self) -> None:
        store = InMemoryPrecomputedVectorStore()
        store.add_records(
            [
                _record(
                    vector_id="chunk-a",
                    text="The refund policy allows refunds within 30 days.",
                    vector=[1.0, 0.0, 0.0],
                    tenant_id="tenant-a",
                    app_id="support",
                    document_id="doc-policy",
                )
            ]
        )

        retrieval = await _service(store, graph_store=SemanticGraphStore()).retrieve(
            scope=VectorDatabaseScope(tenant_id="tenant-a", app_id="support"),
            query="refund policy",
            top_k=5,
            min_similarity=0.0,
        )

        self.assertEqual(retrieval.strategy, "vector_semantic_graph")
        self.assertEqual(retrieval.graph_entities[0].name, "Refund policy")


if __name__ == "__main__":
    unittest.main()
