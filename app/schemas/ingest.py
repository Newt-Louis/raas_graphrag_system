from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.services.ingestion.models import ChunkStrategy


class DocumentIngestResponse(BaseModel):
    status: str = Field(examples=["ready"])
    tenant_id: str
    app_id: str
    collection_id: str | None = None
    document_id: str
    filename: str
    extension: str
    sha256: str
    chunk_strategy: ChunkStrategy
    stats: dict[str, int]
    feed_targets: list[str] = Field(default_factory=lambda: ["graph", "vector"])
    embedding_profile_id: str | None = None
    embedding_model: str | None = None
    vector_table: str | None = None
    vector_stored_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SupportedFormatsResponse(BaseModel):
    allowed_extensions: list[str]
    blocked_image_extensions: list[str]


class VectorDatabaseQueryRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    app_id: str = Field(min_length=1)
    collection_id: str | None = None
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    embedding_profile_id: str | None = None
    expected_dim: int | None = Field(default=None, ge=1)


class VectorDatabaseMatchResponse(BaseModel):
    vector_id: str
    document_id: str
    chunk_id: str
    text: str
    similarity: float
    distance: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorDatabaseQueryResponse(BaseModel):
    query: str
    tenant_id: str
    app_id: str
    collection_id: str | None = None
    vector_table: str
    embedding_profile_id: str | None = None
    embedding_model: str | None = None
    matches: list[VectorDatabaseMatchResponse]
    usage: dict[str, Any] = Field(default_factory=dict)
