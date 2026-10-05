"""Dispatcher: takes queued analyses, downloads them, runs one atelier each, records the results; never opens an archive"""

import logging
import shutil
import signal
import sys
import threading
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from types import FrameType
from typing import Any, Protocol

import docker
import httpx
from docker import DockerClient
from mcplain import __version__
from mcplain.errors import McplainError
from mcplain.fetch.source import ResolvedSource, download_source, resolve_source
from mcplain.inputs import parse_input, parse_selection
from mcplain.models import AnalysisResult, AnalysisStatus, InputKind, InputSpec
from mcplain.verdict import RULES_VERSION
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from mcplain_api.db import RUNNING_STATES, Analysis, AnalysisState, make_engine, make_sessions, utc_now
from mcplain_api.launcher import ATELIER_ERROR, AtelierRun, remove_orphans, run_atelier
from mcplain_api.outcomes import FETCH_ERROR, INTERNAL_ERROR, INTERRUPTED, failure_result
from mcplain_api.settings import Settings

LOGGER = logging.getLogger("mcplain.dispatcher")
IDLE_SECONDS = 1.0
STALE_AFTER = timedelta(minutes=10)
INPUT_FOLDER = "input"
JOB_FOLDER_MODE = 0o700
INPUT_FOLDER_MODE = 0o755
LOG_TEXT_LIMIT = 200
STDERR_LOG_LIMIT = 2000
CACHE_CANDIDATES = 20
GITHUB_KINDS: frozenset[InputKind] = frozenset({InputKind.GITHUB_REPO, InputKind.GITHUB_SUBDIR})
JOB_FAILURE_CODES: frozenset[str] = frozenset(
    {"analyze.job_invalid", "analyze.job_version_mismatch", "analyze.archive_mismatch"}
)
NO_SELECTION = object()


class Launcher(Protocol):
    """Class protocol for what runs ateliers: Docker in production, a fake in the tests"""

    def run(self, input_dir: Path) -> AtelierRun:
        """Run one atelier on a job input folder"""

    def remove_orphans(self) -> int:
        """Remove the ateliers left behind"""


class DockerLauncher:
    """Class that runs ateliers with the Docker SDK"""

    def __init__(self, client: DockerClient, settings: Settings) -> None:
        """Keep the Docker client and the settings"""

        self.client = client
        self.settings = settings

    def run(self, input_dir: Path) -> AtelierRun:
        """Run one hardened atelier on a job input folder"""

        return run_atelier(self.client, input_dir, self.settings)

    def remove_orphans(self) -> int:
        """Remove the ateliers left behind"""

        return remove_orphans(self.client)


@dataclass(frozen=True)
class Claimed:
    """Class that holds what the dispatcher needs from a claimed analysis"""

    id: uuid.UUID
    input_raw: str
    select: str | None


def safe_text(value: object, limit: int = LOG_TEXT_LIMIT) -> str:
    """Cut and escape a text that may come from a third party before it reaches the log"""

    return ascii(str(value)[:limit])


def effective_selection(input_raw: str, selection: str | None) -> object:
    """Return the selection that applies to the downloaded package; a GitHub selection is part of the source key"""

    try:
        spec = parse_input(input_raw)
        if spec.kind in GITHUB_KINDS or not selection:
            return None
        return parse_selection(selection)
    except McplainError:
        return NO_SELECTION


