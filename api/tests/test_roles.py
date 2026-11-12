"""Tests of the PostgreSQL roles on a real database: each service reaches its own tables only, nobody but the counter reads auth"""

import os
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from helpers import altcha_settings
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

from mcplain_api.analysis_gate import enqueue
from mcplain_api.db import AnalysisToken, QuotaUsage, make_engine, make_sessions
from mcplain_api.migrate import set_role_passwords
from mcplain_api.quota import Visitor, VisitorKind

pytestmark = pytest.mark.postgres

ADMIN_URL_VARIABLE = "MCPLAIN_TEST_POSTGRES_URL"
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
TEST_PASSWORDS: dict[str, str] = {
    "mcplain_app": "test-only-app-password-0123456789",
    "mcplain_guichet": "test-only-guichet-password-0123456789",
    "mcplain_facteur": "test-only-facteur-password-0123456789",
}
DENIED = psycopg.errors.InsufficientPrivilege


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """Create a fresh database, migrate it as its owner, give the roles their test passwords, and drop it at the end"""

    admin_url = os.environ.get(ADMIN_URL_VARIABLE)
    if not admin_url:
        pytest.skip(f"set {ADMIN_URL_VARIABLE} to the URL of a PostgreSQL owner")
    url = make_url(admin_url)
    name = "mcplain_roles_" + uuid.uuid4().hex[:12]
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    test_url = url.set(database=name).render_as_string(hide_password=False)
    try:
        config = Config(str(ALEMBIC_INI))
        config.set_main_option("sqlalchemy.url", test_url)
        config.attributes["configure_logger"] = False
        command.upgrade(config, "head")
        engine = make_engine(test_url)
        set_role_passwords(engine, TEST_PASSWORDS)
        engine.dispose()
        yield name
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def connect(database: str, role: str) -> psycopg.Connection:
    """Open an autocommit connection as one service role"""

    url = make_url(os.environ[ADMIN_URL_VARIABLE])
    return psycopg.connect(
        host=url.host, port=url.port or 5432, dbname=database, user=role, password=TEST_PASSWORDS[role], autocommit=True
    )


def denied(connection: psycopg.Connection, statement: str) -> bool:
    """Tell whether PostgreSQL refuses a statement for lack of rights"""

    try:
        connection.execute(statement)
    except DENIED:
        return True
    return False


def test_no_service_role_is_powerful(database: str) -> None:
    """None of the three roles is superuser, may create roles or bypass row security"""

    with connect(database, "mcplain_app") as connection:
        rows = connection.execute(
            "SELECT rolname, rolsuper, rolcreaterole, rolbypassrls FROM pg_roles WHERE rolname LIKE 'mcplain\\_%'"
        ).fetchall()
    assert {row[0] for row in rows} == set(TEST_PASSWORDS)
    assert all(row[1:] == (False, False, False) for row in rows)


def test_the_app_role_never_reads_the_accounts_nor_the_outbox(database: str) -> None:
    """The API, the dispatcher and the writer reach their tables, never the schema auth nor the links of the outbox"""

    with connect(database, "mcplain_app") as connection:
        assert connection.execute("SELECT count(*) FROM analyses").fetchone() == (0,)
        connection.execute("INSERT INTO ip_salts (day, salt, created_at) VALUES ('2026-11-10', 'aa', now())")
        connection.execute("UPDATE ai_admin_alerts SET emailed_at = now()")
        assert denied(connection, 'SELECT * FROM auth."user"')
        assert denied(connection, 'SELECT * FROM auth."account"')
        assert denied(connection, "SELECT * FROM mail_outbox")
        assert denied(connection, "INSERT INTO mail_outbox (id, kind, lang, recipient, link, created_at) VALUES (gen_random_uuid(), 'verify_email', 'en', 'a@example.com', 'http://x', now())")
        assert denied(connection, "CREATE TABLE auth.intruder (id int)")
        assert denied(connection, "SELECT * FROM alembic_version")


