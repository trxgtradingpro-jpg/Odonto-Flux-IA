"""initial schema

Revision ID: 202604070001
Revises:
Create Date: 2026-04-07 21:40:00

"""

from typing import Sequence, Union

from alembic import op

from app.db.base import Base

# revision identifiers, used by Alembic.
revision: str = '202604070001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
