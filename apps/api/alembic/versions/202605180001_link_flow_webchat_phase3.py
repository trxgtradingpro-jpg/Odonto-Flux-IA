"""Add public webchat fields to link flow sessions.

Revision ID: 202605180001
Revises: 202605170001
Create Date: 2026-05-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "202605180001"
down_revision: Union[str, None] = "202605170001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if index_name not in _indexes(table_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    table = "link_flow_sessions"
    _add_column_if_missing(table, sa.Column("channel", sa.String(length=40), nullable=True))
    _add_column_if_missing(table, sa.Column("public_access_token_hash", sa.String(length=255), nullable=True))
    _add_column_if_missing(table, sa.Column("failure_reason", sa.String(length=120), nullable=True))
    _add_column_if_missing(table, sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(table, sa.Column("last_patient_message_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(table, sa.Column("last_assistant_message_at", sa.DateTime(timezone=True), nullable=True))

    _create_index_if_missing("ix_link_flow_sessions_channel", table, ["channel"])
    _create_index_if_missing("ix_link_flow_sessions_public_access_token_hash", table, ["public_access_token_hash"])


def downgrade() -> None:
    table = "link_flow_sessions"
    columns = _columns(table)
    indexes = _indexes(table)

    if "ix_link_flow_sessions_public_access_token_hash" in indexes:
        op.drop_index("ix_link_flow_sessions_public_access_token_hash", table_name=table)
    if "ix_link_flow_sessions_channel" in indexes:
        op.drop_index("ix_link_flow_sessions_channel", table_name=table)

    for column_name in (
        "last_assistant_message_at",
        "last_patient_message_at",
        "closed_at",
        "failure_reason",
        "public_access_token_hash",
        "channel",
    ):
        if column_name in columns:
            op.drop_column(table, column_name)
