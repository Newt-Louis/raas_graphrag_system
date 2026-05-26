from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VectorDatabaseScope:
    tenant_id: str
    app_id: str
    collection_id: str | None = None


@dataclass(frozen=True)
class VectorDocumentChunk:
    text: str
    document_id: str
    chunk_id: str
    vector_id: str | None = None
    chunk_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorIngestRequest:
    scope: VectorDatabaseScope
    chunks: list[VectorDocumentChunk]
    embedding_profile_id: str | None = None
    expected_dim: int | None = None
    batch_size: int | None = None


@dataclass(frozen=True)
class VectorIngestResult:
    tenant_id: str
    app_id: str
    collection_id: str | None
    table_name: str
    embedded_count: int
    stored_count: int
    embedding_profile_id: str | None
    embedding_model: str | None
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorQueryRequest:
    scope: VectorDatabaseScope
    query: str
    top_k: int = 5
    min_similarity: float = 0.0
    embedding_profile_id: str | None = None
    expected_dim: int | None = None


@dataclass(frozen=True)
class VectorMatch:
    vector_id: str
    document_id: str
    chunk_id: str
    text: str
    similarity: float
    distance: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorQueryResult:
    query: str
    tenant_id: str
    app_id: str
    collection_id: str | None
    table_name: str
    matches: list[VectorMatch]
    embedding_profile_id: str | None
    embedding_model: str | None
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PrecomputedVectorRecord:
    vector_id: str
    vector: list[float]
    text: str
    tenant_id: str
    app_id: str
    collection_id: str | None
    document_id: str
    chunk_id: str
    chunk_index: int
    embedding_profile_id: str | None
    embedding_model: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
