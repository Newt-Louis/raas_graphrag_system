from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.graphrag.vector_database.models import (
    PrecomputedVectorRecord,
    VectorDatabaseScope,
    VectorMatch,
    VectorStoredRecord,
)


class LanceDBPrecomputedVectorStore:
    """LanceDB adapter for vectors already produced by the embedding gateway."""

    def __init__(self, db_path: Path, table_name: str, distance_metric: str = "cosine") -> None:
        self.db_path = db_path
        self.table_name = table_name
        self.distance_metric = distance_metric.lower()

    def add_records(self, records: list[PrecomputedVectorRecord]) -> int:
        if not records:
            return 0

        rows = [self._row_for_record(record) for record in records]
        connection = self._connection()
        if self.table_name not in set(connection.table_names(limit=10_000)):
            connection.create_table(self.table_name, data=rows)
            return len(rows)

        table = connection.open_table(self.table_name)
        for row in rows:
            table.delete(f"vector_id = {_sql_literal(row['vector_id'])}")
        table.add(rows)
        return len(rows)

    def search(
        self,
        *,
        scope: VectorDatabaseScope,
        query_vector: list[float],
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> list[VectorMatch]:
        connection = self._connection()
        if self.table_name not in set(connection.table_names(limit=10_000)):
            return []

        table = connection.open_table(self.table_name)
        builder = (
            table.search(query_vector, vector_column_name="vector", query_type="vector")
            .metric(self.distance_metric)
            .where(self._scope_filter(scope), prefilter=True)
            .limit(top_k)
        )

        matches: list[VectorMatch] = []
        for row in builder.to_list():
            distance = float(row.get("_distance", 0.0))
            similarity = _similarity_from_distance(distance, self.distance_metric)
            if similarity < min_similarity:
                continue
            matches.append(
                VectorMatch(
                    vector_id=str(row["vector_id"]),
                    document_id=str(row["document_id"]),
                    chunk_id=str(row["chunk_id"]),
                    text=str(row["text"]),
                    similarity=similarity,
                    distance=distance,
                    metadata=_decode_metadata(row.get("metadata_json")),
                )
            )
        return matches

    def list_records(
        self,
        *,
        scope: VectorDatabaseScope,
        document_id: str | None = None,
        limit: int = 10_000,
    ) -> list[VectorStoredRecord]:
        connection = self._connection()
        if self.table_name not in set(connection.table_names(limit=10_000)):
            return []

        filters = [self._scope_filter(scope)]
        if document_id:
            filters.append(f"document_id = {_sql_literal(document_id)}")

        table = connection.open_table(self.table_name)
        rows = (
            table.search(None)
            .where(" AND ".join(filters), prefilter=True)
            .select(
                [
                    "vector",
                    "vector_id",
                    "document_id",
                    "chunk_id",
                    "chunk_index",
                    "text",
                    "embedding_profile_id",
                    "embedding_model",
                    "metadata_json",
                ]
            )
            .limit(max(1, limit))
            .to_list()
        )

        return [
            VectorStoredRecord(
                vector_id=str(row["vector_id"]),
                document_id=str(row["document_id"]),
                chunk_id=str(row["chunk_id"]),
                chunk_index=int(row.get("chunk_index") or 0),
                text=str(row.get("text") or ""),
                embedding_profile_id=_optional_string(row.get("embedding_profile_id")),
                embedding_model=_optional_string(row.get("embedding_model")),
                vector_dimension=_vector_dimension(row.get("vector")),
                metadata=_decode_metadata(row.get("metadata_json")),
            )
            for row in rows
        ]

    def delete_document(self, *, scope: VectorDatabaseScope, document_id: str) -> int:
        connection = self._connection()
        if self.table_name not in set(connection.table_names(limit=10_000)):
            return 0

        filters = [
            self._scope_filter(scope),
            f"document_id = {_sql_literal(document_id)}",
        ]
        table = connection.open_table(self.table_name)
        matching_records = (
            table.search(None)
            .where(" AND ".join(filters), prefilter=True)
            .select(["vector_id"])
            .limit(100_000)
            .to_list()
        )
        if matching_records:
            table.delete(" AND ".join(filters))
        return len(matching_records)

    def _connection(self):
        try:
            import lancedb

            self.db_path.mkdir(parents=True, exist_ok=True)
            return lancedb.connect(str(self.db_path))
        except Exception as exc:
            raise RuntimeError(f"Vector database is unavailable at {self.db_path}.") from exc

    def _row_for_record(self, record: PrecomputedVectorRecord) -> dict[str, Any]:
        metadata = {
            **record.metadata,
            "tenant_id": record.tenant_id,
            "app_id": record.app_id,
            "collection_id": record.collection_id,
            "document_id": record.document_id,
            "chunk_id": record.chunk_id,
            "chunk_index": record.chunk_index,
            "embedding_profile_id": record.embedding_profile_id,
            "embedding_model": record.embedding_model,
        }
        return {
            "vector": record.vector,
            "vector_id": record.vector_id,
            "tenant_id": record.tenant_id,
            "app_id": record.app_id,
            "collection_id": record.collection_id or "",
            "document_id": record.document_id,
            "chunk_id": record.chunk_id,
            "chunk_index": record.chunk_index,
            "text": record.text,
            "embedding_profile_id": record.embedding_profile_id or "",
            "embedding_model": record.embedding_model or "",
            "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        }

    def _scope_filter(self, scope: VectorDatabaseScope) -> str:
        clauses = [
            f"tenant_id = {_sql_literal(scope.tenant_id)}",
            f"app_id = {_sql_literal(scope.app_id)}",
        ]
        if scope.collection_id:
            clauses.append(f"collection_id = {_sql_literal(scope.collection_id)}")
        return " AND ".join(clauses)


def _decode_metadata(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        decoded = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _optional_string(raw: Any) -> str | None:
    value = str(raw or "").strip()
    return value or None


def _vector_dimension(raw: Any) -> int | None:
    if raw is None:
        return None
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    try:
        return len(raw)
    except TypeError:
        return None


def _similarity_from_distance(distance: float, metric: str) -> float:
    if metric == "cosine":
        return max(0.0, min(1.0, 1.0 - distance))
    return 1.0 / (1.0 + max(0.0, distance))


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
