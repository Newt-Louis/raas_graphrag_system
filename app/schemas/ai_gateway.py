from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AIProviderCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=255)
    provider_kind: str = Field(default="litellm", max_length=80)
    base_url: str | None = None
    auth_type: str = Field(default="api_key", max_length=50)
    is_enabled: bool = True
    is_locked: bool = False
    lock_reason: str | None = None
    default_headers: dict[str, Any] = Field(default_factory=dict)
    provider_config: dict[str, Any] = Field(default_factory=dict)


class AIProviderResponse(AIProviderCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class AIProviderUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    provider_kind: str | None = Field(default=None, max_length=80)
    base_url: str | None = None
    auth_type: str | None = Field(default=None, max_length=50)
    is_enabled: bool | None = None
    is_locked: bool | None = None
    lock_reason: str | None = None
    default_headers: dict[str, Any] | None = None
    provider_config: dict[str, Any] | None = None


class AIAPIKeyCreate(BaseModel):
    provider_id: UUID
    name: str = Field(min_length=1, max_length=255)
    api_key: str = Field(min_length=1)
    api_base: str | None = None
    endpoint_id: str | None = Field(default=None, max_length=120)
    allowed_capabilities: list[str] = Field(default_factory=list)
    status: str = Field(default="active", max_length=50)
    is_enabled: bool = True
    is_locked: bool = False
    lock_reason: str | None = None
    daily_quota_limit: int | None = Field(default=None, ge=0)
    minute_quota_limit: int | None = Field(default=None, ge=0)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AIAPIKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    name: str
    api_key_preview: str
    api_base: str | None
    endpoint_id: str | None
    allowed_capabilities: list[str]
    status: str
    is_enabled: bool
    is_locked: bool
    lock_reason: str | None
    daily_quota_limit: int | None
    minute_quota_limit: int | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AIAPIKeyStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|disabled|locked|cooldown)$")


class AIModelCatalogCreate(BaseModel):
    provider_id: UUID
    capability: str = Field(min_length=1, max_length=30)
    model_name: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    context_window: int | None = Field(default=None, ge=1)
    input_token_limit: int | None = Field(default=None, ge=1)
    output_token_limit: int | None = Field(default=None, ge=1)
    embedding_dimensions: int | None = Field(default=None, ge=1)
    supports_streaming: bool = False
    supports_tools: bool = False
    is_enabled: bool = True
    default_parameters: dict[str, Any] = Field(default_factory=dict)


