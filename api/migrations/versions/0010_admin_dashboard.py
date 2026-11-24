"""Add what the admin dashboard needs: the credit ledger, the state of the low balance mail, the journal of the admin, and indexes"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSTGRESQL = "postgresql"
ROLE_FACTEUR = "mcplain_facteur"
BALANCE_ALERT_ROW = 1
POSTMAN_RIGHTS: tuple[str, ...] = (
    f"GRANT SELECT (created_at, cost_usd) ON public.ai_calls TO {ROLE_FACTEUR}",
    f"GRANT SELECT ON public.credit_entries TO {ROLE_FACTEUR}",
    f"GRANT SELECT, UPDATE (sent_at) ON public.balance_alert TO {ROLE_FACTEUR}",
)


def upgrade() -> None:
    """Create the three tables and the new columns, and give the postman only what it needs to watch the balance"""

    with op.batch_alter_table("analyses") as batch:
        batch.add_column(sa.Column("ignore_cache", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_index("ix_analyses_created_at", "analyses", ["created_at"])
    with op.batch_alter_table("ai_admin_alerts") as batch:
        batch.add_column(sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_ai_admin_alerts_created_at", "ai_admin_alerts", ["created_at"])
    op.create_table(
        "credit_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("note", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('statement', 'top_up')", name="credit_entries_kind_valid"),
        sa.CheckConstraint("amount_usd >= 0", name="credit_entries_amount_valid"),
    )
    op.create_index("ix_credit_entries_created_at", "credit_entries", ["created_at"])
    balance_alert = op.create_table(
        "balance_alert",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.bulk_insert(balance_alert, [{"id": BALANCE_ALERT_ROW, "sent_at": None}])
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("target_kind", sa.String(16), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_actions_created_at", "admin_actions", ["created_at"])
    if op.get_bind().dialect.name == POSTGRESQL:
        for statement in POSTMAN_RIGHTS:
            op.execute(statement)


def downgrade() -> None:
    """Drop the three tables, the new columns and the indexes"""

    op.drop_index("ix_admin_actions_created_at", table_name="admin_actions")
    op.drop_table("admin_actions")
    op.drop_table("balance_alert")
    op.drop_index("ix_credit_entries_created_at", table_name="credit_entries")
    op.drop_table("credit_entries")
    op.drop_index("ix_ai_admin_alerts_created_at", table_name="ai_admin_alerts")
    with op.batch_alter_table("ai_admin_alerts") as batch:
        batch.drop_column("read_at")
    op.drop_index("ix_analyses_created_at", table_name="analyses")
    with op.batch_alter_table("analyses") as batch:
        batch.drop_column("ignore_cache")
