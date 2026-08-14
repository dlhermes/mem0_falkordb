"""Add refined_memory_ids column to memory_refine_candidates

Revision ID: 012
Revises: 011
Create Date: 2026-08-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memory_refine_candidates",
        sa.Column("refined_memory_ids", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("memory_refine_candidates", "refined_memory_ids")
