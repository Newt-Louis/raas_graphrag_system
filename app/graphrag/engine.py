from __future__ import annotations

from app.graphrag.ingestion_pipeline import GraphRAGIngestionPipeline
from app.graphrag.query_pipeline import GraphRAGQueryPipeline


class GraphRAGEngine:
    """Small composition root for GraphRAG graph ingestion and query flows."""

    def __init__(
        self,
        ingestion_pipeline: GraphRAGIngestionPipeline | None = None,
        query_pipeline: GraphRAGQueryPipeline | None = None,
    ) -> None:
        self.ingestion_pipeline = ingestion_pipeline or GraphRAGIngestionPipeline()
        self.query_pipeline = query_pipeline or GraphRAGQueryPipeline()
