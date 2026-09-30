"""agent resume relationship

Revision ID: 5b72a9f1d4c0
Revises: fa850313b768
"""

import sqlalchemy as sa
from alembic import op

revision = "5b72a9f1d4c0"
down_revision = "fa850313b768"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("resumed_from_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_agent_runs_resumed_from_id"),
        "agent_runs",
        ["resumed_from_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_agent_runs_resumed_from_id",
        "agent_runs",
        "agent_runs",
        ["resumed_from_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_agent_runs_resumed_from_id", "agent_runs", type_="foreignkey")
    op.drop_index(op.f("ix_agent_runs_resumed_from_id"), table_name="agent_runs")
    op.drop_column("agent_runs", "resumed_from_id")
