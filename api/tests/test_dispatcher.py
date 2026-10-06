"""Tests of the dispatcher with SQLite, a simulated network (respx) and a fake atelier launcher"""

import base64
import gzip
import hashlib
import logging
import tarfile
import threading
import time
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import respx
from helpers import ENGINE_FIXTURES, make_settings
from mcplain.analyze import analyze_directory
from mcplain.fetch import archive
from mcplain.fetch.osv import QUERYBATCH_URL
from mcplain.job import read_reputation
from mcplain.models import AnalysisResult, Reputation, VerdictColor
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from mcplain_api import dispatcher as dispatcher_module
from mcplain_api.db import Analysis, AnalysisState, Base, make_engine, make_sessions, utc_now
from mcplain_api.dispatcher import Dispatcher, safe_text
from mcplain_api.launcher import ATELIER_ERROR, ATELIER_INVALID_RESULT, ATELIER_TIMEOUT, AtelierRun

NAME = "demo-mcp"
META = f"https://registry.npmjs.org/{NAME}/latest"
TARBALL = f"https://registry.npmjs.org/{NAME}/-/{NAME}-1.0.0.tgz"
ARCHIVE = b"raw bytes the dispatcher must never open"
JOB_FILES = ["job.json", "reputation.json", "source.tar.gz"]
R11_FIXTURE = ENGINE_FIXTURES / "rules" / "R11" / "positive"


class FakeLauncher:
    """Class that stands for Docker: it records each job folder and gives back a planned outcome"""

    def __init__(self, run: AtelierRun | None = None, error: Exception | None = None) -> None:
        """Remember the planned outcome"""

        self.planned = run
        self.error = error
        self.calls: list[tuple[Path, list[str]]] = []
        self.orphans_removed = 0

    def run(self, input_dir: Path) -> AtelierRun:
        """Record the folder and its files, then give the planned outcome"""

        self.calls.append((input_dir, sorted(path.name for path in input_dir.iterdir())))
        if self.error is not None:
            raise self.error
        assert self.planned is not None
        return self.planned

    def remove_orphans(self) -> int:
        """Count the calls"""

        self.orphans_removed += 1
        return 0


def clean_result() -> AnalysisResult:
    """Return a real result, computed by the test from a fixture, as an atelier would print it"""

    return analyze_directory(ENGINE_FIXTURES / "python_fastmcp_clean")


class Osv:
    """Class that stands for OSV.dev: it answers with the MAL- identifiers chosen by the test and counts the calls"""

    def __init__(self) -> None:
        """Start with a clean package"""

        self.identifiers: list[str] = []
        self.calls = 0

    def answer(self, request: httpx.Request) -> httpx.Response:
        """Answer a querybatch about the one package of the registry mock"""

        self.calls += 1
        result: dict[str, object] = {}
        if self.identifiers:
            result = {"vulns": [{"id": identifier} for identifier in self.identifiers]}
        return httpx.Response(200, json={"results": [result]})


def mock_registry(status: int = 200, osv: Osv | None = None) -> respx.Route:
    """Mock the npm registry and OSV for one small package, and return the tarball route"""

    integrity = "sha512-" + base64.b64encode(hashlib.sha512(ARCHIVE).digest()).decode()
    document = {"name": NAME, "version": "1.0.0", "dist": {"tarball": TARBALL, "integrity": integrity}}
    respx.get(META).mock(return_value=httpx.Response(status, json=document))
    if osv is None:
        osv = Osv()
    respx.post(QUERYBATCH_URL).mock(side_effect=osv.answer)
    return respx.get(TARBALL).mock(return_value=httpx.Response(200, content=ARCHIVE))


def r11_identifiers() -> list[str]:
    """Return the MAL- identifiers of the R11 fixture, read from its reputation.json as data"""

    path = R11_FIXTURE / "reputation.json"
    reputation = Reputation.model_validate_json(path.read_text(encoding="utf-8"))
    return [report.id for package in reputation.packages for report in package.malicious]


