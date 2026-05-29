from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class VisualizationScopeRequest(BaseModel):
    tenant_id: str = Field(default="tenant-a", min_length=1)
    app_id: str = Field(default="app-a", min_length=1)
    collection_id: str | None = None


class VectorSearchDebugRequest(VisualizationScopeRequest):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    min_similarity: float = Field(default=0.4, ge=0.0, le=1.0)
    embedding_profile_id: str | None = None
    expected_dim: int | None = Field(default=None, ge=1)


class VisualizeGraphElementContext(BaseModel):
    element_id: str
    element_type: str
    text: str
    order_index: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisualizeGraphChunkContext(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    chunk_index: int
    source_elements: list[VisualizeGraphElementContext] = Field(default_factory=list)
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
    parent_chunk_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorSearchDebugMatch(BaseModel):
    rank: int
    vector_id: str
    document_id: str
    chunk_id: str
    chunk_text: str
    similarity: float
    distance: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    graph_context: VisualizeGraphChunkContext | None = None


class VectorSearchDebugResponse(BaseModel):
    query: str
    tenant_id: str
    app_id: str
    collection_id: str | None = None
    vector_table: str
    embedding_profile_id: str | None = None
    embedding_model: str | None = None
    top_k: int
    min_similarity: float
    matches: list[VectorSearchDebugMatch]
    usage: dict[str, Any] = Field(default_factory=dict)


class VectorHealthRequest(VisualizationScopeRequest):
    document_id: str | None = None
    limit: int = Field(default=10_000, ge=1, le=100_000)


class VectorEmbeddingProfileHealthItem(BaseModel):
    document_id: str
    collection_id: str | None = None
    embedding_profile_id: str | None = None
    embedding_profile_name: str | None = None
    embedding_model: str | None = None
    expected_dimension: int | None = None
    vector_dimension: int | None = None
    dimension_status: str
    embedded_chunk_count: int
    graph_chunk_count: int | None = None
    graph_embeddable_chunk_count: int | None = None
    missing_embedding_count: int | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    last_indexed_at: datetime | None = None


class VectorEmbeddingProfileHealthResponse(BaseModel):
    tenant_id: str
    app_id: str
    collection_id: str | None = None
    vector_table: str
    checked_at: datetime
    total_embedded_chunks: int
    documents: list[VectorEmbeddingProfileHealthItem]
