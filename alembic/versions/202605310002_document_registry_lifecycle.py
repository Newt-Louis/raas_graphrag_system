"""add document registry lifecycle

Revision ID: 202605310002
Revises: 202605310001
Create Date: 2026-05-31 22:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "202605310002"
down_revision: Union[str, None] = "202605310001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("documents", "tenant_id", nullable=True)
    op.alter_column("documents", "app_id", nullable=True)
    op.create_unique_constraint("uq_documents_filename", "documents", ["filename"])


def downgrade() -> None:
    op.drop_constraint("uq_documents_filename", "documents", type_="unique")
    op.alter_column("documents", "app_id", nullable=False)
    op.alter_column("documents", "tenant_id", nullable=False)
