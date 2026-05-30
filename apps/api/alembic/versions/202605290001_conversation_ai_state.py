"""add conversation ai state

Revision ID: 202605290001
Revises: 202605280001
Create Date: 2026-05-29 00:00:01.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "202605290001"
down_revision: Union[str, None] = "202605280001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if "ai_state" not in _columns("conversations"):
        op.add_column(
            "conversations",
            sa.Column(
                "ai_state",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
    op.alter_column("conversations", "ai_state", server_default=None)


def downgrade() -> None:
    if "ai_state" in _columns("conversations"):
        op.drop_column("conversations", "ai_state")
