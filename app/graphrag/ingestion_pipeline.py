from __future__ import annotations

from app.graphrag.graph_database import GraphIngestResult, KuzuGraphStore, get_kuzu_graph_store
from app.services.ingestion.models import IngestionBundle


class GraphRAGIngestionPipeline:
    """Persists parsed document structure into the GraphRAG graph store."""

    def __init__(self, graph_store: KuzuGraphStore | None = None) -> None:
        self.graph_store = graph_store or get_kuzu_graph_store()

    def ingest_graph(self, bundle: IngestionBundle) -> GraphIngestResult:
        return self.graph_store.ingest_bundle(bundle)
