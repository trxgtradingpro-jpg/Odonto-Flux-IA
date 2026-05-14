"""patient cpf

Revision ID: 202604240001
Revises: 202604230001
Create Date: 2026-04-24 11:40:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202604240001"
down_revision: Union[str, None] = "202604230001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    patient_columns = {column["name"] for column in inspector.get_columns("patients")}
    indexes = {index["name"] for index in inspector.get_indexes("patients")}
    unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("patients")}

    if "cpf" not in patient_columns:
        op.add_column("patients", sa.Column("cpf", sa.String(length=20), nullable=True))

    if "normalized_cpf" not in patient_columns:
        op.add_column("patients", sa.Column("normalized_cpf", sa.String(length=20), nullable=True))

    if "ix_patients_normalized_cpf" not in indexes:
        op.create_index("ix_patients_normalized_cpf", "patients", ["normalized_cpf"], unique=False)

    if "uq_patient_tenant_cpf" not in unique_constraints:
        op.create_unique_constraint("uq_patient_tenant_cpf", "patients", ["tenant_id", "normalized_cpf"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    patient_columns = {column["name"] for column in inspector.get_columns("patients")}
    indexes = {index["name"] for index in inspector.get_indexes("patients")}
    unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("patients")}

    if "uq_patient_tenant_cpf" in unique_constraints:
        op.drop_constraint("uq_patient_tenant_cpf", "patients", type_="unique")

    if "ix_patients_normalized_cpf" in indexes:
        op.drop_index("ix_patients_normalized_cpf", table_name="patients")

    if "normalized_cpf" in patient_columns:
        op.drop_column("patients", "normalized_cpf")

    if "cpf" in patient_columns:
        op.drop_column("patients", "cpf")
