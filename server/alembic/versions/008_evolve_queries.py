"""Create evolve_queries table

Revision ID: 008
Revises: 007
Create Date: 2026-08-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evolve_queries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("agent_id", sa.String(255), nullable=True),
        sa.Column("run_id", sa.String(255), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=True),
        sa.Column("depth", sa.String(16), nullable=True),
        sa.Column("rerank", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_score", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_zero_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_evolve_queries_created_at", "evolve_queries", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_evolve_queries_created_at", table_name="evolve_queries")
    op.drop_table("evolve_queries")
