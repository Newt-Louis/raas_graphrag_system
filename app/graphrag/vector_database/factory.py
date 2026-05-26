from __future__ import annotations

from app.core.config import settings
from app.graphrag.ai_client import GraphRAGAIClient
from app.graphrag.vector_database.lancedb_store import LanceDBPrecomputedVectorStore
from app.graphrag.vector_database.pipeline import GraphRAGVectorDatabasePipeline


def get_lancedb_vector_store() -> LanceDBPrecomputedVectorStore:
    return LanceDBPrecomputedVectorStore(
        db_path=settings.LANCEDB_PATH,
        table_name=settings.VECTOR_INDEX_TABLE,
        distance_metric=settings.VECTOR_DISTANCE_METRIC,
    )


def get_vector_database_pipeline(ai_client: GraphRAGAIClient) -> GraphRAGVectorDatabasePipeline:
    return GraphRAGVectorDatabasePipeline(
        ai_client=ai_client,
        vector_store=get_lancedb_vector_store(),
    )
