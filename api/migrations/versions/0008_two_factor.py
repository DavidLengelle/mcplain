"""Add the second factor of the counter (Better Auth twoFactor plugin) to the auth schema, owned by the counter's role"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSTGRESQL = "postgresql"
ROLE_GUICHET = "mcplain_guichet"

TWO_FACTOR_TABLES: tuple[str, ...] = (
    'ALTER TABLE auth."user" ADD COLUMN "twoFactorEnabled" boolean DEFAULT false',
    'CREATE TABLE auth."twoFactor" ("id" text NOT NULL PRIMARY KEY, "secret" text NOT NULL, "backupCodes" text NOT NULL, '
    '"userId" text NOT NULL REFERENCES auth."user" ("id") ON DELETE CASCADE, "verified" boolean, '
    '"failedVerificationCount" integer, "lockedUntil" timestamptz)',
    'CREATE INDEX "twoFactor_secret_idx" ON auth."twoFactor" ("secret")',
    'CREATE INDEX "twoFactor_userId_idx" ON auth."twoFactor" ("userId")',
)


def upgrade() -> None:
    """Create the column and the table of the second factor as the counter's role, from the SQL Better Auth generates"""

    if op.get_bind().dialect.name != POSTGRESQL:
        return
    op.execute(f"SET LOCAL ROLE {ROLE_GUICHET}")
    for statement in TWO_FACTOR_TABLES:
        op.execute(statement)
    op.execute("RESET ROLE")


def downgrade() -> None:
    """Remove the table and the column of the second factor"""

    if op.get_bind().dialect.name != POSTGRESQL:
        return
    op.execute('DROP TABLE auth."twoFactor"')
    op.execute('ALTER TABLE auth."user" DROP COLUMN "twoFactorEnabled"')
