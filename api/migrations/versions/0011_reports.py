"""Add the reports of the visitors, their daily counts and their marks, and let the postman erase the old comments only"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSTGRESQL = "postgresql"
ROLE_FACTEUR = "mcplain_facteur"
POSTMAN_RIGHTS: tuple[str, ...] = (
    f"GRANT SELECT (closed_at, comment_erased_at), UPDATE (comment, comment_erased_at) ON public.reports TO {ROLE_FACTEUR}",
)


def upgrade() -> None:
    """Create the three tables and their indexes, and give the postman the two column rights of the erasing"""

    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("comment", sa.String(500), nullable=True),
        sa.Column("engine_version", sa.String(32), nullable=True),
        sa.Column("rules_version", sa.String(32), nullable=True),
        sa.Column("color", sa.String(16), nullable=True),
        sa.Column("reporter_kind", sa.String(16), nullable=False),
        sa.Column("reporter_user_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment_erased_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('false_alarm', 'missed_danger', 'author_error')", name="reports_kind_valid"),
        sa.CheckConstraint("status IN ('new', 'handled', 'rejected')", name="reports_status_valid"),
        sa.CheckConstraint("reporter_kind IN ('anonymous', 'account', 'deleted')", name="reports_reporter_kind_valid"),
        sa.CheckConstraint("color IS NULL OR color IN ('red', 'orange', 'gray', 'green')", name="reports_color_valid"),
    )
    op.create_index("ix_reports_created_at", "reports", ["created_at"])
    op.create_index("ix_reports_status_created_at", "reports", ["status", "created_at"])
    op.create_index("ix_reports_closed_at", "reports", ["closed_at"])
    op.create_index("ix_reports_reporter_user_id", "reports", ["reporter_user_id"])
    op.create_table(
        "report_counts",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("subject", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("day", "subject", name="report_counts_pkey"),
    )
    op.create_table(
        "report_marks",
        sa.Column("subject", sa.String(80), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("subject", "analysis_id", "kind", name="report_marks_pkey"),
    )
    op.create_index("ix_report_marks_day", "report_marks", ["day"])
    if op.get_bind().dialect.name == POSTGRESQL:
        for statement in POSTMAN_RIGHTS:
            op.execute(statement)


def downgrade() -> None:
    """Drop the three tables and their indexes"""

    op.drop_index("ix_report_marks_day", table_name="report_marks")
    op.drop_table("report_marks")
    op.drop_table("report_counts")
    op.drop_index("ix_reports_reporter_user_id", table_name="reports")
    op.drop_index("ix_reports_closed_at", table_name="reports")
    op.drop_index("ix_reports_status_created_at", table_name="reports")
    op.drop_index("ix_reports_created_at", table_name="reports")
    op.drop_table("reports")
