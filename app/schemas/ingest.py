from __future__ import annotations

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
    warnings: list[str] = Field(default_factory=list)


class SupportedFormatsResponse(BaseModel):
    allowed_extensions: list[str]
    blocked_image_extensions: list[str]
