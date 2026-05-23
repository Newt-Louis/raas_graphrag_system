from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TestAPIAIKeyRequest(BaseModel):
    model_name: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=512, ge=1, le=8192)


class TestAPIAIKeyResponse(BaseModel):
    success: bool
    model_name: str
    response_text: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
