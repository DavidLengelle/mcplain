"""Tests of the tokens given back by the dispatcher, of the cache-only requests, and of the one table of failure codes"""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import respx
from helpers import REPOSITORY, altcha_settings
from mcplain.models import AnalysisStatus
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from test_dispatcher import FakeLauncher, clean_result, load, make_dispatcher, mock_registry

from mcplain_api import launcher as launcher_module
from mcplain_api import outcomes
from mcplain_api.analysis_gate import enqueue
from mcplain_api.db import AnalysisToken, Base, QuotaUsage, UserHistory, make_engine, make_sessions
from mcplain_api.launcher import ATELIER_ERROR, ATELIER_INVALID_RESULT, ATELIER_TIMEOUT, AtelierRun
from mcplain_api.quota import Visitor, VisitorKind
from mcplain_api.refunds import GIVE_BACK, KEEP, REFUND_BY_CODE, gives_back, refund_of

ENGINE_SOURCE = REPOSITORY / "engine" / "src" / "mcplain"
API_SOURCE = Path(__file__).resolve().parents[1] / "src" / "mcplain_api"
ENGINE_CODE = re.compile(r'Error\(\s*"([a-z_]+\.[a-z_]+)"')
VISITOR = Visitor(VisitorKind.ACCOUNT, "user:demo", "demo")
INPUT = "npx -y demo-mcp"


@pytest.fixture
def sessions() -> sessionmaker:
    """Return sessions on a fresh in-memory database"""

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_sessions(engine)


@pytest.fixture
def jobs(tmp_path: Path) -> Path:
    """Return an empty jobs folder"""

    folder = tmp_path / "jobs"
    folder.mkdir()
    return folder


def ask(sessions: sessionmaker, limit: int = 10, text: str = INPUT) -> tuple[uuid.UUID, bool]:
    """Create an analysis as the API does, with a token taken from a quota of the given size"""

    settings = altcha_settings(quota_account=limit)
    created = enqueue(sessions, settings, VISITOR, text, None, datetime.now(UTC))
    return created.id, created.cache_only


def used(sessions: sessionmaker) -> int:
    """Return the tokens of the visitor for today"""

    with sessions() as session:
        return session.scalar(select(QuotaUsage.count).where(QuotaUsage.subject == VISITOR.subject)) or 0


def refunded(sessions: sessionmaker, identifier: uuid.UUID) -> bool:
    """Tell whether the token of an analysis was given back"""

    with sessions() as session:
        token = session.get(AnalysisToken, identifier)
    assert token is not None
    return token.refunded_at is not None


@respx.mock
def test_a_real_analysis_keeps_its_token_and_the_cache_gives_it_back(sessions: sessionmaker, jobs: Path) -> None:
    """The first analysis keeps its token; the same package served by the cache gives its token back"""

    mock_registry()
    dispatcher = make_dispatcher(sessions, jobs, FakeLauncher(AtelierRun(clean_result(), None)))
    first, _ = ask(sessions)
    second, _ = ask(sessions)
    assert dispatcher.run_once() and dispatcher.run_once()
    assert load(sessions, second).from_cache
    assert (refunded(sessions, first), refunded(sessions, second)) == (False, True)
    assert used(sessions) == 1


@respx.mock
def test_a_list_of_several_servers_gives_its_token_back(sessions: sessionmaker, jobs: Path) -> None:
    """A link that gives a list of several MCP servers does not count; the click on one of them does"""

    mock_registry()
    listing = clean_result().model_copy(update={"status": AnalysisStatus.MULTIPLE_SERVERS})
    identifier, _ = ask(sessions)
    make_dispatcher(sessions, jobs, FakeLauncher(AtelierRun(listing, None))).run_once()
    assert load(sessions, identifier).state == "done"
    assert refunded(sessions, identifier)
    assert used(sessions) == 0


@respx.mock
@pytest.mark.parametrize("code", [ATELIER_TIMEOUT, ATELIER_INVALID_RESULT, ATELIER_ERROR])
def test_a_failure_of_mcplain_gives_its_token_back(sessions: sessionmaker, jobs: Path, code: str) -> None:
    """An atelier that times out, prints nothing usable or crashes gives the token back"""

    mock_registry()
    identifier, _ = ask(sessions)
    make_dispatcher(sessions, jobs, FakeLauncher(AtelierRun(None, code, "", 1))).run_once()
    assert load(sessions, identifier).error_code == code
    assert refunded(sessions, identifier)
    assert used(sessions) == 0


@respx.mock
@pytest.mark.parametrize(("status", "code", "given_back"), [(404, "fetch.npm_not_found", False), (500, "fetch.http_error", True)])
def test_a_download_error_gives_back_or_keeps_by_its_engine_code(
    sessions: sessionmaker, jobs: Path, status: int, code: str, given_back: bool
) -> None:
    """A package the registry does not know keeps the token; a registry in error gives it back"""

    mock_registry(status=status)
    identifier, _ = ask(sessions)
    make_dispatcher(sessions, jobs, FakeLauncher(AtelierRun(clean_result(), None))).run_once()
    row = load(sessions, identifier)
    assert row.error_code == "fetch_error"
    assert row.result is not None and row.result["error"]["code"] == code
    assert refunded(sessions, identifier) is given_back
    assert used(sessions) == int(not given_back)


