"""Create evolve feedback loop tables

Revision ID: 007
Revises: 006
Create Date: 2026-08-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evolve_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("memory_id", sa.String(255), nullable=False),
        sa.Column("feedback_type", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_evolve_feedback_memory_id", "evolve_feedback", ["memory_id"])

    op.create_table(
        "evolve_salience",
        sa.Column("memory_id", sa.String(255), primary_key=True),
        sa.Column("salience_score", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_access_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "evolve_salience_adjustments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("memory_id", sa.String(255), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("feedback_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_evolve_salience_adjustments_memory_id", "evolve_salience_adjustments", ["memory_id"]
    )
    op.create_foreign_key(
        "fk_evolve_salience_adjustments_feedback_id",
        "evolve_salience_adjustments",
        "evolve_feedback",
        ["feedback_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_table("evolve_salience_adjustments")
    op.drop_table("evolve_salience")
    op.drop_table("evolve_feedback")
