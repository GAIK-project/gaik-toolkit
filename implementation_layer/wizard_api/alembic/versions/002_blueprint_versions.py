"""blueprint_versions + active_version on wizard_sessions

Revision ID: 002
Revises: 001
Create Date: 2026-06-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wizard_sessions",
        sa.Column("active_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "blueprint_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=512), nullable=False, server_default=""),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["wizard_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "version", name="uq_blueprint_session_version"),
    )
    op.create_index(
        op.f("ix_blueprint_versions_session_id"),
        "blueprint_versions",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_blueprint_versions_session_id"), table_name="blueprint_versions")
    op.drop_table("blueprint_versions")
    op.drop_column("wizard_sessions", "active_version")
