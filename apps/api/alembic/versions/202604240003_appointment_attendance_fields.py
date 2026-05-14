"""appointment attendance fields

Revision ID: 202604240003
Revises: 202604240002
Create Date: 2026-04-24 16:20:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202604240003"
down_revision: Union[str, None] = "202604240002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    appointment_columns = {column["name"] for column in inspector.get_columns("appointments")}

    if "attendance_status" not in appointment_columns:
        op.add_column(
            "appointments",
            sa.Column("attendance_status", sa.String(length=40), nullable=False, server_default="pendente"),
        )
        op.execute("UPDATE appointments SET attendance_status = 'pendente' WHERE attendance_status IS NULL")
        op.alter_column("appointments", "attendance_status", server_default=None)

    if "attendance_notes" not in appointment_columns:
        op.add_column(
            "appointments",
            sa.Column("attendance_notes", sa.Text(), nullable=False, server_default=""),
        )
        op.execute("UPDATE appointments SET attendance_notes = '' WHERE attendance_notes IS NULL")
        op.alter_column("appointments", "attendance_notes", server_default=None)

    if "next_appointment_status" not in appointment_columns:
        op.add_column(
            "appointments",
            sa.Column("next_appointment_status", sa.String(length=40), nullable=False, server_default="nao_definido"),
        )
        op.execute(
            "UPDATE appointments SET next_appointment_status = 'nao_definido' WHERE next_appointment_status IS NULL"
        )
        op.alter_column("appointments", "next_appointment_status", server_default=None)

    op.execute(
        """
        UPDATE appointments
        SET attendance_status = CASE
            WHEN status = 'concluida' THEN 'compareceu'
            WHEN status = 'falta' THEN 'faltou'
            ELSE attendance_status
        END
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    appointment_columns = {column["name"] for column in inspector.get_columns("appointments")}

    if "next_appointment_status" in appointment_columns:
        op.drop_column("appointments", "next_appointment_status")

    if "attendance_notes" in appointment_columns:
        op.drop_column("appointments", "attendance_notes")

    if "attendance_status" in appointment_columns:
        op.drop_column("appointments", "attendance_status")
