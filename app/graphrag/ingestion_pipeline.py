from __future__ import annotations

from dataclasses import replace

from app.graphrag.graph_database import (
    GraphDatabaseScope,
    GraphIngestResult,
    KuzuGraphStore,
    SemanticExtractionError,
    SemanticGraphExtractor,
    get_kuzu_graph_store,
)
from app.services.ingestion.models import IngestionBundle


class GraphRAGIngestionPipeline:
    """Persists parsed document structure into the GraphRAG graph store."""

    def __init__(self, graph_store: KuzuGraphStore | None = None) -> None:
        self.graph_store = graph_store or get_kuzu_graph_store()

    async def ingest_graph(
        self,
        bundle: IngestionBundle,
        *,
        semantic_extractor: SemanticGraphExtractor | None = None,
    ) -> GraphIngestResult:
        result = self.graph_store.ingest_bundle(bundle)
        if semantic_extractor is None:
            return result

        parsed = bundle.parsed_document
        scope = GraphDatabaseScope(
            tenant_id=parsed.scope.tenant_id,
            app_id=parsed.scope.app_id,
            collection_id=parsed.scope.collection_id,
        )
        entity_count = 0
        relation_count = 0
        mention_count = 0
        warnings: list[str] = []
        for chunk in bundle.chunks:
            if not chunk.is_embeddable or not chunk.text.strip():
                continue
            try:
                extraction = await semantic_extractor.extract_chunk(
                    chunk.text,
                    tenant_id=scope.tenant_id,
                    app_id=scope.app_id,
                    collection_id=scope.collection_id,
                )
                stored = self.graph_store.persist_semantic_extraction(
                    scope=scope,
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    extraction=extraction,
                )
                entity_count += stored.entity_count
                relation_count += stored.relation_count
                mention_count += stored.mention_count
            except SemanticExtractionError as exc:
                warnings.append(f"Semantic extraction skipped for chunk {chunk.chunk_id}: {exc}")

        return replace(
            result,
            semantic_entity_count=entity_count,
            semantic_relation_count=relation_count,
            semantic_mention_count=mention_count,
            semantic_warnings=warnings,
        )
