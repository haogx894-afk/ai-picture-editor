"""add user approval, plans and usage quotas

Revision ID: 91c4f6e8a2b1
Revises: 8d4e0a1b2c3d
"""

import sqlalchemy as sa
from alembic import op


revision = "91c4f6e8a2b1"
down_revision = "8d4e0a1b2c3d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing local accounts remain usable. New registrations are assigned by the service.
    op.add_column(
        "users",
        sa.Column("status", sa.String(length=16), server_default="approved", nullable=False),
    )
    op.alter_column("users", "status", server_default="pending")
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("users", sa.Column("plan", sa.String(length=16), server_default="free", nullable=False))
    op.add_column("users", sa.Column("agent_input_limit", sa.Integer(), server_default="2", nullable=False))
    op.add_column("users", sa.Column("agent_input_used", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("agent_output_limit", sa.Integer(), server_default="2", nullable=False))
    op.add_column("users", sa.Column("agent_output_used", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("edit_limit", sa.Integer(), server_default="2", nullable=False))
    op.add_column("users", sa.Column("edit_used", sa.Integer(), server_default="0", nullable=False))
    op.create_index(
        "uq_users_single_admin",
        "users",
        ["is_admin"],
        unique=True,
        postgresql_where=sa.text("is_admin = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_single_admin", table_name="users")
    for name in (
        "edit_used",
        "edit_limit",
        "agent_output_used",
        "agent_output_limit",
        "agent_input_used",
        "agent_input_limit",
        "plan",
        "is_admin",
        "status",
    ):
        op.drop_column("users", name)
