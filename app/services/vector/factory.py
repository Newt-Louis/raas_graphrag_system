from __future__ import annotations

from app.core.config import settings
from app.services.vector.embeddings import HashingTextEmbeddingService, TextEmbeddingService
from app.services.vector.store import LanceDBVectorStore


def get_embedding_service() -> TextEmbeddingService:
    return HashingTextEmbeddingService(
        dimensions=settings.EMBEDDING_DIMENSIONS,
        model_name=settings.EMBEDDING_MODEL_NAME,
    )


def get_vector_store() -> LanceDBVectorStore:
    return LanceDBVectorStore(
        db_path=settings.LANCEDB_PATH,
        table_name=settings.VECTOR_INDEX_TABLE,
        embedding_service=get_embedding_service(),
        distance_metric=settings.VECTOR_DISTANCE_METRIC,
    )
