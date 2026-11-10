"""One-shot service: apply the migrations as the owner of the database, then give each service role its password"""

import os
import re
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from psycopg import sql
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import Engine

from mcplain_api.db import make_engine

ALEMBIC_INI_ENV = "MCPLAIN_ALEMBIC_INI"
DEFAULT_ALEMBIC_INI = "/app/alembic.ini"
PASSWORD_PATTERN = re.compile(r"^[A-Za-z0-9_-]{24,256}$")
POSTGRESQL_PREFIX = "postgresql"


class MigrateSettings(BaseSettings):
    """Class that holds the owner URL of the database and the passwords of the three service roles"""

    model_config = SettingsConfigDict(populate_by_name=True, extra="ignore")

    database_url: str = Field(validation_alias="DATABASE_URL")
    app_password: SecretStr = Field(validation_alias="MCPLAIN_APP_DB_PASSWORD")
    guichet_password: SecretStr = Field(validation_alias="MCPLAIN_GUICHET_DB_PASSWORD")
    facteur_password: SecretStr = Field(validation_alias="MCPLAIN_FACTEUR_DB_PASSWORD")

    @field_validator("app_password", "guichet_password", "facteur_password")
    @classmethod
    def password_fits_in_a_url(cls, value: SecretStr) -> SecretStr:
        """Refuse a password too short, or one that would need escaping in a database URL"""

        if not PASSWORD_PATTERN.match(value.get_secret_value()):
            raise ValueError("use at least 24 letters, digits, '-' or '_': run scripts/init-secrets.sh")
        return value

    def role_passwords(self) -> dict[str, str]:
        """Return the password of each service role"""

        return {
            "mcplain_app": self.app_password.get_secret_value(),
            "mcplain_guichet": self.guichet_password.get_secret_value(),
            "mcplain_facteur": self.facteur_password.get_secret_value(),
        }


def set_role_passwords(engine: Engine, passwords: dict[str, str]) -> None:
    """Give each role its password, quoted by psycopg, never written in a log"""

    connection = engine.raw_connection()
    try:
        cursor = connection.cursor()
        for role, password in passwords.items():
            statement = sql.SQL("ALTER ROLE {} WITH PASSWORD {}").format(sql.Identifier(role), sql.Literal(password))
            cursor.execute(statement)
        connection.commit()
    finally:
        connection.close()


def main() -> int:
    """Run alembic upgrade head, then set the passwords of the service roles on PostgreSQL"""

    settings = MigrateSettings()
    config = Config(str(Path(os.environ.get(ALEMBIC_INI_ENV, DEFAULT_ALEMBIC_INI))))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")
    if settings.database_url.startswith(POSTGRESQL_PREFIX):
        engine = make_engine(settings.database_url)
        set_role_passwords(engine, settings.role_passwords())
        engine.dispose()
    print("migrate: database up to date, service roles ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