@respx.mock
def test_a_token_is_never_given_back_twice(sessions: sessionmaker, jobs: Path) -> None:
    """Finishing the same analysis again does not give a second token back"""

    mock_registry()
    identifier, _ = ask(sessions)
    ask(sessions)
    dispatcher = make_dispatcher(sessions, jobs, FakeLauncher(AtelierRun(None, ATELIER_TIMEOUT, "", 1)))
    dispatcher.run_once()
    assert used(sessions) == 1
    dispatcher._record_failure(identifier, ATELIER_TIMEOUT, outcomes.failure_result(ATELIER_TIMEOUT))
    assert used(sessions) == 1


@respx.mock
def test_at_quota_a_cached_server_is_served_and_an_unknown_one_ends_without_download(
    sessions: sessionmaker, jobs: Path
) -> None:
    """A cache-only request is served by the cache, OSV asked; without cache it ends quota_exhausted, nothing downloaded"""

    tarball = mock_registry()
    launcher = FakeLauncher(AtelierRun(clean_result(), None))
    dispatcher = make_dispatcher(sessions, jobs, launcher)
    ask(sessions, limit=1)
    assert dispatcher.run_once()
    cached, cache_only = ask(sessions, limit=1)
    assert cache_only
    assert dispatcher.run_once()
    served = load(sessions, cached)
    assert (served.state, served.from_cache) == ("done", True)
    assert tarball.call_count == 1
    with sessions.begin() as session:
        session.execute(UserHistory.__table__.delete())
    unknown, cache_only = ask(sessions, limit=1, text="npx -y demo-mcp@0.9.0")
    assert cache_only
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(UserHistory)) == 1
    respx.get("https://registry.npmjs.org/demo-mcp/0.9.0").mock(
        return_value=respx.MockResponse(
            200,
            json={
                "name": "demo-mcp",
                "version": "0.9.0",
                "dist": {"tarball": "https://registry.npmjs.org/demo-mcp/-/demo-mcp-0.9.0.tgz", "integrity": "sha512-AAAA"},
            },
        )
    )
    other_tarball = respx.get("https://registry.npmjs.org/demo-mcp/-/demo-mcp-0.9.0.tgz")
    assert dispatcher.run_once()
    row = load(sessions, unknown)
    assert (row.state, row.result, row.error_code) == ("quota_exhausted", None, None)
    assert other_tarball.call_count == 0
    assert len(launcher.calls) == 1
    assert list(jobs.iterdir()) == []
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(UserHistory)) == 0
        assert session.get(AnalysisToken, unknown) is None
    assert used(sessions) == 1


def emitted_codes() -> set[str]:
    """Return every error code written in the engine and every failure code of the API and of the atelier launcher"""

    codes: set[str] = set()
    for path in ENGINE_SOURCE.rglob("*.py"):
        codes |= set(ENGINE_CODE.findall(path.read_text(encoding="utf-8")))
    codes |= set(outcomes.FAILURE_CODES) - {outcomes.FETCH_ERROR}
    codes |= {launcher_module.ATELIER_TIMEOUT, launcher_module.ATELIER_INVALID_RESULT, launcher_module.ATELIER_ERROR}
    return codes


def test_every_failure_code_is_in_the_one_table() -> None:
    """Each code emitted somewhere has its line in REFUND_BY_CODE, so that an unknown code never happens"""

    codes = emitted_codes()
    assert len(codes) > 60
    assert sorted(codes - set(REFUND_BY_CODE)) == []
    assert sorted(set(REFUND_BY_CODE) - codes) == []


def test_the_table_follows_the_decisions_of_david() -> None:
    """MCPlain or the network gives back; the link keeps; integrity problems give back; an unknown code gives back"""

    for code in ("internal_error", "interrupted", "atelier_timeout", "fetch.timeout", "fetch.github_rate_limited"):
        assert refund_of(code) is GIVE_BACK
    for code in ("fetch.integrity_missing", "fetch.integrity_mismatch"):
        assert refund_of(code) is GIVE_BACK
    for code in ("fetch.not_found", "fetch.host_not_allowed", "fetch.insecure_url", "fetch.bad_redirect", "fetch.too_many_redirects"):
        assert refund_of(code) is KEEP
    for code in ("archive.too_large", "input.reference_not_found", "analyze.subdir_not_found"):
        assert refund_of(code) is KEEP
    assert refund_of("never.seen_before") is GIVE_BACK
    assert refund_of(None) is GIVE_BACK
    for code in ("api.queue_full", "quota_exhausted"):
        assert code not in REFUND_BY_CODE
    assert not gives_back("done", None, {"status": "ok"}, False)
    assert not gives_back("done", None, {"status": "error", "error": {"code": "archive.too_large"}}, False)
    assert gives_back("failed", "fetch_error", {"error": {"code": "fetch.timeout"}}, False)
    assert not gives_back("failed", "fetch_error", {"error": {"code": "fetch.not_found"}}, False)
    assert gives_back("failed", "fetch_error", None, False)
