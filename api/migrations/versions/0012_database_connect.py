"""Let only the three service roles connect to the database of MCPlain: any other role, such as the one of Umami, is refused"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSTGRESQL = "postgresql"
ROLES: tuple[str, ...] = ("mcplain_app", "mcplain_guichet", "mcplain_facteur")


def quoted_database() -> str:
    """Return the name of the current database, quoted as an identifier"""

    name = op.get_bind().execute(sa.text("SELECT current_database()")).scalar_one()
    return '"' + str(name).replace('"', '""') + '"'


def upgrade() -> None:
    """Take the right to connect away from PUBLIC and give it back to the three service roles only"""

    if op.get_bind().dialect.name != POSTGRESQL:
        return
    database = quoted_database()
    op.execute(f"REVOKE CONNECT ON DATABASE {database} FROM PUBLIC")
    for role in ROLES:
        op.execute(f"GRANT CONNECT ON DATABASE {database} TO {role}")


def downgrade() -> None:
    """Give the right to connect back to PUBLIC, as PostgreSQL does by default"""

    if op.get_bind().dialect.name != POSTGRESQL:
        return
    database = quoted_database()
    for role in ROLES:
        op.execute(f"REVOKE CONNECT ON DATABASE {database} FROM {role}")
    op.execute(f"GRANT CONNECT ON DATABASE {database} TO PUBLIC")
