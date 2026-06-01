from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.graphrag.vector_database import (
    InMemoryPrecomputedVectorStore,
    LanceDBPrecomputedVectorStore,
    PrecomputedVectorRecord,
    VectorDatabaseScope,
)
from app.services.ingestion.models import IngestionBundle, VectorRecord
from app.services.vector.embeddings import TextEmbeddingService


@dataclass(frozen=True)
class VectorSearchQuery:
    tenant_id: str
    app_id: str
    query: str
    collection_id: str | None = None
    top_k: int = 5
    min_score: float = 0.0


@dataclass
class VectorSearchResult:
    vector_id: str
    text: str
    score: float
    distance: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(Protocol):
    def add_records(self, records: list[VectorRecord]) -> int:
        ...

    def search(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
        ...


class LanceDBVectorStore:
    """Compatibility service backed by the LlamaIndex LanceDB adapter."""

    def __init__(
        self,
        db_path: Path,
        table_name: str,
        embedding_service: TextEmbeddingService,
        distance_metric: str = "cosine",
    ) -> None:
        self.embedding_service = embedding_service
        self.store = LanceDBPrecomputedVectorStore(
            db_path=db_path,
            table_name=table_name,
            distance_metric=distance_metric,
        )

    def persist_vectors(self, bundle: IngestionBundle) -> int:
        return self.add_records(bundle.vector_records)

    def add_records(self, records: list[VectorRecord]) -> int:
        vectors = self.embedding_service.embed_batch([record.text for record in records])
        return self.store.add_records(
            [
                _precomputed_record(record, vector, model_name=self.embedding_service.model_name)
                for record, vector in zip(records, vectors, strict=True)
            ]
        )

    def search(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
        return _search(self.store, self.embedding_service, query)


class InMemoryVectorStore:
    """Compatibility test service backed by LlamaIndex SimpleVectorStore."""

    def __init__(self, embedding_service: TextEmbeddingService) -> None:
        self.embedding_service = embedding_service
        self.store = InMemoryPrecomputedVectorStore()

    def add_records(self, records: list[VectorRecord]) -> int:
        vectors = self.embedding_service.embed_batch([record.text for record in records])
        return self.store.add_records(
            [
                _precomputed_record(record, vector, model_name=self.embedding_service.model_name)
                for record, vector in zip(records, vectors, strict=True)
            ]
        )

    def persist_vectors(self, bundle: IngestionBundle) -> int:
        return self.add_records(bundle.vector_records)

    def search(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
        return _search(self.store, self.embedding_service, query)


def _precomputed_record(record: VectorRecord, vector: list[float], *, model_name: str) -> PrecomputedVectorRecord:
    metadata = dict(record.metadata)
    return PrecomputedVectorRecord(
        vector_id=record.vector_id,
        vector=vector,
        text=record.text,
        tenant_id=str(metadata["tenant_id"]),
        app_id=str(metadata["app_id"]),
        collection_id=str(metadata.get("collection_id") or "") or None,
        document_id=str(metadata["document_id"]),
        chunk_id=str(metadata.get("chunk_id") or record.vector_id),
        chunk_index=int(metadata.get("chunk_index") or 0),
        embedding_profile_id=None,
        embedding_model=model_name,
        metadata=metadata,
    )


def _search(store, embedding_service: TextEmbeddingService, query: VectorSearchQuery) -> list[VectorSearchResult]:
    matches = store.search(
        scope=VectorDatabaseScope(
            tenant_id=query.tenant_id,
            app_id=query.app_id,
            collection_id=query.collection_id,
        ),
        query_vector=embedding_service.embed_text(query.query),
        top_k=query.top_k,
        min_similarity=query.min_score,
    )
    return [
        VectorSearchResult(
            vector_id=match.vector_id,
            text=match.text,
            score=match.similarity,
            distance=match.distance,
            metadata=match.metadata,
        )
        for match in matches
    ]
