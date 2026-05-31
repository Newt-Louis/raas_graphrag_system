"""drop embedding rotation pools

Revision ID: 202605310001
Revises: 0802b55c4dc8
Create Date: 2026-05-31 21:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202605310001"
down_revision: Union[str, None] = "0802b55c4dc8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("embedding_rotation_pools")


def downgrade() -> None:
    op.create_table(
        "embedding_rotation_pools",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("current_position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rotation_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("weight", sa.Integer(), nullable=False, server_default=sa.text("1")),
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
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["app_id"], ["customer_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["embedding_model_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", name="uq_embedding_rotation_pools_profile"),
    )
    op.create_index(
        "ix_embedding_rotation_pools_scope_default",
        "embedding_rotation_pools",
        ["tenant_id", "app_id", "is_default"],
    )
    op.create_index("ix_embedding_rotation_pools_order", "embedding_rotation_pools", ["rotation_order"])
    op.create_index("ix_embedding_rotation_pools_current", "embedding_rotation_pools", ["current_position"])
    op.create_index(
        "ix_embedding_rotation_pools_enabled_locked",
        "embedding_rotation_pools",
        ["is_enabled", "is_locked"],
    )
    op.create_index(
        "ix_embedding_rotation_pools_quota_cooldown",
        "embedding_rotation_pools",
        ["today_quota_exhausted", "rate_limited_until"],
    )
