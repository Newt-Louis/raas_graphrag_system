from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class AIProvider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_providers"

    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_kind: Mapped[str] = mapped_column(String(80), nullable=False, default="litellm")
    base_url: Mapped[str | None] = mapped_column(Text)
    auth_type: Mapped[str] = mapped_column(String(50), nullable=False, default="api_key")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lock_reason: Mapped[str | None] = mapped_column(Text)
    default_headers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    provider_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    api_keys: Mapped[list["AIAPIKey"]] = relationship(back_populates="provider")
    models: Mapped[list["AIModelCatalog"]] = relationship(back_populates="provider")


class AIAPIKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_api_keys"
    __table_args__ = (
        Index("ix_ai_api_keys_provider_status", "provider_id", "status"),
        Index("ix_ai_api_keys_enabled_locked", "is_enabled", "is_locked"),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_providers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    api_base: Mapped[str | None] = mapped_column(Text)
    endpoint_id: Mapped[str | None] = mapped_column(String(120))
    allowed_capabilities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lock_reason: Mapped[str | None] = mapped_column(Text)
    daily_quota_limit: Mapped[int | None] = mapped_column(Integer)
    minute_quota_limit: Mapped[int | None] = mapped_column(Integer)
    quota_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    provider: Mapped[AIProvider] = relationship(back_populates="api_keys")


class AIModelCatalog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_model_catalog"
    __table_args__ = (
        UniqueConstraint("provider_id", "capability", "model_name", name="uq_ai_model_catalog_provider_capability_model"),
        Index("ix_ai_model_catalog_capability_enabled", "capability", "is_enabled"),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    capability: Mapped[str] = mapped_column(String(30), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    context_window: Mapped[int | None] = mapped_column(Integer)
    input_token_limit: Mapped[int | None] = mapped_column(Integer)
    output_token_limit: Mapped[int | None] = mapped_column(Integer)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_tools: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    provider: Mapped[AIProvider] = relationship(back_populates="models")


class LLMRotationPool(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "llm_rotation_pools"
    __table_args__ = (
        UniqueConstraint("profile_id", name="uq_llm_rotation_pools_profile"),
        Index("ix_llm_rotation_pools_scope_default", "tenant_id", "app_id", "is_default"),
        Index("ix_llm_rotation_pools_order", "rotation_order"),
        Index("ix_llm_rotation_pools_current", "current_position"),
        Index("ix_llm_rotation_pools_enabled_locked", "is_enabled", "is_locked"),
        Index("ix_llm_rotation_pools_quota_cooldown", "today_quota_exhausted", "rate_limited_until"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"))
    app_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_apps.id", ondelete="CASCADE"))
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("llm_model_profiles.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="default")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    current_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rotation_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lock_reason: Mapped[str | None] = mapped_column(Text)
    today_quota_exhausted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quota_exhausted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rate_limited_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    daily_request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minute_request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text)

    profile: Mapped["LLMModelProfile"] = relationship(back_populates="pool_state")


class LLMModelProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "llm_model_profiles"

    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_providers.id", ondelete="RESTRICT"), nullable=False)
    api_key_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_api_keys.id", ondelete="RESTRICT"), nullable=False)
    model_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_model_catalog.id", ondelete="SET NULL"))
    profile_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_base: Mapped[str | None] = mapped_column(Text)
    endpoint_id: Mapped[str | None] = mapped_column(String(120))
    temperature: Mapped[float | None] = mapped_column(Float)
    top_p: Mapped[float | None] = mapped_column(Float)
    top_k: Mapped[int | None] = mapped_column(Integer)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    cost_per_1k_input_tokens: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    cost_per_1k_output_tokens: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    extra_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    pool_state: Mapped["LLMRotationPool | None"] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        single_parent=True,
    )


class EmbeddingRotationPool(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "embedding_rotation_pools"
    __table_args__ = (
        UniqueConstraint("profile_id", name="uq_embedding_rotation_pools_profile"),
        Index("ix_embedding_rotation_pools_scope_default", "tenant_id", "app_id", "is_default"),
        Index("ix_embedding_rotation_pools_order", "rotation_order"),
        Index("ix_embedding_rotation_pools_current", "current_position"),
        Index("ix_embedding_rotation_pools_enabled_locked", "is_enabled", "is_locked"),
        Index("ix_embedding_rotation_pools_quota_cooldown", "today_quota_exhausted", "rate_limited_until"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"))
    app_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_apps.id", ondelete="CASCADE"))
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("embedding_model_profiles.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="default")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    current_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rotation_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lock_reason: Mapped[str | None] = mapped_column(Text)
    today_quota_exhausted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quota_exhausted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rate_limited_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    daily_request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minute_request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text)

    profile: Mapped["EmbeddingModelProfile"] = relationship(back_populates="pool_state")


class EmbeddingModelProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "embedding_model_profiles"

    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_providers.id", ondelete="RESTRICT"), nullable=False)
    api_key_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_api_keys.id", ondelete="RESTRICT"), nullable=False)
    model_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_model_catalog.id", ondelete="SET NULL"))
    profile_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_base: Mapped[str | None] = mapped_column(Text)
    endpoint_id: Mapped[str | None] = mapped_column(String(120))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    batch_size: Mapped[int | None] = mapped_column(Integer)
    retrieval_top_k: Mapped[int | None] = mapped_column(Integer)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    cost_per_1k_tokens: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    extra_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    pool_state: Mapped["EmbeddingRotationPool | None"] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        single_parent=True,
    )


class AIUsageEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_usage_events"
    __table_args__ = (
        Index("ix_ai_usage_events_scope_created", "tenant_id", "app_id", "created_at"),
        Index("ix_ai_usage_events_profile_created", "capability", "profile_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"))
    app_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_apps.id", ondelete="SET NULL"))
    profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    provider_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_providers.id", ondelete="SET NULL"))
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_api_keys.id", ondelete="SET NULL"))
    capability: Mapped[str] = mapped_column(String(30), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(255))
    endpoint: Mapped[str | None] = mapped_column(String(255))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    input_count: Mapped[int | None] = mapped_column(Integer)
    verdict_action: Mapped[str | None] = mapped_column(String(80))
    error_reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
