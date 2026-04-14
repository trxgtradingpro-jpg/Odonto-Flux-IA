"""professional schedule fields

Revision ID: 202604140002
Revises: 202604080001
Create Date: 2026-04-14 08:20:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202604140002"
down_revision: Union[str, None] = "202604080001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    professional_columns = {column["name"] for column in inspector.get_columns("professionals")}

    if "working_days" not in professional_columns:
        op.add_column(
            "professionals",
            sa.Column(
                "working_days",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[0,1,2,3,4]'::jsonb"),
            ),
        )
    if "shift_start" not in professional_columns:
        op.add_column(
            "professionals",
            sa.Column("shift_start", sa.String(length=5), nullable=False, server_default="08:00"),
        )
    if "shift_end" not in professional_columns:
        op.add_column(
            "professionals",
            sa.Column("shift_end", sa.String(length=5), nullable=False, server_default="18:00"),
        )
    if "procedures" not in professional_columns:
        op.add_column(
            "professionals",
            sa.Column(
                "procedures",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )

    op.alter_column("professionals", "working_days", server_default=None)
    op.alter_column("professionals", "shift_start", server_default=None)
    op.alter_column("professionals", "shift_end", server_default=None)
    op.alter_column("professionals", "procedures", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    professional_columns = {column["name"] for column in inspector.get_columns("professionals")}

    if "procedures" in professional_columns:
        op.drop_column("professionals", "procedures")
    if "shift_end" in professional_columns:
        op.drop_column("professionals", "shift_end")
    if "shift_start" in professional_columns:
        op.drop_column("professionals", "shift_start")
    if "working_days" in professional_columns:
        op.drop_column("professionals", "working_days")
