"""Tests of the Alembic migrations: they build exactly the tables of the models"""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from mcplain_api.db import Base, make_engine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def alembic_config(url: str) -> Config:
    """Return the Alembic configuration pointed at a test database"""

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    return config


def test_migrations_build_the_models(tmp_path: Path) -> None:
    """After upgrade head, the database matches the models, indexes included"""

    url = f"sqlite:///{tmp_path / 'mcplain.db'}"
    command.upgrade(alembic_config(url), "head")
    engine = make_engine(url)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    indexes = {index["name"]: index["column_names"] for index in inspect(engine).get_indexes("analyses")}
    assert indexes == {"ix_analyses_state_created_at": ["state", "created_at"], "ix_analyses_source_key": ["source_key"]}
    engine.dispose()


def test_migrations_go_back_down(tmp_path: Path) -> None:
    """downgrade base removes the table"""

    url = f"sqlite:///{tmp_path / 'mcplain.db'}"
    config = alembic_config(url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    engine = make_engine(url)
    assert "analyses" not in inspect(engine).get_table_names()
    engine.dispose()
