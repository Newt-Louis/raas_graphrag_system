from __future__ import annotations

from app.graphrag.graph_database import (
    GraphContextResult,
    GraphDatabaseScope,
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
