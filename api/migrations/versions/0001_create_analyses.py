"""Create the analyses table, which is also the job queue"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the analyses table and its indexes"""

    op.create_table(
        "analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("input_raw", sa.String(length=500), nullable=False),
        sa.Column("select", sa.String(length=500), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("source_key", sa.String(length=600), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("result", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("engine_version", sa.String(length=32), nullable=True),
        sa.Column("rules_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('queued', 'fetching', 'analyzing', 'done', 'failed')", name="analyses_state_valid"
        ),
        sa.PrimaryKeyConstraint("id", name="analyses_pkey"),
    )
    op.create_index("ix_analyses_state_created_at", "analyses", ["state", "created_at"])
    op.create_index("ix_analyses_source_key", "analyses", ["source_key"])


def downgrade() -> None:
    """Drop the analyses table"""

    op.drop_index("ix_analyses_source_key", table_name="analyses")
    op.drop_index("ix_analyses_state_created_at", table_name="analyses")
    op.drop_table("analyses")