class Dispatcher:
    """Class that empties the queue, with at most MCPLAIN_MAX_PARALLEL analyses at the same time"""

    def __init__(
        self,
        settings: Settings,
        sessions: sessionmaker,
        launcher: Launcher,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Keep the settings, the database sessions and the atelier launcher"""

        self.settings = settings
        self.sessions = sessions
        self.launcher = launcher
        self.transport = transport
        self.stopping = threading.Event()

    def recover(self) -> int:
        """Fail the analyses interrupted for more than 10 minutes and remove the ateliers left behind"""

        now = utc_now()
        stale = now - STALE_AFTER
        gray = failure_result(INTERRUPTED).model_dump(mode="json")
        with self.sessions.begin() as session:
            rows = session.scalars(
                select(Analysis)
                .where(Analysis.state.in_(RUNNING_STATES))
                .where(or_(Analysis.started_at < stale, Analysis.started_at.is_(None)))
                .with_for_update(skip_locked=True)
            ).all()
            identifiers = [row.id for row in rows]
            for row in rows:
                row.state = AnalysisState.FAILED.value
                row.error_code = INTERRUPTED
                row.result = gray
                row.finished_at = now
        for identifier in identifiers:
            shutil.rmtree(self.settings.jobs_dir / str(identifier), ignore_errors=True)
        removed = self.launcher.remove_orphans()
        LOGGER.info("startup: %d interrupted analyses failed, %d orphan ateliers removed", len(identifiers), removed)
        return len(identifiers)

    def claim(self) -> Claimed | None:
        """Take the oldest queued analysis, locked so that another dispatcher skips it, and mark it fetching"""

        with self.sessions.begin() as session:
            row = session.scalars(
                select(Analysis)
                .where(Analysis.state == AnalysisState.QUEUED.value)
                .order_by(Analysis.created_at, Analysis.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if row is None:
                return None
            row.state = AnalysisState.FETCHING.value
            row.started_at = utc_now()
            return Claimed(row.id, row.input_raw, row.select)

    def run_once(self) -> bool:
        """Claim and process one analysis in the current thread; return False when the queue is empty"""

        claimed = self.claim()
        if claimed is None:
            return False
        self.process(claimed)
        return True

    def run_forever(self) -> None:
        """Process the queue until asked to stop, waiting 1 s when it is empty"""

        active: set[Future[None]] = set()
        with ThreadPoolExecutor(max_workers=self.settings.max_parallel) as pool:
            while not self.stopping.is_set():
                active = {future for future in active if not future.done()}
                if len(active) >= self.settings.max_parallel:
                    wait(active, timeout=IDLE_SECONDS, return_when=FIRST_COMPLETED)
                    continue
                try:
                    claimed = self.claim()
                except SQLAlchemyError as error:
                    LOGGER.error("cannot read the queue: %s", type(error).__name__)
                    claimed = None
                if claimed is None:
                    self.stopping.wait(IDLE_SECONDS)
                    continue
                future = pool.submit(self.process, claimed)
                future.add_done_callback(_report_crash)
                active.add(future)

    def stop(self) -> None:
        """Ask the loop to stop after the analyses already started"""

        self.stopping.set()

    def process(self, claimed: Claimed) -> None:
        """Resolve, reuse or download, analyze in an atelier, and record; the job folder is always removed"""

        job_dir = self.settings.jobs_dir / str(claimed.id)
        try:
            self._process(claimed, job_dir)
        except McplainError as error:
            LOGGER.info("analysis %s: download failed with %s", claimed.id, error.code)
            self._record_failure(claimed.id, FETCH_ERROR, failure_result(FETCH_ERROR, error.code, error.params))
        except Exception as error:
            LOGGER.error("analysis %s: internal error %s %s", claimed.id, type(error).__name__, safe_text(error))
            self._record_failure(claimed.id, INTERNAL_ERROR, failure_result(INTERNAL_ERROR))
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    def _process(self, claimed: Claimed, job_dir: Path) -> None:
        """Run the steps of one analysis"""

        LOGGER.info("analysis %s: start %s", claimed.id, safe_text(claimed.input_raw))
        spec = parse_input(claimed.input_raw)
        selection = None
        if claimed.select:
            selection = parse_selection(claimed.select)
        resolved = resolve_source(spec, selection, transport=self.transport)
        self._update(claimed.id, source_key=resolved.source_key)
        cached = self._cached(claimed.id, resolved)
        if cached is not None:
            LOGGER.info("analysis %s: served from the cache for %s", claimed.id, safe_text(resolved.source_key))
            self._record_result(claimed.id, _reuse(cached, resolved, spec))
            return
        job_dir.mkdir(mode=JOB_FOLDER_MODE)
        job_dir.chmod(JOB_FOLDER_MODE)
        input_dir = job_dir / INPUT_FOLDER
        input_dir.mkdir(mode=INPUT_FOLDER_MODE)
        input_dir.chmod(INPUT_FOLDER_MODE)
        job = download_source(resolved, input_dir, transport=self.transport)
        self._update(claimed.id, state=AnalysisState.ANALYZING.value)
        run = self.launcher.run(input_dir)
        if run.result is None:
            code = run.error_code or ATELIER_ERROR
            LOGGER.warning(
                "analysis %s: %s, exit code %s, stderr %s",
                claimed.id,
                code,
                run.exit_code,
                safe_text(run.stderr, STDERR_LOG_LIMIT),
            )
            self._record_failure(claimed.id, code, failure_result(code, source=job.source))
            return
        error = run.result.error
        if run.result.status is AnalysisStatus.ERROR and error is not None and error.code in JOB_FAILURE_CODES:
            LOGGER.warning("analysis %s: the atelier refused the job with %s", claimed.id, safe_text(error.code))
            self._record_failure(claimed.id, ATELIER_ERROR, run.result)
            return
        self._record_result(claimed.id, run.result)

    def _cached(self, identifier: uuid.UUID, resolved: ResolvedSource) -> AnalysisResult | None:
        """Return a finished analysis of the same source, selection, engine and rules, if there is one"""

        with self.sessions() as session:
            rows = session.scalars(
                select(Analysis)
                .where(Analysis.state == AnalysisState.DONE.value)
                .where(Analysis.source_key == resolved.source_key)
                .where(Analysis.engine_version == __version__)
                .where(Analysis.rules_version == RULES_VERSION)
                .where(Analysis.id != identifier)
                .order_by(Analysis.finished_at.desc())
                .limit(CACHE_CANDIDATES)
            ).all()
        for row in rows:
            if effective_selection(row.input_raw, row.select) != resolved.select:
                continue
            try:
                result = AnalysisResult.model_validate(row.result)
            except ValueError:
                continue
            if result.status is not AnalysisStatus.ERROR:
                return result
        return None

    def _update(self, identifier: uuid.UUID, **values: Any) -> None:
        """Change some columns of one analysis"""

        with self.sessions.begin() as session:
            row = session.get(Analysis, identifier)
            if row is None:
                return
            for key, value in values.items():
                setattr(row, key, value)

    def _record_result(self, identifier: uuid.UUID, result: AnalysisResult) -> None:
        """Record a finished analysis"""

        self._finish(identifier, AnalysisState.DONE.value, None, result)
        LOGGER.info("analysis %s: done, %s", identifier, result.verdict.color.value)

    def _record_failure(self, identifier: uuid.UUID, error_code: str, result: AnalysisResult) -> None:
        """Record a failed analysis with its gray result"""

        self._finish(identifier, AnalysisState.FAILED.value, error_code, result)
        LOGGER.info("analysis %s: failed, %s", identifier, error_code)

    def _finish(self, identifier: uuid.UUID, state: str, error_code: str | None, result: AnalysisResult) -> None:
        """Store the final state, the result and the versions of the engine and of the rules"""

        self._update(
            identifier,
            state=state,
            error_code=error_code,
            result=result.model_dump(mode="json"),
            engine_version=__version__,
            rules_version=RULES_VERSION,
            finished_at=utc_now(),
        )


def _reuse(cached: AnalysisResult, resolved: ResolvedSource, spec: InputSpec) -> AnalysisResult:
    """Copy a cached result with the description of the new request: source and ignored arguments"""

    source = resolved.source
    if source.integrity is None and cached.source is not None:
        source = source.model_copy(update={"integrity": cached.source.integrity})
    return cached.model_copy(update={"source": source, "ignored_arguments": list(spec.ignored_arguments)})


def _report_crash(future: Future[None]) -> None:
    """Log an analysis thread that ended with an exception, for example when the database is down"""

    error = future.exception()
    if error is not None:
        LOGGER.error("analysis thread failed: %s %s", type(error).__name__, safe_text(error))


def main() -> int:
    """Run the dispatcher until SIGTERM or SIGINT"""

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings()
    settings.jobs_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.database_url)
    client = docker.from_env()
    dispatcher = Dispatcher(settings, make_sessions(engine), DockerLauncher(client, settings))

    def stop(signal_number: int, frame: FrameType | None) -> None:
        """Stop taking new analyses"""

        LOGGER.info("stopping after the analyses already started")
        dispatcher.stop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOGGER.info(
        "dispatcher started: %d in parallel, atelier %s, GitHub token %s",
        settings.max_parallel,
        safe_text(settings.atelier_image),
        settings.github_token is not None,
    )
    dispatcher.recover()
    dispatcher.run_forever()
    client.close()
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
