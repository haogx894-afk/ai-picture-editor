"""persist whether a turn may continue planning automatically

Revision ID: 8d4e0a1b2c3d
Revises: 7c2e6f4a9b11
"""

import sqlalchemy as sa
from alembic import op


revision = "8d4e0a1b2c3d"
down_revision = "7c2e6f4a9b11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("auto_continue", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "auto_continue")