class ReputationLauncher(FakeLauncher):
    """Class that analyzes the R11 fixture with the reputation.json of each job, as the atelier would read it"""

    def __init__(self) -> None:
        """Start with no job seen"""

        super().__init__()
        self.fingerprints: list[str] = []

    def run(self, input_dir: Path) -> AtelierRun:
        """Record the job, then analyze the fixture code with the reputation written by the dispatcher"""

        self.calls.append((input_dir, sorted(path.name for path in input_dir.iterdir())))
        self.fingerprints.append(hashlib.sha256((input_dir / "reputation.json").read_bytes()).hexdigest())
        return AtelierRun(analyze_directory(R11_FIXTURE, reputation=read_reputation(input_dir)), None)


def rules(result: AnalysisResult) -> set[str]:
    """Return the rules that raised an alert"""

    return {alert.rule for alert in result.verdict.alerts}


def forbid_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every way of opening an archive fail"""

    def refuse(*args: object, **kwargs: object) -> None:
        """Fail the test if an archive is opened"""

        raise AssertionError("the dispatcher must never open an archive")

    monkeypatch.setattr(archive, "extract_archive", refuse)
    monkeypatch.setattr(tarfile, "open", refuse)
    monkeypatch.setattr(zipfile, "ZipFile", refuse)
    monkeypatch.setattr(gzip, "GzipFile", refuse)


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


def make_dispatcher(sessions: sessionmaker, jobs: Path, launcher: FakeLauncher, parallel: int = 2) -> Dispatcher:
    """Build a dispatcher on the test database and jobs folder"""

    return Dispatcher(make_settings(jobs_dir=jobs, max_parallel=parallel), sessions, launcher)


def queue(sessions: sessionmaker, text: str = f"npx -y {NAME}", **values: object) -> uuid.UUID:
    """Insert a queued analysis"""

    values = {"state": AnalysisState.QUEUED.value, **values}
    with sessions.begin() as session:
        row = Analysis(input_raw=text, **values)
        session.add(row)
        session.flush()
        return row.id


def load(sessions: sessionmaker, identifier: uuid.UUID) -> Analysis:
    """Read one analysis back"""

    with sessions() as session:
        row = session.get(Analysis, identifier)
    assert row is not None
    return row


def gray(row: Analysis) -> AnalysisResult:
    """Check that a stored result is gray and return it"""

    assert row.result is not None
    result = AnalysisResult.model_validate(row.result)
    assert result.verdict.color is VerdictColor.GRAY
    return result


@respx.mock
def test_success_records_the_result_and_removes_the_folder(
    sessions: sessionmaker, jobs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The archive is downloaded raw, given to one atelier, the result is recorded, the folder removed"""

    tarball = mock_registry()
    launcher = FakeLauncher(AtelierRun(clean_result(), None))
    identifier = queue(sessions)
    forbid_extraction(monkeypatch)
    assert make_dispatcher(sessions, jobs, launcher).run_once()
    row = load(sessions, identifier)
    assert (row.state, row.error_code, row.source_key) == ("done", None, f"npm:{NAME}@1.0.0")
    assert row.result == clean_result().model_dump(mode="json")
    assert (row.engine_version, row.rules_version) == ("0.1.0", "1")
    assert row.started_at is not None and row.finished_at is not None
    assert launcher.calls == [(jobs / str(identifier) / "input", JOB_FILES)]
    assert tarball.call_count == 1
    assert list(jobs.iterdir()) == []


@respx.mock
def test_same_package_is_served_from_the_cache(sessions: sessionmaker, jobs: Path) -> None:
    """A second request for the same version copies the result without download and without atelier"""

    tarball = mock_registry()
    launcher = FakeLauncher(AtelierRun(clean_result(), None))
    dispatcher = make_dispatcher(sessions, jobs, launcher)
    first = queue(sessions)
    second = queue(sessions, f"npx {NAME} ~/Desktop --port 3000")
    assert dispatcher.run_once() and dispatcher.run_once()
    assert len(launcher.calls) == 1
    assert tarball.call_count == 1
    cached = load(sessions, second)
    assert cached.state == "done"
    assert cached.source_key == load(sessions, first).source_key
    result = AnalysisResult.model_validate(cached.result)
    assert result.ignored_arguments == ["~/Desktop", "--port", "3000"]
    assert result.verdict == clean_result().verdict


