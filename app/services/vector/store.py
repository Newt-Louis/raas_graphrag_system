from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

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
    def __init__(
        self,
        db_path: Path,
        table_name: str,
        embedding_service: TextEmbeddingService,
        distance_metric: str = "cosine",
    ) -> None:
        self.db_path = db_path
        self.table_name = table_name
        self.embedding_service = embedding_service
        self.distance_metric = distance_metric.lower()

    def persist_vectors(self, bundle: IngestionBundle) -> int:
        return self.add_records(bundle.vector_records)

    def add_records(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0

        rows = self._rows_for_records(records)
        connection = self._connection()
        if self.table_name not in set(connection.table_names(limit=10_000)):
            connection.create_table(self.table_name, data=rows)
            return len(rows)

        table = connection.open_table(self.table_name)
        for row in rows:
            table.delete(f"vector_id = {_sql_literal(row['vector_id'])}")
        table.add(rows)
        return len(rows)

    def search(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
        connection = self._connection()
        if self.table_name not in set(connection.table_names(limit=10_000)):
            return []

        query_vector = self.embedding_service.embed_text(query.query)
        table = connection.open_table(self.table_name)
        builder = (
            table.search(query_vector, vector_column_name="vector", query_type="vector")
            .metric(self.distance_metric)
            .where(self._scope_filter(query), prefilter=True)
            .limit(query.top_k)
        )

        results: list[VectorSearchResult] = []
        for row in builder.to_list():
            distance = float(row.get("_distance", 0.0))
            score = self._score_from_distance(distance)
            if score < query.min_score:
                continue
            metadata = _decode_metadata(row.get("metadata_json"))
            results.append(
                VectorSearchResult(
                    vector_id=str(row["vector_id"]),
                    text=str(row["text"]),
                    score=score,
                    distance=distance,
                    metadata=metadata,
                )
            )
        return results

    def _connection(self):
        try:
            import lancedb

            self.db_path.mkdir(parents=True, exist_ok=True)
            return lancedb.connect(str(self.db_path))
        except Exception as exc:
            raise RuntimeError(f"Vector database is unavailable at {self.db_path}.") from exc

    def _rows_for_records(self, records: list[VectorRecord]) -> list[dict[str, Any]]:
        vectors = self.embedding_service.embed_batch([record.text for record in records])
        rows: list[dict[str, Any]] = []
        for record, vector in zip(records, vectors, strict=True):
            metadata = dict(record.metadata)
            rows.append(
                {
                    "vector": vector,
                    "vector_id": record.vector_id,
                    "tenant_id": str(metadata["tenant_id"]),
                    "app_id": str(metadata["app_id"]),
                    "collection_id": str(metadata.get("collection_id") or ""),
                    "document_id": str(metadata["document_id"]),
                    "chunk_id": str(metadata["chunk_id"]),
                    "parent_chunk_id": str(metadata.get("parent_chunk_id") or ""),
                    "content_hash": str(metadata.get("content_hash") or ""),
                    "text": record.text,
                    "embedding_model": self.embedding_service.model_name,
                    "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                }
            )
        return rows

    def _scope_filter(self, query: VectorSearchQuery) -> str:
        clauses = [
            f"tenant_id = {_sql_literal(query.tenant_id)}",
            f"app_id = {_sql_literal(query.app_id)}",
        ]
        if query.collection_id:
            clauses.append(f"collection_id = {_sql_literal(query.collection_id)}")
        return " AND ".join(clauses)

    def _score_from_distance(self, distance: float) -> float:
        if self.distance_metric == "cosine":
            return max(0.0, min(1.0, 1.0 - distance))
        return 1.0 / (1.0 + max(0.0, distance))


class InMemoryVectorStore:
    def __init__(self, embedding_service: TextEmbeddingService) -> None:
        self.embedding_service = embedding_service
        self._rows: dict[str, dict[str, Any]] = {}

    def add_records(self, records: list[VectorRecord]) -> int:
        vectors = self.embedding_service.embed_batch([record.text for record in records])
        for record, vector in zip(records, vectors, strict=True):
            metadata = dict(record.metadata)
            self._rows[record.vector_id] = {
                "vector": vector,
                "vector_id": record.vector_id,
                "text": record.text,
                "metadata": metadata,
            }
        return len(records)

    def persist_vectors(self, bundle: IngestionBundle) -> int:
        return self.add_records(bundle.vector_records)

    def search(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
        query_vector = self.embedding_service.embed_text(query.query)
        results: list[VectorSearchResult] = []
        for row in self._rows.values():
            metadata = row["metadata"]
            if metadata.get("tenant_id") != query.tenant_id or metadata.get("app_id") != query.app_id:
                continue
            if query.collection_id and metadata.get("collection_id") != query.collection_id:
                continue
            score = _dot(query_vector, row["vector"])
            if score < query.min_score:
                continue
            results.append(
                VectorSearchResult(
                    vector_id=row["vector_id"],
                    text=row["text"],
                    score=score,
                    distance=1.0 - score,
                    metadata=dict(metadata),
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return results[: query.top_k]


def _decode_metadata(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        decoded = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
