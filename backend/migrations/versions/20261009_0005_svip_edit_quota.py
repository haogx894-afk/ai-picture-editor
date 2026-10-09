"""cap existing SVIP edit quotas at the new default

Revision ID: a1b2c3d4e5f6
Revises: 91c4f6e8a2b1
"""

from alembic import op


revision = "a1b2c3d4e5f6"
down_revision = "91c4f6e8a2b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve usage history while applying the new SVIP edit allowance.
    op.execute("UPDATE users SET edit_limit = 4 WHERE plan = 'svip' AND edit_limit = 500")


def downgrade() -> None:
    op.execute("UPDATE users SET edit_limit = 500 WHERE plan = 'svip' AND edit_limit = 4")