@respx.mock
def test_osv_is_asked_again_and_an_unchanged_reputation_uses_the_cache(sessions: sessionmaker, jobs: Path) -> None:
    """OSV is asked at each request; with the same answer the cache serves, keyed by the reputation.json sha256"""

    osv = Osv()
    tarball = mock_registry(osv=osv)
    launcher = ReputationLauncher()
    dispatcher = make_dispatcher(sessions, jobs, launcher)
    first = queue(sessions)
    second = queue(sessions)
    assert dispatcher.run_once() and dispatcher.run_once()
    assert osv.calls == 2
    assert (len(launcher.calls), tarball.call_count) == (1, 1)
    rows = [load(sessions, first), load(sessions, second)]
    assert [row.state for row in rows] == ["done", "done"]
    assert [row.reputation_sha256 for row in rows] == launcher.fingerprints * 2
    assert AnalysisResult.model_validate(rows[1].result).verdict == AnalysisResult.model_validate(rows[0].result).verdict


@respx.mock
def test_new_malicious_report_gives_a_new_analysis_and_r11(sessions: sessionmaker, jobs: Path) -> None:
    """When OSV starts listing the version as malicious, the cache is skipped and the new verdict is red R11"""

    osv = Osv()
    tarball = mock_registry(osv=osv)
    launcher = ReputationLauncher()
    dispatcher = make_dispatcher(sessions, jobs, launcher)
    first = queue(sessions)
    assert dispatcher.run_once()
    osv.identifiers = r11_identifiers()
    second = queue(sessions)
    assert dispatcher.run_once()
    assert osv.calls == 2
    assert (len(launcher.calls), tarball.call_count) == (2, 2)
    before = AnalysisResult.model_validate(load(sessions, first).result)
    after = AnalysisResult.model_validate(load(sessions, second).result)
    assert before.verdict.color is not VerdictColor.RED and "R11" not in rules(before)
    assert after.verdict.color is VerdictColor.RED and "R11" in rules(after)
    assert load(sessions, second).reputation_sha256 == launcher.fingerprints[1] != launcher.fingerprints[0]


@respx.mock
def test_other_selection_is_not_served_from_the_cache(sessions: sessionmaker, jobs: Path) -> None:
    """The same package with another selected server is analyzed again"""

    mock_registry()
    launcher = FakeLauncher(AtelierRun(clean_result(), None))
    dispatcher = make_dispatcher(sessions, jobs, launcher)
    queue(sessions)
    queue(sessions, select="src/a")
    assert dispatcher.run_once() and dispatcher.run_once()
    assert len(launcher.calls) == 2


@respx.mock
def test_gray_error_results_are_not_reused(sessions: sessionmaker, jobs: Path) -> None:
    """A finished analysis whose result is an error is analyzed again"""

    mock_registry()
    broken = AnalysisResult.model_validate(
        {**clean_result().model_dump(mode="json"), "status": "error", "error": {"code": "archive.corrupted"}}
    )
    launcher = FakeLauncher(AtelierRun(broken, None))
    dispatcher = make_dispatcher(sessions, jobs, launcher)
    queue(sessions)
    queue(sessions)
    assert dispatcher.run_once() and dispatcher.run_once()
    assert len(launcher.calls) == 2


@respx.mock
def test_download_error_fails_gray_with_the_engine_code(sessions: sessionmaker, jobs: Path) -> None:
    """A package the registry does not know gives failed, fetch_error, and the engine code in the result"""

    mock_registry(status=404)
    launcher = FakeLauncher(AtelierRun(clean_result(), None))
    identifier = queue(sessions)
    make_dispatcher(sessions, jobs, launcher).run_once()
    row = load(sessions, identifier)
    assert (row.state, row.error_code) == ("failed", "fetch_error")
    result = gray(row)
    assert result.error is not None and result.error.code == "fetch.npm_not_found"
    assert launcher.calls == []
    assert list(jobs.iterdir()) == []


