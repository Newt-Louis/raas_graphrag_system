from __future__ import annotations

from app.graphrag.graph_database import (
    GraphContextResult,
    GraphDatabaseScope,
    GraphTraversalResult,
    GraphVisualizationResult,
    KuzuGraphStore,
    get_kuzu_graph_store,
)


class GraphRAGQueryPipeline:
    """Reads graph context needed to expand vector retrieval results."""

    def __init__(self, graph_store: KuzuGraphStore | None = None) -> None:
        self.graph_store = graph_store or get_kuzu_graph_store()

    def chunk_context(
        self,
        *,
        tenant_id: str,
        app_id: str,
        collection_id: str | None,
        chunk_ids: list[str],
    ) -> GraphContextResult:
        return self.graph_store.chunk_context(
            scope=GraphDatabaseScope(
                tenant_id=tenant_id,
                app_id=app_id,
                collection_id=collection_id,
            ),
            chunk_ids=chunk_ids,
        )

    def entity_context(
        self,
        *,
        tenant_id: str,
        app_id: str,
        collection_id: str | None,
        entity_names: list[str],
        hops: int = 2,
    ) -> GraphTraversalResult:
        return self.graph_store.entity_context(
            scope=GraphDatabaseScope(tenant_id=tenant_id, app_id=app_id, collection_id=collection_id),
            entity_names=entity_names,
            hops=hops,
        )

    def semantic_context_for_chunks(
        self,
        *,
        tenant_id: str,
        app_id: str,
        collection_id: str | None,
        chunk_ids: list[str],
        hops: int = 1,
    ) -> GraphTraversalResult:
        return self.graph_store.semantic_context_for_chunks(
            scope=GraphDatabaseScope(tenant_id=tenant_id, app_id=app_id, collection_id=collection_id),
            chunk_ids=chunk_ids,
            hops=hops,
        )

    def visualization(
        self,
        *,
        tenant_id: str,
        app_id: str,
        collection_id: str | None,
        document_id: str | None = None,
        include_structure: bool = True,
        include_semantic: bool = True,
        limit: int = 2_000,
    ) -> GraphVisualizationResult:
        return self.graph_store.graph_visualization(
            scope=GraphDatabaseScope(tenant_id=tenant_id, app_id=app_id, collection_id=collection_id),
            document_id=document_id,
            include_structure=include_structure,
            include_semantic=include_semantic,
            limit=limit,
        )
