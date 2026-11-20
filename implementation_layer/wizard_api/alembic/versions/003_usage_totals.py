"""usage_totals: spend and sessions started per user and per deployment month

Revision ID: 003
Revises: 002
Create Date: 2026-11-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_totals",
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sessions_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("scope", "key"),
    )


def downgrade() -> None:
    op.drop_table("usage_totals")
