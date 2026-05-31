from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    extension: str
    content_type: str | None = None
    byte_size: int
    sha256: str
    status: str
    chunk_count: int
    vector_record_count: int
    graph_record_count: int
    last_indexed_at: datetime | None = None
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class DocumentDeleteResponse(BaseModel):
    document_id: str
    deleted_vector_count: int
    deleted_graph_count: int