@respx.mock
@pytest.mark.parametrize("code", [ATELIER_TIMEOUT, ATELIER_INVALID_RESULT, ATELIER_ERROR])
def test_atelier_failures_fail_gray(sessions: sessionmaker, jobs: Path, code: str) -> None:
    """Each atelier failure gives failed, its code, a gray result, and the folder is removed"""

    mock_registry()
    launcher = FakeLauncher(AtelierRun(None, code, "\x1b[2J" + "e" * 5000, 1))
    identifier = queue(sessions)
    make_dispatcher(sessions, jobs, launcher).run_once()
    row = load(sessions, identifier)
    assert (row.state, row.error_code) == ("failed", code)
    result = gray(row)
    assert result.error is not None and result.error.code == f"job.{code}"
    assert result.source is not None and result.source.name == NAME
    assert list(jobs.iterdir()) == []


@respx.mock
def test_job_refused_by_the_atelier_fails_gray(sessions: sessionmaker, jobs: Path) -> None:
    """A job the atelier refuses, for example for another engine version, is failed and never cached"""

    mock_registry()
    refused = AnalysisResult.model_validate(
        {
            **clean_result().model_dump(mode="json"),
            "status": "error",
            "servers": [],
            "error": {"code": "analyze.job_version_mismatch"},
            "verdict": {"color": "gray"},
        }
    )
    identifier = queue(sessions)
    make_dispatcher(sessions, jobs, FakeLauncher(AtelierRun(refused, None))).run_once()
    row = load(sessions, identifier)
    assert (row.state, row.error_code) == ("failed", ATELIER_ERROR)
    gray(row)


@respx.mock
def test_unexpected_exception_fails_gray_and_removes_the_folder(sessions: sessionmaker, jobs: Path) -> None:
    """A crash of the dispatcher code gives failed, internal_error, and the folder is still removed"""

    mock_registry()
    launcher = FakeLauncher(error=RuntimeError("boom"))
    identifier = queue(sessions)
    make_dispatcher(sessions, jobs, launcher).run_once()
    row = load(sessions, identifier)
    assert (row.state, row.error_code) == ("failed", "internal_error")
    result = gray(row)
    assert result.error is not None and result.error.code == "job.internal_error"
    assert len(launcher.calls) == 1
    assert list(jobs.iterdir()) == []


def test_interrupted_analyses_are_failed_at_startup(sessions: sessionmaker, jobs: Path) -> None:
    """Analyses fetching or analyzing for more than 10 minutes become failed interrupted; recent ones stay"""

    old = utc_now() - timedelta(minutes=11)
    recent = utc_now() - timedelta(minutes=1)
    fetching = queue(sessions, state=AnalysisState.FETCHING.value, started_at=old)
    analyzing = queue(sessions, state=AnalysisState.ANALYZING.value, started_at=old)
    running = queue(sessions, state=AnalysisState.ANALYZING.value, started_at=recent)
    waiting = queue(sessions)
    (jobs / str(fetching) / "input").mkdir(parents=True)
    launcher = FakeLauncher()
    assert make_dispatcher(sessions, jobs, launcher).recover() == 2
    for identifier in (fetching, analyzing):
        row = load(sessions, identifier)
        assert (row.state, row.error_code) == ("failed", "interrupted")
        result = gray(row)
        assert result.error is not None and result.error.code == "job.interrupted"
    assert load(sessions, running).state == "analyzing"
    assert load(sessions, waiting).state == "queued"
    assert launcher.orphans_removed == 1
    assert list(jobs.iterdir()) == []


def test_oldest_analysis_is_claimed_first(sessions: sessionmaker, jobs: Path) -> None:
    """The queue is first in, first out, and a claimed analysis is marked fetching"""

    first = queue(sessions, created_at=utc_now() - timedelta(seconds=5))
    queue(sessions)
    claimed = make_dispatcher(sessions, jobs, FakeLauncher()).claim()
    assert claimed is not None and claimed.id == first
    assert load(sessions, first).state == "fetching"


