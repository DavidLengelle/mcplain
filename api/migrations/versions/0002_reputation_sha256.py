"""Add the sha256 of the normalized reputation.json, part of the cache key"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the reputation_sha256 column; older analyses keep it empty and are never served from the cache"""

    op.add_column("analyses", sa.Column("reputation_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Drop the reputation_sha256 column"""

    with op.batch_alter_table("analyses") as batch:
        batch.drop_column("reputation_sha256")
