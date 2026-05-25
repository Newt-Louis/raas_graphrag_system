"""make ai gateway rotation pools the runtime rows

Revision ID: 202605250001
Revises: 202605220001
Create Date: 2026-05-25 22:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202605250001"
down_revision: Union[str, None] = "202605220001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RUNTIME_COLUMNS = [
    "pool_id",
    "rotation_order",
    "weight",
    "is_enabled",
    "is_locked",
    "lock_reason",
    "today_quota_exhausted",
    "quota_exhausted_until",
    "rate_limited_until",
    "last_used_at",
    "daily_request_count",
    "minute_request_count",
    "success_count",
    "failure_count",
]


def upgrade() -> None:
    _upgrade_runtime_pool(
        pool_table="llm_rotation_pools",
        profile_table="llm_model_profiles",
        old_scope_unique="uq_llm_rotation_pools_scope_name",
        old_profile_order_unique="uq_llm_model_profiles_pool_order",
        old_profile_pool_fk="llm_model_profiles_pool_id_fkey",
        old_profile_pool_enabled_index="ix_llm_model_profiles_pool_enabled",
        old_profile_quota_index="ix_llm_model_profiles_quota_cooldown",
        profile_fk_name="llm_rotation_pools_profile_id_fkey",
        profile_unique_name="uq_llm_rotation_pools_profile",
        order_index_name="ix_llm_rotation_pools_order",
        current_index_name="ix_llm_rotation_pools_current",
        enabled_index_name="ix_llm_rotation_pools_enabled_locked",
        quota_index_name="ix_llm_rotation_pools_quota_cooldown",
    )
    _upgrade_runtime_pool(
        pool_table="embedding_rotation_pools",
        profile_table="embedding_model_profiles",
        old_scope_unique="uq_embedding_rotation_pools_scope_name",
        old_profile_order_unique="uq_embedding_model_profiles_pool_order",
        old_profile_pool_fk="embedding_model_profiles_pool_id_fkey",
        old_profile_pool_enabled_index="ix_embedding_model_profiles_pool_enabled",
        old_profile_quota_index="ix_embedding_model_profiles_quota_cooldown",
        profile_fk_name="embedding_rotation_pools_profile_id_fkey",
        profile_unique_name="uq_embedding_rotation_pools_profile",
        order_index_name="ix_embedding_rotation_pools_order",
        current_index_name="ix_embedding_rotation_pools_current",
        enabled_index_name="ix_embedding_rotation_pools_enabled_locked",
        quota_index_name="ix_embedding_rotation_pools_quota_cooldown",
    )


def downgrade() -> None:
    _downgrade_runtime_pool(
        pool_table="embedding_rotation_pools",
        profile_table="embedding_model_profiles",
        scope_unique="uq_embedding_rotation_pools_scope_name",
        profile_order_unique="uq_embedding_model_profiles_pool_order",
        profile_pool_fk="embedding_model_profiles_pool_id_fkey",
        profile_pool_enabled_index="ix_embedding_model_profiles_pool_enabled",
        profile_quota_index="ix_embedding_model_profiles_quota_cooldown",
        profile_fk_name="embedding_rotation_pools_profile_id_fkey",
        profile_unique_name="uq_embedding_rotation_pools_profile",
        order_index_name="ix_embedding_rotation_pools_order",
        current_index_name="ix_embedding_rotation_pools_current",
        enabled_index_name="ix_embedding_rotation_pools_enabled_locked",
        quota_index_name="ix_embedding_rotation_pools_quota_cooldown",
    )
    _downgrade_runtime_pool(
        pool_table="llm_rotation_pools",
        profile_table="llm_model_profiles",
        scope_unique="uq_llm_rotation_pools_scope_name",
        profile_order_unique="uq_llm_model_profiles_pool_order",
        profile_pool_fk="llm_model_profiles_pool_id_fkey",
        profile_pool_enabled_index="ix_llm_model_profiles_pool_enabled",
        profile_quota_index="ix_llm_model_profiles_quota_cooldown",
        profile_fk_name="llm_rotation_pools_profile_id_fkey",
        profile_unique_name="uq_llm_rotation_pools_profile",
        order_index_name="ix_llm_rotation_pools_order",
        current_index_name="ix_llm_rotation_pools_current",
        enabled_index_name="ix_llm_rotation_pools_enabled_locked",
        quota_index_name="ix_llm_rotation_pools_quota_cooldown",
    )


def _upgrade_runtime_pool(
    *,
    pool_table: str,
    profile_table: str,
    old_scope_unique: str,
    old_profile_order_unique: str,
    old_profile_pool_fk: str,
    old_profile_pool_enabled_index: str,
    old_profile_quota_index: str,
    profile_fk_name: str,
    profile_unique_name: str,
    order_index_name: str,
    current_index_name: str,
    enabled_index_name: str,
    quota_index_name: str,
) -> None:
    op.drop_constraint(old_scope_unique, pool_table, type_="unique")
    op.add_column(pool_table, sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(pool_table, sa.Column("rotation_order", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column(pool_table, sa.Column("weight", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.add_column(pool_table, sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column(pool_table, sa.Column("lock_reason", sa.Text(), nullable=True))
    op.add_column(pool_table, sa.Column("today_quota_exhausted", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column(pool_table, sa.Column("quota_exhausted_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(pool_table, sa.Column("rate_limited_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(pool_table, sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(pool_table, sa.Column("daily_request_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column(pool_table, sa.Column("minute_request_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column(pool_table, sa.Column("success_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column(pool_table, sa.Column("failure_count", sa.Integer(), nullable=False, server_default=sa.text("0")))

    op.execute(
        f"""
        INSERT INTO {pool_table} (
            id, tenant_id, app_id, profile_id, name, is_default, is_enabled,
            current_position, rotation_order, weight, is_locked, lock_reason,
            today_quota_exhausted, quota_exhausted_until, rate_limited_until,
            last_used_at, daily_request_count, minute_request_count,
            success_count, failure_count, description, created_at, updated_at
        )
        SELECT profile.id, old_pool.tenant_id, old_pool.app_id, profile.id,
               profile.profile_name, old_pool.is_default, profile.is_enabled,
               CASE WHEN old_pool.current_position = profile.rotation_order THEN 1 ELSE 0 END,
               profile.rotation_order, profile.weight, profile.is_locked, profile.lock_reason,
               profile.today_quota_exhausted, profile.quota_exhausted_until, profile.rate_limited_until,
               profile.last_used_at, profile.daily_request_count, profile.minute_request_count,
               profile.success_count, profile.failure_count, old_pool.description,
               profile.created_at, profile.updated_at
        FROM {profile_table} AS profile
        JOIN {pool_table} AS old_pool ON old_pool.id = profile.pool_id
        """
    )
    op.drop_index(old_profile_quota_index, table_name=profile_table)
    op.drop_index(old_profile_pool_enabled_index, table_name=profile_table)
    op.drop_constraint(old_profile_order_unique, profile_table, type_="unique")
    op.drop_constraint(old_profile_pool_fk, profile_table, type_="foreignkey")
    for column_name in RUNTIME_COLUMNS:
        op.drop_column(profile_table, column_name)

    op.execute(f"DELETE FROM {pool_table} WHERE profile_id IS NULL")
    op.alter_column(pool_table, "profile_id", nullable=False)

    op.create_foreign_key(profile_fk_name, pool_table, profile_table, ["profile_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint(profile_unique_name, pool_table, ["profile_id"])
    op.create_index(order_index_name, pool_table, ["rotation_order"])
    op.create_index(current_index_name, pool_table, ["current_position"])
    op.create_index(enabled_index_name, pool_table, ["is_enabled", "is_locked"])
    op.create_index(quota_index_name, pool_table, ["today_quota_exhausted", "rate_limited_until"])


def _downgrade_runtime_pool(
    *,
    pool_table: str,
    profile_table: str,
    scope_unique: str,
    profile_order_unique: str,
    profile_pool_fk: str,
    profile_pool_enabled_index: str,
    profile_quota_index: str,
    profile_fk_name: str,
    profile_unique_name: str,
    order_index_name: str,
    current_index_name: str,
    enabled_index_name: str,
    quota_index_name: str,
) -> None:
    op.add_column(profile_table, sa.Column("pool_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(profile_table, sa.Column("rotation_order", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column(profile_table, sa.Column("weight", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.add_column(profile_table, sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column(profile_table, sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column(profile_table, sa.Column("lock_reason", sa.Text(), nullable=True))
    op.add_column(profile_table, sa.Column("today_quota_exhausted", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column(profile_table, sa.Column("quota_exhausted_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(profile_table, sa.Column("rate_limited_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(profile_table, sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(profile_table, sa.Column("daily_request_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column(profile_table, sa.Column("minute_request_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column(profile_table, sa.Column("success_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column(profile_table, sa.Column("failure_count", sa.Integer(), nullable=False, server_default=sa.text("0")))

    op.execute(
        f"""
        UPDATE {profile_table} AS profile
        SET pool_id = pool.id,
            rotation_order = pool.rotation_order,
            weight = pool.weight,
            is_enabled = pool.is_enabled,
            is_locked = pool.is_locked,
            lock_reason = pool.lock_reason,
            today_quota_exhausted = pool.today_quota_exhausted,
            quota_exhausted_until = pool.quota_exhausted_until,
            rate_limited_until = pool.rate_limited_until,
            last_used_at = pool.last_used_at,
            daily_request_count = pool.daily_request_count,
            minute_request_count = pool.minute_request_count,
            success_count = pool.success_count,
            failure_count = pool.failure_count
        FROM {pool_table} AS pool
        WHERE profile.id = pool.profile_id
        """
    )
    op.alter_column(profile_table, "pool_id", nullable=False)

    op.drop_index(quota_index_name, table_name=pool_table)
    op.drop_index(enabled_index_name, table_name=pool_table)
    op.drop_index(current_index_name, table_name=pool_table)
    op.drop_index(order_index_name, table_name=pool_table)
    op.drop_constraint(profile_unique_name, pool_table, type_="unique")
    op.drop_constraint(profile_fk_name, pool_table, type_="foreignkey")

    op.create_foreign_key(profile_pool_fk, profile_table, pool_table, ["pool_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint(profile_order_unique, profile_table, ["pool_id", "rotation_order"])
    op.create_index(profile_pool_enabled_index, profile_table, ["pool_id", "is_enabled", "is_locked"])
    op.create_index(profile_quota_index, profile_table, ["today_quota_exhausted", "rate_limited_until"])

    for column_name in reversed(RUNTIME_COLUMNS[1:]):
        op.drop_column(pool_table, column_name)
    op.drop_column(pool_table, "profile_id")
    op.create_unique_constraint(scope_unique, pool_table, ["tenant_id", "app_id", "name"])
