"""Add the ban state of an account (date and optional reason) to the auth schema, written by the counter only"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSTGRESQL = "postgresql"
ROLE_GUICHET = "mcplain_guichet"
BAN_REASON_MAX_CHARS = 200

BAN_COLUMNS: tuple[str, ...] = (
    'ALTER TABLE auth."user" ADD COLUMN "bannedAt" timestamptz',
    'ALTER TABLE auth."user" ADD COLUMN "banReason" text',
    f'ALTER TABLE auth."user" ADD CONSTRAINT user_ban_reason_length CHECK (char_length("banReason") <= {BAN_REASON_MAX_CHARS})',
)


def upgrade() -> None:
    """Create the two ban columns as the counter's role, from the SQL Better Auth generates, with a length limit"""

    if op.get_bind().dialect.name != POSTGRESQL:
        return
    op.execute(f"SET LOCAL ROLE {ROLE_GUICHET}")
    for statement in BAN_COLUMNS:
        op.execute(statement)
    op.execute("RESET ROLE")


def downgrade() -> None:
    """Remove the ban columns"""

    if op.get_bind().dialect.name != POSTGRESQL:
        return
    op.execute('ALTER TABLE auth."user" DROP CONSTRAINT user_ban_reason_length')
    op.execute('ALTER TABLE auth."user" DROP COLUMN "banReason"')
    op.execute('ALTER TABLE auth."user" DROP COLUMN "bannedAt"')
