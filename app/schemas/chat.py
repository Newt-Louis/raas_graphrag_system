from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings


class ChatRetrieveRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    app_id: str = Field(min_length=1)
    collection_id: str | None = None
    message: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default_factory=lambda: settings.RETRIEVAL_MIN_SCORE, ge=0.0, le=1.0)


class RetrievedContextResponse(BaseModel):
    source: str
    text: str
    score: float
    document_id: str
    chunk_id: str
    metadata: dict[str, Any]


class ChatRetrieveResponse(BaseModel):
    tenant_id: str
    app_id: str
    collection_id: str | None
    query: str
    strategy: str
    contexts: list[RetrievedContextResponse]
