"""add affiliate prospect ownership

Revision ID: 202606080001
Revises: 202605290001
Create Date: 2026-06-08 00:00:01.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "202606080001"
down_revision: Union[str, None] = "202605290001"
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


def upgrade() -> None:
    columns = _columns("prospect_accounts")
    if "affiliate_owner_user_id" not in columns:
        op.add_column(
            "prospect_accounts",
            sa.Column(
                "affiliate_owner_user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if "affiliate_claimed_at" not in columns:
        op.add_column(
            "prospect_accounts",
            sa.Column("affiliate_claimed_at", sa.DateTime(timezone=True), nullable=True),
        )

    indexes = _indexes("prospect_accounts")
    if "ix_prospect_accounts_affiliate_owner_user_id" not in indexes:
        op.create_index(
            "ix_prospect_accounts_affiliate_owner_user_id",
            "prospect_accounts",
            ["affiliate_owner_user_id"],
        )
    if "ix_prospect_accounts_affiliate_claimed_at" not in indexes:
        op.create_index(
            "ix_prospect_accounts_affiliate_claimed_at",
            "prospect_accounts",
            ["affiliate_claimed_at"],
        )

    op.execute(
        sa.text(
            """
            UPDATE prospect_accounts AS prospect
            SET affiliate_owner_user_id = prospect.created_by,
                affiliate_claimed_at = COALESCE(prospect.first_contact_at, prospect.created_at)
            WHERE prospect.affiliate_owner_user_id IS NULL
              AND prospect.created_by IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM user_roles AS user_role
                  JOIN roles AS role ON role.id = user_role.role_id
                  WHERE user_role.user_id = prospect.created_by
                    AND role.name = 'sales_affiliate'
              )
            """
        )
    )


def downgrade() -> None:
    indexes = _indexes("prospect_accounts")
    if "ix_prospect_accounts_affiliate_claimed_at" in indexes:
        op.drop_index("ix_prospect_accounts_affiliate_claimed_at", table_name="prospect_accounts")
    if "ix_prospect_accounts_affiliate_owner_user_id" in indexes:
        op.drop_index("ix_prospect_accounts_affiliate_owner_user_id", table_name="prospect_accounts")

    columns = _columns("prospect_accounts")
    if "affiliate_claimed_at" in columns:
        op.drop_column("prospect_accounts", "affiliate_claimed_at")
    if "affiliate_owner_user_id" in columns:
        op.drop_column("prospect_accounts", "affiliate_owner_user_id")
