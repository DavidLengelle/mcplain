"""Add the tables of the accounts; on PostgreSQL, the roles of the services and the auth schema of the counter (guichet)"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_APP = "mcplain_app"
ROLE_GUICHET = "mcplain_guichet"
ROLE_FACTEUR = "mcplain_facteur"
ROLES: tuple[str, ...] = (ROLE_APP, ROLE_GUICHET, ROLE_FACTEUR)
AUTH_SCHEMA = "auth"
POSTGRESQL = "postgresql"

BETTER_AUTH_TABLES: tuple[str, ...] = (
    'CREATE TABLE auth."user" ("id" text NOT NULL PRIMARY KEY, "name" text NOT NULL, "email" text NOT NULL UNIQUE, '
    '"emailVerified" boolean NOT NULL, "image" text, "createdAt" timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, '
    '"updatedAt" timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, "role" text DEFAULT \'user\' NOT NULL, '
    "CONSTRAINT user_role_valid CHECK (\"role\" IN ('user', 'admin')))",
    'CREATE TABLE auth."session" ("id" text NOT NULL PRIMARY KEY, "expiresAt" timestamptz NOT NULL, "token" text NOT NULL UNIQUE, '
    '"createdAt" timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, "updatedAt" timestamptz NOT NULL, "ipAddress" text, '
    '"userAgent" text, "userId" text NOT NULL REFERENCES auth."user" ("id") ON DELETE CASCADE)',
    'CREATE TABLE auth."account" ("id" text NOT NULL PRIMARY KEY, "accountId" text NOT NULL, "providerId" text NOT NULL, '
    '"userId" text NOT NULL REFERENCES auth."user" ("id") ON DELETE CASCADE, "accessToken" text, "refreshToken" text, '
    '"idToken" text, "accessTokenExpiresAt" timestamptz, "refreshTokenExpiresAt" timestamptz, "scope" text, "password" text, '
    '"createdAt" timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, "updatedAt" timestamptz NOT NULL)',
    'CREATE TABLE auth."verification" ("id" text NOT NULL PRIMARY KEY, "identifier" text NOT NULL, "value" text NOT NULL, '
    '"expiresAt" timestamptz NOT NULL, "createdAt" timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, '
    '"updatedAt" timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL)',
    'CREATE INDEX "session_userId_idx" ON auth."session" ("userId")',
    'CREATE INDEX "account_userId_idx" ON auth."account" ("userId")',
    'CREATE INDEX "verification_identifier_idx" ON auth."verification" ("identifier")',
)


def upgrade() -> None:
    """Create the shared tables, then the roles, the auth schema and the rights on PostgreSQL"""

    op.add_column("ai_admin_alerts", sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "mail_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("lang", sa.String(8), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("link", sa.String(2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('verify_email', 'reset_password')", name="mail_outbox_kind_valid"),
        sa.CheckConstraint("lang IN ('en', 'fr')", name="mail_outbox_lang_valid"),
    )
    op.create_index("ix_mail_outbox_created_at", "mail_outbox", ["created_at"])
    op.create_table(
        "ip_salts",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("salt", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "altcha_uses",
        sa.Column("signature_hash", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_altcha_uses_expires_at", "altcha_uses", ["expires_at"])
    op.create_table(
        "signup_counts",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("day", "ip_hash", name="signup_counts_pkey"),
    )
    op.create_table(
        "signup_refusals",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
    )
    if op.get_bind().dialect.name == POSTGRESQL:
        create_roles_and_rights()


def create_roles_and_rights() -> None:
    """Create the roles without password, the auth schema owned by the counter, and give each role its rights only"""

    owner = op.get_bind().execute(sa.text("SELECT current_user")).scalar_one()
    for role in ROLES:
        op.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') "
            f"THEN CREATE ROLE {role} LOGIN; END IF; END $$"
        )
        op.execute(f"ALTER ROLE {role} NOSUPERUSER NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT LOGIN")
    op.execute(f"ALTER ROLE {ROLE_APP} CREATEDB")
    op.execute(f"CREATE SCHEMA {AUTH_SCHEMA} AUTHORIZATION {ROLE_GUICHET}")
    op.execute(f"REVOKE ALL ON SCHEMA {AUTH_SCHEMA} FROM PUBLIC")
    op.execute(f"SET LOCAL ROLE {ROLE_GUICHET}")
    for statement in BETTER_AUTH_TABLES:
        op.execute(statement)
    op.execute("RESET ROLE")
    op.execute(f"ALTER ROLE {ROLE_GUICHET} SET search_path = {AUTH_SCHEMA}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE_APP}")
    op.execute(f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {ROLE_APP}')
    op.execute(f"REVOKE ALL ON public.mail_outbox FROM {ROLE_APP}")
    op.execute(f"REVOKE ALL ON public.alembic_version FROM {ROLE_APP}")
    op.execute(f"GRANT INSERT ON public.mail_outbox TO {ROLE_GUICHET}")
    op.execute(f"GRANT SELECT, DELETE ON public.mail_outbox TO {ROLE_FACTEUR}")
    op.execute(f"GRANT SELECT, UPDATE (emailed_at) ON public.ai_admin_alerts TO {ROLE_FACTEUR}")


def downgrade() -> None:
    """Remove the auth schema, the rights and the roles on PostgreSQL, then the shared tables"""

    if op.get_bind().dialect.name == POSTGRESQL:
        owner = op.get_bind().execute(sa.text("SELECT current_user")).scalar_one()
        op.execute(f"DROP SCHEMA IF EXISTS {AUTH_SCHEMA} CASCADE")
        op.execute(f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" IN SCHEMA public REVOKE ALL ON TABLES FROM {ROLE_APP}')
        for role in ROLES:
            op.execute(f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN DROP OWNED BY {role}; DROP ROLE {role}; END IF; END $$")
    op.drop_table("signup_refusals")
    op.drop_table("signup_counts")
    op.drop_index("ix_altcha_uses_expires_at", table_name="altcha_uses")
    op.drop_table("altcha_uses")
    op.drop_table("ip_salts")
    op.drop_index("ix_mail_outbox_created_at", table_name="mail_outbox")
    op.drop_table("mail_outbox")
    op.drop_column("ai_admin_alerts", "emailed_at")