def test_empty_queue_claims_nothing(sessions: sessionmaker, jobs: Path) -> None:
    """With nothing queued, run_once does nothing"""

    assert make_dispatcher(sessions, jobs, FakeLauncher()).run_once() is False


def test_claim_skips_locked_rows_on_postgresql() -> None:
    """On PostgreSQL the claim query takes the row with FOR UPDATE SKIP LOCKED"""

    statement = (
        dispatcher_module.select(Analysis)
        .where(Analysis.state == AnalysisState.QUEUED.value)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    assert "FOR UPDATE SKIP LOCKED" in str(statement.compile(dialect=postgresql.dialect()))


class BlockingLauncher(FakeLauncher):
    """Class that keeps each atelier busy until the test releases it, and counts how many run together"""

    def __init__(self) -> None:
        """Start with no atelier running"""

        super().__init__(AtelierRun(clean_result(), None))
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.running = 0
        self.most = 0

    def run(self, input_dir: Path) -> AtelierRun:
        """Wait for the release while counting the ateliers running together"""

        with self.lock:
            self.running += 1
            self.most = max(self.most, self.running)
        self.release.wait(10)
        with self.lock:
            self.running -= 1
        return super().run(input_dir)


@respx.mock
def test_at_most_max_parallel_analyses_run_together(tmp_path: Path, jobs: Path) -> None:
    """With MCPLAIN_MAX_PARALLEL=2 and 3 different packages, the third waits for a free place"""

    engine = make_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    Base.metadata.create_all(engine)
    sessions = make_sessions(engine)
    launcher = BlockingLauncher()
    names = ["alpha-mcp", "beta-mcp", "gamma-mcp"]
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(ARCHIVE).digest()).decode()
    for name in names:
        tarball = f"https://registry.npmjs.org/{name}/-/{name}-1.0.0.tgz"
        document = {"name": name, "version": "1.0.0", "dist": {"tarball": tarball, "integrity": integrity}}
        respx.get(f"https://registry.npmjs.org/{name}/latest").mock(return_value=httpx.Response(200, json=document))
        respx.get(tarball).mock(return_value=httpx.Response(200, content=ARCHIVE))
    respx.post(QUERYBATCH_URL).mock(return_value=httpx.Response(200, json={"results": [{}]}))
    identifiers = [queue(sessions, f"npx {name}") for name in names]
    dispatcher = make_dispatcher(sessions, jobs, launcher, parallel=2)
    loop = threading.Thread(target=dispatcher.run_forever)
    loop.start()
    try:
        deadline = time.monotonic() + 10
        while launcher.running < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(0.3)
        assert launcher.running == 2
        assert load(sessions, identifiers[2]).state == "queued"
        launcher.release.set()
        while time.monotonic() < deadline and any(load(sessions, item).state != "done" for item in identifiers):
            time.sleep(0.05)
    finally:
        launcher.release.set()
        dispatcher.stop()
        loop.join(10)
    assert launcher.most == 2
    assert [load(sessions, item).state for item in identifiers] == ["done", "done", "done"]


def test_third_party_text_is_cut_and_escaped() -> None:
    """Escape sequences, line breaks and invisible characters never reach the log as they are"""

    text = safe_text("evil\x1b[2J\nnext line\u202e" + "x" * 1000)
    assert "\x1b" not in text and "\n" not in text and "\u202e" not in text
    assert len(text) < 260


@respx.mock
def test_atelier_stderr_is_logged_escaped(sessions: sessionmaker, jobs: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The error output of a failed atelier is logged cut to 2000 characters and escaped"""

    mock_registry()
    launcher = FakeLauncher(AtelierRun(None, ATELIER_ERROR, "\x1b[2J" + "e" * 1990, 1))
    queue(sessions)
    with caplog.at_level(logging.INFO, logger="mcplain.dispatcher"):
        make_dispatcher(sessions, jobs, launcher).run_once()
    messages = [record.getMessage() for record in caplog.records]
    stderr_lines = [message for message in messages if "stderr" in message]
    assert stderr_lines
    assert all("\x1b" not in message for message in messages)
    assert "\\x1b[2J" in stderr_lines[0]
