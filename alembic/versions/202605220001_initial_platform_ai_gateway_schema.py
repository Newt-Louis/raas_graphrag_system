"""initial platform and ai gateway schema

Revision ID: 202605220001
Revises:
Create Date: 2026-05-22 00:01:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202605220001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def _uuid_pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "platform_users",
        _uuid_pk(),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_platform_users_email", "platform_users", ["email"])

    op.create_table(
        "tenants",
        _uuid_pk(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    op.create_table(
        "customer_apps",
        _uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("allowed_origins", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("widget_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_customer_apps_tenant_slug"),
    )
    op.create_index("ix_customer_apps_tenant_status", "customer_apps", ["tenant_id", "status"])

    op.create_table(
        "ai_providers",
        _uuid_pk(),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("provider_kind", sa.String(length=80), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("auth_type", sa.String(length=50), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("lock_reason", sa.Text(), nullable=True),
        sa.Column("default_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("provider_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_ai_providers_code", "ai_providers", ["code"])

    op.create_table(
        "ai_api_keys",
        _uuid_pk(),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.String(length=255), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("api_base", sa.Text(), nullable=True),
        sa.Column("endpoint_id", sa.String(length=120), nullable=True),
        sa.Column("allowed_capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("lock_reason", sa.Text(), nullable=True),
        sa.Column("daily_quota_limit", sa.Integer(), nullable=True),
        sa.Column("minute_quota_limit", sa.Integer(), nullable=True),
        sa.Column("quota_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_providers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("ix_ai_api_keys_enabled_locked", "ai_api_keys", ["is_enabled", "is_locked"])
    op.create_index("ix_ai_api_keys_provider_status", "ai_api_keys", ["provider_id", "status"])

    op.create_table(
        "ai_model_catalog",
        _uuid_pk(),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability", sa.String(length=30), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("input_token_limit", sa.Integer(), nullable=True),
        sa.Column("output_token_limit", sa.Integer(), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("supports_streaming", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("supports_tools", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("default_parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "capability", "model_name", name="uq_ai_model_catalog_provider_capability_model"),
    )
    op.create_index("ix_ai_model_catalog_capability_enabled", "ai_model_catalog", ["capability", "is_enabled"])

    op.create_table(
        "llm_rotation_pools",
        _uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("current_position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["app_id"], ["customer_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "app_id", "name", name="uq_llm_rotation_pools_scope_name"),
    )
    op.create_index("ix_llm_rotation_pools_scope_default", "llm_rotation_pools", ["tenant_id", "app_id", "is_default"])

    op.create_table(
        "embedding_rotation_pools",
        _uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("current_position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["app_id"], ["customer_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "app_id", "name", name="uq_embedding_rotation_pools_scope_name"),
    )
    op.create_index("ix_embedding_rotation_pools_scope_default", "embedding_rotation_pools", ["tenant_id", "app_id", "is_default"])

    op.create_table(
        "llm_model_profiles",
        _uuid_pk(),
        sa.Column("pool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("profile_name", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("api_base", sa.Text(), nullable=True),
        sa.Column("endpoint_id", sa.String(length=120), nullable=True),
        sa.Column("rotation_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("weight", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("lock_reason", sa.Text(), nullable=True),
        sa.Column("today_quota_exhausted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("quota_exhausted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rate_limited_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("daily_request_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("minute_request_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("top_p", sa.Float(), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("120")),
        sa.Column("cost_per_1k_input_tokens", sa.Numeric(12, 8), nullable=True),
        sa.Column("cost_per_1k_output_tokens", sa.Numeric(12, 8), nullable=True),
        sa.Column("extra_parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.ForeignKeyConstraint(["api_key_id"], ["ai_api_keys.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_id"], ["ai_model_catalog.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pool_id"], ["llm_rotation_pools.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_providers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pool_id", "rotation_order", name="uq_llm_model_profiles_pool_order"),
    )
    op.create_index("ix_llm_model_profiles_pool_enabled", "llm_model_profiles", ["pool_id", "is_enabled", "is_locked"])
    op.create_index("ix_llm_model_profiles_quota_cooldown", "llm_model_profiles", ["today_quota_exhausted", "rate_limited_until"])

    op.create_table(
        "embedding_model_profiles",
        _uuid_pk(),
        sa.Column("pool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("profile_name", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("api_base", sa.Text(), nullable=True),
        sa.Column("endpoint_id", sa.String(length=120), nullable=True),
        sa.Column("rotation_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("weight", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("lock_reason", sa.Text(), nullable=True),
        sa.Column("today_quota_exhausted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("quota_exhausted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rate_limited_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("daily_request_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("minute_request_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("batch_size", sa.Integer(), nullable=True),
        sa.Column("retrieval_top_k", sa.Integer(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("cost_per_1k_tokens", sa.Numeric(12, 8), nullable=True),
        sa.Column("extra_parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.ForeignKeyConstraint(["api_key_id"], ["ai_api_keys.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_id"], ["ai_model_catalog.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pool_id"], ["embedding_rotation_pools.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_providers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pool_id", "rotation_order", name="uq_embedding_model_profiles_pool_order"),
    )
    op.create_index("ix_embedding_model_profiles_pool_enabled", "embedding_model_profiles", ["pool_id", "is_enabled", "is_locked"])
    op.create_index("ix_embedding_model_profiles_quota_cooldown", "embedding_model_profiles", ["today_quota_exhausted", "rate_limited_until"])

    op.create_table(
        "documents",
        _uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", sa.String(length=120), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("extension", sa.String(length=32), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("vector_record_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("graph_record_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.ForeignKeyConstraint(["app_id"], ["customer_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "app_id", "sha256", name="uq_documents_scope_sha256"),
    )
    op.create_index("ix_documents_scope_status", "documents", ["tenant_id", "app_id", "status"])

    op.create_table(
        "document_ingestion_jobs",
        _uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("current_step", sa.String(length=80), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.ForeignKeyConstraint(["app_id"], ["customer_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_ingestion_jobs_document", "document_ingestion_jobs", ["document_id"])
    op.create_index("ix_document_ingestion_jobs_scope_status", "document_ingestion_jobs", ["tenant_id", "app_id", "status"])

    op.create_table(
        "ai_usage_events",
        _uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capability", sa.String(length=30), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("endpoint", sa.String(length=255), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("input_count", sa.Integer(), nullable=True),
        sa.Column("verdict_action", sa.String(length=80), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_timestamps(),
        sa.ForeignKeyConstraint(["api_key_id"], ["ai_api_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["app_id"], ["customer_apps.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_providers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_events_profile_created", "ai_usage_events", ["capability", "profile_id", "created_at"])
    op.create_index("ix_ai_usage_events_scope_created", "ai_usage_events", ["tenant_id", "app_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_events_scope_created", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_profile_created", table_name="ai_usage_events")
    op.drop_table("ai_usage_events")

    op.drop_index("ix_document_ingestion_jobs_scope_status", table_name="document_ingestion_jobs")
    op.drop_index("ix_document_ingestion_jobs_document", table_name="document_ingestion_jobs")
    op.drop_table("document_ingestion_jobs")

    op.drop_index("ix_documents_scope_status", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_embedding_model_profiles_quota_cooldown", table_name="embedding_model_profiles")
    op.drop_index("ix_embedding_model_profiles_pool_enabled", table_name="embedding_model_profiles")
    op.drop_table("embedding_model_profiles")

    op.drop_index("ix_llm_model_profiles_quota_cooldown", table_name="llm_model_profiles")
    op.drop_index("ix_llm_model_profiles_pool_enabled", table_name="llm_model_profiles")
    op.drop_table("llm_model_profiles")

    op.drop_index("ix_embedding_rotation_pools_scope_default", table_name="embedding_rotation_pools")
    op.drop_table("embedding_rotation_pools")

    op.drop_index("ix_llm_rotation_pools_scope_default", table_name="llm_rotation_pools")
    op.drop_table("llm_rotation_pools")

    op.drop_index("ix_ai_model_catalog_capability_enabled", table_name="ai_model_catalog")
    op.drop_table("ai_model_catalog")

    op.drop_index("ix_ai_api_keys_provider_status", table_name="ai_api_keys")
    op.drop_index("ix_ai_api_keys_enabled_locked", table_name="ai_api_keys")
    op.drop_table("ai_api_keys")

    op.drop_index("ix_ai_providers_code", table_name="ai_providers")
    op.drop_table("ai_providers")

    op.drop_index("ix_customer_apps_tenant_status", table_name="customer_apps")
    op.drop_table("customer_apps")

    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")

    op.drop_index("ix_platform_users_email", table_name="platform_users")
    op.drop_table("platform_users")
