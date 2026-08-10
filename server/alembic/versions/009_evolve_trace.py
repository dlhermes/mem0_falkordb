"""Add trace column to evolve_queries

Revision ID: 009
Revises: 008
Create Date: 2026-08-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evolve_queries", sa.Column("trace", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("evolve_queries", "trace")
