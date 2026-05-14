"""user unit scope

Revision ID: 202604230001
Revises: 202604140002
Create Date: 2026-04-23 23:55:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202604230001"
down_revision: Union[str, None] = "202604140002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("users")}
    indexes = {index["name"] for index in inspector.get_indexes("users")}

    if "unit_id" not in user_columns:
        op.add_column("users", sa.Column("unit_id", sa.UUID(), nullable=True))

    if "ix_users_unit_id" not in indexes:
        op.create_index("ix_users_unit_id", "users", ["unit_id"], unique=False)

    if "fk_users_unit_id_units" not in foreign_keys:
        op.create_foreign_key(
            "fk_users_unit_id_units",
            "users",
            "units",
            ["unit_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("users")}
    indexes = {index["name"] for index in inspector.get_indexes("users")}

    if "fk_users_unit_id_units" in foreign_keys:
        op.drop_constraint("fk_users_unit_id_units", "users", type_="foreignkey")
    if "ix_users_unit_id" in indexes:
        op.drop_index("ix_users_unit_id", table_name="users")
    if "unit_id" in user_columns:
        op.drop_column("users", "unit_id")