def test_the_counter_reads_its_schema_and_only_writes_the_outbox(database: str) -> None:
    """The counter owns auth, adds rows to the outbox, and reads nothing else of public"""

    with connect(database, "mcplain_guichet") as connection:
        assert connection.execute("SHOW search_path").fetchone() == ("auth",)
        connection.execute(
            'INSERT INTO "user" (id, name, email, "emailVerified", "createdAt", "updatedAt") VALUES (\'u1\', \'\', \'a@example.com\', true, now(), now())'
        )
        assert connection.execute('SELECT role FROM "user"').fetchone() == ("user",)
        connection.execute(
            "INSERT INTO public.mail_outbox (id, kind, lang, recipient, link, created_at) VALUES (gen_random_uuid(), 'verify_email', 'fr', 'a@example.com', 'http://localhost:3000/x', now())"
        )
        assert denied(connection, "SELECT * FROM public.mail_outbox")
        assert denied(connection, "DELETE FROM public.mail_outbox")
        assert denied(connection, "SELECT * FROM public.analyses")
        assert denied(connection, "SELECT * FROM public.ai_admin_alerts")
        assert denied(connection, "SELECT * FROM public.ip_salts")


def test_the_role_column_accepts_user_admin_and_bench_only(database: str) -> None:
    """A role other than user, admin or bench is refused by the database itself"""

    with connect(database, "mcplain_guichet") as connection:
        connection.execute(
            'INSERT INTO "user" (id, name, email, "emailVerified", role) VALUES (\'u3\', \'\', \'c@example.com\', true, \'bench\')'
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                'INSERT INTO "user" (id, name, email, "emailVerified", role) VALUES (\'u2\', \'\', \'b@example.com\', true, \'root\')'
            )


def test_the_postman_reads_and_deletes_the_outbox_and_marks_the_alerts(database: str) -> None:
    """The postman reads and deletes mail_outbox, reads the alerts and only sets emailed_at"""

    with connect(database, "mcplain_facteur") as connection:
        assert connection.execute("SELECT count(*) FROM mail_outbox").fetchone() is not None
        connection.execute("DELETE FROM mail_outbox")
        connection.execute("SELECT id, code, created_at FROM ai_admin_alerts")
        connection.execute("UPDATE ai_admin_alerts SET emailed_at = now()")
        assert denied(connection, "UPDATE ai_admin_alerts SET code = 'x'")
        assert denied(connection, "INSERT INTO mail_outbox (id, kind, lang, recipient, link, created_at) VALUES (gen_random_uuid(), 'verify_email', 'en', 'a@example.com', 'http://x', now())")
        assert denied(connection, "SELECT * FROM analyses")
        assert denied(connection, "SELECT * FROM ai_texts")
        assert denied(connection, 'SELECT * FROM auth."user"')


def test_the_app_role_keeps_the_quotas_and_the_counter_never_reads_them(database: str) -> None:
    """The API writes the quotas, the tokens, the burst counts and the history; the counter reads none of them"""

    with connect(database, "mcplain_app") as connection:
        for table in ("quota_usage", "analysis_tokens", "burst_counts", "quota_refusals", "user_history"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with connect(database, "mcplain_guichet") as connection:
        for table in ("quota_usage", "analysis_tokens", "burst_counts", "quota_refusals", "user_history"):
            assert denied(connection, f"SELECT * FROM public.{table}")


def test_take_token_is_atomic_on_postgresql(database: str) -> None:
    """Five simultaneous requests with three tokens left give exactly three counted analyses, as the API role"""

    url = make_url(os.environ[ADMIN_URL_VARIABLE]).set(
        database=database, username="mcplain_app", password=TEST_PASSWORDS["mcplain_app"]
    )
    engine = make_engine(url.render_as_string(hide_password=False))
    sessions = make_sessions(engine)
    settings = altcha_settings(max_queued=100)
    visitor = Visitor(VisitorKind.ANONYMOUS, "ip:" + "e" * 64, None)
    barrier = threading.Barrier(5)
    created: list[bool] = []
    errors: list[BaseException] = []

    def ask() -> None:
        """Wait for the others, then ask for an analysis"""

        try:
            barrier.wait()
            created.append(enqueue(sessions, settings, visitor, "uvx mcp-server-fetch", None, datetime.now(UTC)).cache_only)
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=ask) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    try:
        assert errors == []
        assert sorted(created) == [False, False, False, True, True]
        with sessions() as session:
            assert session.scalar(select(QuotaUsage.count).where(QuotaUsage.subject == visitor.subject)) == 3
            assert session.scalar(select(func.count()).select_from(AnalysisToken).where(AnalysisToken.subject == visitor.subject)) == 3
    finally:
        engine.dispose()
