"""user page permissions

Revision ID: 202604240002
Revises: 202604240001
Create Date: 2026-04-24 15:10:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202604240002"
down_revision: Union[str, None] = "202604240001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}

    if "page_permissions" not in user_columns:
        op.add_column(
            "users",
            sa.Column(
                "page_permissions",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
        op.execute("UPDATE users SET page_permissions = '{}'::jsonb WHERE page_permissions IS NULL")
        op.alter_column("users", "page_permissions", server_default=None)

    if "force_fullscreen_mode" not in user_columns:
        op.add_column(
            "users",
            sa.Column("force_fullscreen_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.execute("UPDATE users SET force_fullscreen_mode = false WHERE force_fullscreen_mode IS NULL")
        op.alter_column("users", "force_fullscreen_mode", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}

    if "force_fullscreen_mode" in user_columns:
        op.drop_column("users", "force_fullscreen_mode")

    if "page_permissions" in user_columns:
        op.drop_column("users", "page_permissions")
