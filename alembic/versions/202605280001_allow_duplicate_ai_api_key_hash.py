"""allow duplicate provider api key hashes

Revision ID: 202605280001
Revises: 202605250001
Create Date: 2026-05-28 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "202605280001"
down_revision: Union[str, None] = "202605250001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE ai_api_keys DROP CONSTRAINT IF EXISTS ai_api_keys_key_hash_key")


def downgrade() -> None:
    op.create_unique_constraint("ai_api_keys_key_hash_key", "ai_api_keys", ["key_hash"])
