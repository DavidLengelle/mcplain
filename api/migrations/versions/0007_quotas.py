"""Add the quotas, the burst counts, the tokens of the analyses, the history of the accounts, and the bench role"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSTGRESQL = "postgresql"
STATE_CONSTRAINT = "analyses_state_valid"
NEW_STATES = "state IN ('queued', 'fetching', 'analyzing', 'done', 'failed', 'quota_exhausted')"
OLD_STATES = "state IN ('queued', 'fetching', 'analyzing', 'done', 'failed')"
ROLE_CONSTRAINT = "user_role_valid"


def upgrade() -> None:
    """Create the new tables, accept the quota_exhausted state and, on PostgreSQL, the bench role of an account"""

    with op.batch_alter_table("analyses") as batch:
        batch.add_column(sa.Column("cache_only", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.drop_constraint(STATE_CONSTRAINT, type_="check")
        batch.create_check_constraint(STATE_CONSTRAINT, NEW_STATES)
    op.create_table(
        "quota_usage",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("subject", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("day", "subject", name="quota_usage_pkey"),
    )
    op.create_table(
        "analysis_tokens",
        sa.Column("analysis_id", sa.Uuid(), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("subject", sa.String(80), nullable=False),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_analysis_tokens_day", "analysis_tokens", ["day"])
    op.create_index("ix_analysis_tokens_subject", "analysis_tokens", ["subject"])
    op.create_table(
        "burst_counts",
        sa.Column("subject", sa.String(80), nullable=False),
        sa.Column("minute", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("subject", "minute", name="burst_counts_pkey"),
    )
    op.create_index("ix_burst_counts_minute", "burst_counts", ["minute"])
    op.create_table(
        "quota_refusals",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("day", "kind", name="quota_refusals_pkey"),
    )
    op.create_table(
        "user_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_history_user_id_created_at", "user_history", ["user_id", "created_at"])
    op.create_index("ix_user_history_analysis_id", "user_history", ["analysis_id"])
    if op.get_bind().dialect.name == POSTGRESQL:
        op.execute(
            f'ALTER TABLE auth."user" DROP CONSTRAINT {ROLE_CONSTRAINT}, '
            f"ADD CONSTRAINT {ROLE_CONSTRAINT} CHECK (\"role\" IN ('user', 'admin', 'bench'))"
        )


def downgrade() -> None:
    """Remove the new tables, the quota_exhausted state and the bench role"""

    if op.get_bind().dialect.name == POSTGRESQL:
        op.execute("UPDATE auth.\"user\" SET role = 'user' WHERE role = 'bench'")
        op.execute(
            f'ALTER TABLE auth."user" DROP CONSTRAINT {ROLE_CONSTRAINT}, '
            f"ADD CONSTRAINT {ROLE_CONSTRAINT} CHECK (\"role\" IN ('user', 'admin'))"
        )
    op.drop_index("ix_user_history_analysis_id", table_name="user_history")
    op.drop_index("ix_user_history_user_id_created_at", table_name="user_history")
    op.drop_table("user_history")
    op.drop_table("quota_refusals")
    op.drop_index("ix_burst_counts_minute", table_name="burst_counts")
    op.drop_table("burst_counts")
    op.drop_index("ix_analysis_tokens_subject", table_name="analysis_tokens")
    op.drop_index("ix_analysis_tokens_day", table_name="analysis_tokens")
    op.drop_table("analysis_tokens")
    op.drop_table("quota_usage")
    op.execute("DELETE FROM analyses WHERE state = 'quota_exhausted'")
    with op.batch_alter_table("analyses") as batch:
        batch.drop_constraint(STATE_CONSTRAINT, type_="check")
        batch.create_check_constraint(STATE_CONSTRAINT, OLD_STATES)
        batch.drop_column("cache_only")
