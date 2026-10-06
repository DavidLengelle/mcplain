"""Add the date of the real analysis and whether the result comes from the cache"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add analyzed_at, empty for older analyses, and from_cache, false for them"""

    op.add_column("analyses", sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analyses", sa.Column("from_cache", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Drop analyzed_at and from_cache"""

    with op.batch_alter_table("analyses") as batch:
        batch.drop_column("from_cache")
        batch.drop_column("analyzed_at")
