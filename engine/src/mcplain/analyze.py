"""Pipeline: resolve and download a source, then analyze the job folder offline: detection, adapter and verdict"""

import shutil
import tempfile
from pathlib import Path

import httpx

from mcplain.adapters import adapter_for
from mcplain.config import DEFAULT_LIMITS, Limits
from mcplain.detect import detect
from mcplain.errors import McplainError
from mcplain.fetch.archive import extract_archive
from mcplain.fetch.source import download_source, resolve_source
from mcplain.inputs import parse_input, parse_selection
from mcplain.job import read_job, read_reputation, verified_archive
from mcplain.models import (
    AnalysisResult,
    AnalysisStatus,
    AnalyzedSource,
    ErrorInfo,
    Reputation,
    ReputationStatus,
    Verdict,
    VerdictColor,
)
from mcplain.verdict import compute_verdict

WORKDIR_PREFIX = "mcplain-"
INPUT_FOLDER = "input"
WORK_FOLDER = "work"
EXTRACT_FOLDER = "source"


def not_checked() -> Reputation:
    """Return the reputation of a local analysis, which never uses the network"""

    return Reputation(status=ReputationStatus.NOT_CHECKED)


def _join(first: str | None, second: str | None) -> str | None:
    """Join two optional relative folder paths"""

    parts = [part for part in (first, second) if part]
    if not parts:
        return None
    return "/".join(parts)


def _relative_to(path: str, folder: str) -> str:
    """Express a root-relative path relative to a server folder"""

    if folder == "." or not path.startswith(folder + "/"):
        return path
    return path[len(folder) + 1:]


def _finish(result: AnalysisResult) -> AnalysisResult:
    """Compute and attach the verdict"""

    result.verdict = compute_verdict(result)
    return result


def _placeholder_verdict() -> Verdict:
    """Return the verdict used before the real one is computed"""

    return Verdict(color=VerdictColor.GRAY)


def error_result(error: McplainError, source: AnalyzedSource | None = None) -> AnalysisResult:
    """Build the result of an analysis that stopped on an error"""

    result = AnalysisResult(
        status=AnalysisStatus.ERROR,
        source=source,
        error=ErrorInfo(code=error.code, params=error.params),
        verdict=_placeholder_verdict(),
    )
    return _finish(result)


def analyze_directory(
    path: Path,
    source: AnalyzedSource | None = None,
    subdir: str | None = None,
    select: str | None = None,
    limits: Limits = DEFAULT_LIMITS,
    reputation: Reputation | None = None,
) -> AnalysisResult:
    """Analyze a local folder; this step never uses the network, the reputation is given as data"""

    root = Path(path)
    if not root.is_dir():
        return error_result(McplainError("analyze.not_a_directory", path=str(path)), source)
    try:
        detection = detect(root, _join(subdir, select), limits)
    except McplainError as error:
        return error_result(error, source)
    result = AnalysisResult(
        status=detection.status,
        source=source,
        available_servers=detection.candidates,
        available_servers_truncated=detection.truncated,
        language=detection.language,
        compiled_files=detection.compiled_files,
        notes=detection.notes,
        reputation=reputation,
        verdict=_placeholder_verdict(),
    )
    if detection.status is not AnalysisStatus.OK or detection.server is None:
        if detection.status is not AnalysisStatus.MULTIPLE_SERVERS:
            result.available_servers = []
        return _finish(result)
    server = detection.server
    adapter = adapter_for(server.language, limits)
    if adapter is None:
        result.status = AnalysisStatus.UNSUPPORTED_LANGUAGE
        result.language = server.language
        return _finish(result)
    server_dir = root
    if server.path != ".":
        server_dir = root.joinpath(*server.path.split("/"))
    analysis = adapter.analyze(server_dir)
    analysis.path = server.path
    analysis.name = server.name
    analysis.sdk = server.sdk
    analysis.compiled_files = [_relative_to(path, server.path) for path in detection.compiled_files]
    result.servers = [analysis]
    result.available_servers = []
    if detection.binary_signals and not analysis.tools:
        result.status = AnalysisStatus.COMPILED
    return _finish(result)


def analyze_job(job_input_dir: Path, work_dir: Path, limits: Limits = DEFAULT_LIMITS) -> AnalysisResult:
    """Analyze a job folder without network: check job.json and the archive, extract it into work_dir, analyze"""

    try:
        job = read_job(job_input_dir, limits)
    except McplainError as error:
        return error_result(error)
    try:
        archive = verified_archive(job_input_dir, job)
        root = extract_archive(archive, work_dir / EXTRACT_FOLDER, limits)
    except McplainError as error:
        result = error_result(error, job.source)
    else:
        result = analyze_directory(
            root,
            source=job.source,
            subdir=job.source.subdir,
            select=job.select,
            limits=limits,
            reputation=read_reputation(job_input_dir, limits),
        )
    result.ignored_arguments = list(job.spec.ignored_arguments)
    return result


def analyze_input(
    text: str,
    select: str | None = None,
    limits: Limits = DEFAULT_LIMITS,
    transport: httpx.BaseTransport | None = None,
) -> AnalysisResult:
    """Run the whole pipeline on what the user pasted: resolve, download, then analyze in a temporary folder"""

    ignored: list[str] = []
    try:
        spec = parse_input(text)
        ignored = spec.ignored_arguments
        selection = None
        if select:
            selection = parse_selection(select)
        resolved = resolve_source(spec, selection, limits, transport)
        workdir = Path(tempfile.mkdtemp(prefix=WORKDIR_PREFIX))
        try:
            job_input_dir = workdir / INPUT_FOLDER
            job_input_dir.mkdir()
            download_source(resolved, job_input_dir, limits, transport)
            result = analyze_job(job_input_dir, workdir / WORK_FOLDER, limits)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    except McplainError as error:
        result = error_result(error)
    result.ignored_arguments = ignored
    return result