class AIModelCatalogResponse(AIModelCatalogCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class LLMRotationPoolCreate(BaseModel):
    tenant_id: UUID | None = None
    app_id: UUID | None = None
    profile_id: UUID
    name: str = Field(default="default", min_length=1, max_length=120)
    is_default: bool = False
    is_enabled: bool = True
    current_position: int = Field(default=0, ge=0)
    rotation_order: int = Field(default=0, ge=0)
    weight: int = Field(default=1, ge=1)
    is_locked: bool = False
    lock_reason: str | None = None
    today_quota_exhausted: bool = False
    daily_request_count: int = Field(default=0, ge=0)
    minute_request_count: int = Field(default=0, ge=0)
    description: str | None = None


class LLMRotationPoolResponse(LLMRotationPoolCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class LLMModelProfileBase(BaseModel):
    pool_id: UUID | None = None
    provider_id: UUID
    api_key_id: UUID
    model_id: UUID | None = None
    profile_name: str = Field(min_length=1, max_length=255)
    model_name: str = Field(min_length=1, max_length=255)
    api_base: str | None = None
    endpoint_id: str | None = Field(default=None, max_length=120)
    rotation_order: int = Field(default=0, ge=0)
    weight: int = Field(default=1, ge=1)
    is_enabled: bool = True
    is_locked: bool = False
    lock_reason: str | None = None
    today_quota_exhausted: bool = False
    daily_request_count: int = Field(default=0, ge=0)
    minute_request_count: int = Field(default=0, ge=0)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    top_k: int | None = Field(default=None, ge=0)
    max_output_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: int = Field(default=120, ge=1)
    cost_per_1k_input_tokens: Decimal | None = Field(default=None, ge=0)
    cost_per_1k_output_tokens: Decimal | None = Field(default=None, ge=0)
    extra_parameters: dict[str, Any] = Field(default_factory=dict)


class LLMModelProfileCreate(LLMModelProfileBase):
    pass


class LLMModelProfileUpdate(BaseModel):
    pool_id: UUID | None = None
    provider_id: UUID | None = None
    api_key_id: UUID | None = None
    model_id: UUID | None = None
    profile_name: str | None = Field(default=None, min_length=1, max_length=255)
    model_name: str | None = Field(default=None, min_length=1, max_length=255)
    api_base: str | None = None
    endpoint_id: str | None = Field(default=None, max_length=120)
    rotation_order: int | None = Field(default=None, ge=0)
    weight: int | None = Field(default=None, ge=1)
    is_enabled: bool | None = None
    is_locked: bool | None = None
    lock_reason: str | None = None
    today_quota_exhausted: bool | None = None
    daily_request_count: int | None = Field(default=None, ge=0)
    minute_request_count: int | None = Field(default=None, ge=0)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    top_k: int | None = Field(default=None, ge=0)
    max_output_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: int | None = Field(default=None, ge=1)
    cost_per_1k_input_tokens: Decimal | None = Field(default=None, ge=0)
    cost_per_1k_output_tokens: Decimal | None = Field(default=None, ge=0)
    extra_parameters: dict[str, Any] | None = None


class LLMModelProfileResponse(LLMModelProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class EmbeddingRotationPoolCreate(BaseModel):
    tenant_id: UUID | None = None
    app_id: UUID | None = None
    profile_id: UUID
    name: str = Field(default="default", min_length=1, max_length=120)
    is_default: bool = False
    is_enabled: bool = True
    current_position: int = Field(default=0, ge=0)
    rotation_order: int = Field(default=0, ge=0)
    weight: int = Field(default=1, ge=1)
    is_locked: bool = False
    lock_reason: str | None = None
    today_quota_exhausted: bool = False
    daily_request_count: int = Field(default=0, ge=0)
    minute_request_count: int = Field(default=0, ge=0)
    description: str | None = None


class EmbeddingRotationPoolResponse(EmbeddingRotationPoolCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class EmbeddingModelProfileBase(BaseModel):
    pool_id: UUID | None = None
    provider_id: UUID
    api_key_id: UUID
    model_id: UUID | None = None
    profile_name: str = Field(min_length=1, max_length=255)
    model_name: str = Field(min_length=1, max_length=255)
    api_base: str | None = None
    endpoint_id: str | None = Field(default=None, max_length=120)
    rotation_order: int = Field(default=0, ge=0)
    weight: int = Field(default=1, ge=1)
    is_enabled: bool = True
    is_locked: bool = False
    lock_reason: str | None = None
    today_quota_exhausted: bool = False
    daily_request_count: int = Field(default=0, ge=0)
    minute_request_count: int = Field(default=0, ge=0)
    embedding_dimensions: int | None = Field(default=None, ge=1)
    batch_size: int | None = Field(default=None, ge=1)
    retrieval_top_k: int | None = Field(default=None, ge=1)
    timeout_seconds: int = Field(default=60, ge=1)
    cost_per_1k_tokens: Decimal | None = Field(default=None, ge=0)
    extra_parameters: dict[str, Any] = Field(default_factory=dict)


class EmbeddingModelProfileCreate(EmbeddingModelProfileBase):
    pass


class EmbeddingModelProfileUpdate(BaseModel):
    pool_id: UUID | None = None
    provider_id: UUID | None = None
    api_key_id: UUID | None = None
    model_id: UUID | None = None
    profile_name: str | None = Field(default=None, min_length=1, max_length=255)
    model_name: str | None = Field(default=None, min_length=1, max_length=255)
    api_base: str | None = None
    endpoint_id: str | None = Field(default=None, max_length=120)
    rotation_order: int | None = Field(default=None, ge=0)
    weight: int | None = Field(default=None, ge=1)
    is_enabled: bool | None = None
    is_locked: bool | None = None
    lock_reason: str | None = None
    today_quota_exhausted: bool | None = None
    daily_request_count: int | None = Field(default=None, ge=0)
    minute_request_count: int | None = Field(default=None, ge=0)
    embedding_dimensions: int | None = Field(default=None, ge=1)
    batch_size: int | None = Field(default=None, ge=1)
    retrieval_top_k: int | None = Field(default=None, ge=1)
    timeout_seconds: int | None = Field(default=None, ge=1)
    cost_per_1k_tokens: Decimal | None = Field(default=None, ge=0)
    extra_parameters: dict[str, Any] | None = None


class EmbeddingModelProfileResponse(EmbeddingModelProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
