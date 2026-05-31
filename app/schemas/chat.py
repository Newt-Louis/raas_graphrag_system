from __future__ import annotations

from typing import Any, Literal

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


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8_000)


class ChatCompletionRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    app_id: str = Field(min_length=1)
    collection_id: str | None = None
    session_id: str | None = Field(default=None, max_length=255)
    message: str = Field(min_length=1, max_length=8_000)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=12)
    top_k: int = Field(default=5, ge=1, le=10)
    min_similarity: float = Field(default=0.4, ge=0.0, le=1.0)


class ChatCitationResponse(BaseModel):
    reference: int
    source: str
    document_id: str
    chunk_id: str
    filename: str | None = None
    similarity: float | None = None
    excerpt: str


class ChatCompletionResponse(BaseModel):
    tenant_id: str
    app_id: str
    collection_id: str | None = None
    session_id: str | None = None
    answer: str
    strategy: str
    citations: list[ChatCitationResponse] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
