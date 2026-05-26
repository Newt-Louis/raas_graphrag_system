from __future__ import annotations

import math

from app.graphrag.vector_database.models import (
    PrecomputedVectorRecord,
    VectorDatabaseScope,
    VectorMatch,
)


class InMemoryPrecomputedVectorStore:
    """Small precomputed-vector store for unit tests and local pipeline checks."""

    def __init__(self, table_name: str = "in_memory_vector_chunks", distance_metric: str = "cosine") -> None:
        self.table_name = table_name
        self.distance_metric = distance_metric
        self._records: dict[str, PrecomputedVectorRecord] = {}

    def add_records(self, records: list[PrecomputedVectorRecord]) -> int:
        for record in records:
            self._records[record.vector_id] = record
        return len(records)

    def search(
        self,
        *,
        scope: VectorDatabaseScope,
        query_vector: list[float],
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> list[VectorMatch]:
        matches: list[VectorMatch] = []
        for record in self._records.values():
            if record.tenant_id != scope.tenant_id or record.app_id != scope.app_id:
                continue
            if scope.collection_id and record.collection_id != scope.collection_id:
                continue
            similarity = _cosine_similarity(query_vector, record.vector)
            if similarity < min_similarity:
                continue
            matches.append(
                VectorMatch(
                    vector_id=record.vector_id,
                    document_id=record.document_id,
                    chunk_id=record.chunk_id,
                    text=record.text,
                    similarity=similarity,
                    distance=1.0 - similarity,
                    metadata=dict(record.metadata),
                )
            )
        matches.sort(key=lambda item: item.similarity, reverse=True)
        return matches[:top_k]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))
