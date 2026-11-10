"""Tests of the Alembic migrations: they build exactly the tables of the models"""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

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
    assert {"ai_texts", "ai_admin_alerts", "ai_state", "ai_calls"} <= set(inspect(engine).get_table_names())
    constraints = {item["name"]: item["column_names"] for item in inspect(engine).get_unique_constraints("ai_texts")}
    assert constraints == {"ai_texts_cache_key": ["kind", "lang", "hash", "prompt_version", "model"]}
    indexes = {index["name"]: index["column_names"] for index in inspect(engine).get_indexes("analyses")}
    assert indexes == {"ix_analyses_state_created_at": ["state", "created_at"], "ix_analyses_source_key": ["source_key"]}
    engine.dispose()


def test_migrations_go_back_down(tmp_path: Path) -> None:
    """downgrade base removes the tables"""

    url = f"sqlite:///{tmp_path / 'mcplain.db'}"
    config = alembic_config(url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    engine = make_engine(url)
    assert not {"analyses", "ai_texts", "ai_admin_alerts", "ai_state", "ai_calls"} & set(inspect(engine).get_table_names())
    engine.dispose()


def test_texts_broken_by_encoding_become_retryable(tmp_path: Path) -> None:
    """Migration 0005 turns rejected encoding texts into failed ones, keeps the others, and logs the calls already paid"""

    url = f"sqlite:///{tmp_path / 'mcplain.db'}"
    config = alembic_config(url)
    command.upgrade(config, "0004")
    engine = make_engine(url)
    columns = "id, kind, lang, hash, prompt_version, model, status, reject_reason, input_tokens, output_tokens, cost_usd, request_id, created_at, updated_at"
    rows = [
        ("a" * 32, "rejected", "encoding", 1198, 341, "req_a"),
        ("b" * 32, "rejected", "forbidden_word", 10, 5, "req_b"),
        ("c" * 32, "ready", None, 0, 0, None),
    ]
    with engine.begin() as connection:
        for identifier, status, reason, tokens_in, tokens_out, request in rows:
            connection.execute(
                text(f"INSERT INTO ai_texts ({columns}) VALUES (:id, 'notice', 'fr', :hash, 'notice-v3', 'm', :status, :reason, :tin, :tout, 0.01, :req, '2026-11-09 10:00:00', '2026-11-09 10:00:00')"),
                {"id": identifier, "hash": identifier * 2, "status": status, "reason": reason, "tin": tokens_in, "tout": tokens_out, "req": request},
            )
    engine.dispose()
    command.upgrade(config, "head")
    engine = make_engine(url)
    with engine.connect() as connection:
        statuses = dict(connection.execute(text("SELECT reject_reason, status FROM ai_texts WHERE reject_reason IS NOT NULL")).all())
        logged = connection.execute(text("SELECT request_id, reject_reason FROM ai_calls ORDER BY request_id")).all()
    assert statuses == {"encoding": "failed", "forbidden_word": "rejected"}
    assert [tuple(row) for row in logged] == [("req_a", "encoding"), ("req_b", "forbidden_word")]
    engine.dispose()
