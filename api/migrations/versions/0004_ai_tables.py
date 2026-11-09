"""Add the tables of the AI writer: its texts, its alerts for the admin and its state"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_COLUMN = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    """Create ai_texts, ai_admin_alerts and ai_state"""

    op.create_table(
        "ai_texts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("lang", sa.String(8), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("content", JSON_COLUMN, nullable=True),
        sa.Column("reject_reason", sa.String(32), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Float(), server_default="0", nullable=False),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("analysis_id", sa.Uuid(), nullable=True),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "lang", "hash", "prompt_version", "model", name="ai_texts_cache_key"),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'rejected', 'failed', 'paused', 'disabled')", name="ai_texts_status_valid"
        ),
    )
    op.create_index("ix_ai_texts_status_created_at", "ai_texts", ["status", "created_at"])
    op.create_index("ix_ai_texts_updated_at", "ai_texts", ["updated_at"])
    op.create_table(
        "ai_admin_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", JSON_COLUMN, nullable=True),
    )
    op.create_index("ix_ai_admin_alerts_code_created_at", "ai_admin_alerts", ["code", "created_at"])
    op.create_table(
        "ai_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_reason", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    """Drop the three tables"""

    op.drop_table("ai_state")
    op.drop_table("ai_admin_alerts")
    op.drop_table("ai_texts")
