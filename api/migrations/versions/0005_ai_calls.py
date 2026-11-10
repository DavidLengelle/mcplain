"""Add the log of AI calls, fill it from the texts already written, and make the texts broken by encoding retryable"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ai_calls, copy one call per text that cost something, and turn rejected encoding texts into failed ones"""

    op.create_table(
        "ai_calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("text_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("lang", sa.String(8), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("reject_reason", sa.String(32), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Float(), server_default="0", nullable=False),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_calls_text_id_created_at", "ai_calls", ["text_id", "created_at"])
    op.create_index("ix_ai_calls_created_at", "ai_calls", ["created_at"])
    op.create_index("ix_ai_calls_reject_reason_created_at", "ai_calls", ["reject_reason", "created_at"])
    texts = sa.table(
        "ai_texts",
        sa.column("id", sa.Uuid()),
        sa.column("kind", sa.String()),
        sa.column("lang", sa.String()),
        sa.column("status", sa.String()),
        sa.column("reject_reason", sa.String()),
        sa.column("input_tokens", sa.Integer()),
        sa.column("output_tokens", sa.Integer()),
        sa.column("cost_usd", sa.Float()),
        sa.column("request_id", sa.String()),
        sa.column("retry_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(texts).where(texts.c.input_tokens + texts.c.output_tokens > 0)).all()
    calls = sa.table(
        "ai_calls",
        sa.column("id", sa.Uuid()),
        sa.column("text_id", sa.Uuid()),
        sa.column("kind", sa.String()),
        sa.column("lang", sa.String()),
        sa.column("outcome", sa.String()),
        sa.column("reject_reason", sa.String()),
        sa.column("input_tokens", sa.Integer()),
        sa.column("output_tokens", sa.Integer()),
        sa.column("cost_usd", sa.Float()),
        sa.column("request_id", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    if rows:
        op.bulk_insert(
            calls,
            [
                {
                    "id": uuid.uuid4(),
                    "text_id": row.id,
                    "kind": row.kind,
                    "lang": row.lang,
                    "outcome": "answered",
                    "reject_reason": row.reject_reason,
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                    "cost_usd": row.cost_usd,
                    "request_id": row.request_id,
                    "created_at": row.updated_at,
                }
                for row in rows
            ],
        )
    connection.execute(
        texts.update()
        .where(texts.c.status == "rejected")
        .where(texts.c.reject_reason == "encoding")
        .values(status="failed", retry_at=None)
    )


def downgrade() -> None:
    """Drop ai_calls; the texts stay failed, they are only asked again"""

    op.drop_table("ai_calls")
