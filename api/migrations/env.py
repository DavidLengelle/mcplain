"""Alembic environment: the database URL comes from the settings, never from alembic.ini"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from mcplain_api.db import Base, make_engine
from mcplain_api.settings import Settings

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)


def database_url() -> str:
    """Return the URL given by a test, or the one of the settings"""

    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return Settings().database_url


def run(connection: Connection) -> None:
    """Run the migrations on one connection"""

    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_offline() -> None:
    """Write the migrations as SQL without a database"""

    context.configure(url=database_url(), target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    """Apply the migrations to the database"""

    engine = make_engine(database_url())
    with engine.connect() as connection:
        run(connection)
    engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
