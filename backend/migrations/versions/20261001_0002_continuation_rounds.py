"""persist continuous agent planning rounds

Revision ID: 7c2e6f4a9b11
Revises: 5b72a9f1d4c0
"""

import sqlalchemy as sa
from alembic import op


revision = "7c2e6f4a9b11"
down_revision = "5b72a9f1d4c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("continuation_rounds", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "continuation_rounds")
