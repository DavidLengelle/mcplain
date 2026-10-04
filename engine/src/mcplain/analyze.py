"""Pipeline: input, download, detection, adapter and verdict"""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

import httpx

from mcplain.adapters import adapter_for
from mcplain.config import DEFAULT_LIMITS, Limits
from mcplain.dependencies import direct_dependencies
from mcplain.detect import detect
from mcplain.errors import FetchError, McplainError
from mcplain.fetch import github, npm, pypi
from mcplain.fetch.archive import extract_archive
from mcplain.fetch.http import SafeClient
from mcplain.fetch.osv import PackageQuery, check_reputation
from mcplain.fetch.resolve import (
    NPM_REGISTRY,
    match_links,
    npm_links,
    published_candidate,
    pypi_links,
)
from mcplain.inputs import add_subdir, parse_input, parse_selection, resolve_tree_reference
from mcplain.models import (
    AnalysisResult,
    AnalysisStatus,
    AnalyzedSource,
    ErrorInfo,
    InputKind,
    InputSpec,
    Reputation,
    ReputationStatus,
    SourceKind,
    SourceOrigin,
    Verdict,
    VerdictColor,
)
from mcplain.verdict import compute_verdict

WORKDIR_PREFIX = "mcplain-"
GITHUB_ARTIFACT = "github_tarball"
NPM_ARTIFACT = "npm_tarball"
LATEST_LABEL = "latest"
NOT_PUBLISHED_CODES: frozenset[str] = frozenset({"fetch.npm_not_found", "fetch.pypi_not_found"})
PACKAGE_ECOSYSTEMS: dict[SourceKind, str] = {SourceKind.NPM: "npm", SourceKind.PYPI: "PyPI"}


@dataclass(frozen=True)
class FetchedSource:
    """Class that points to downloaded code ready for offline analysis"""

    root: Path
    subdir: str | None
    source: AnalyzedSource
    reputation: Reputation | None = None


@contextmanager
def fetch_source(
    spec: InputSpec,
    limits: Limits = DEFAULT_LIMITS,
    transport: httpx.BaseTransport | None = None,
    select: str | None = None,
) -> Iterator[FetchedSource]:
    """Download and extract a source into a temporary folder removed afterwards, then check its reputation"""

    workdir = Path(tempfile.mkdtemp(prefix=WORKDIR_PREFIX))
    try:
        with SafeClient(limits, github.github_host_headers(), transport) as client:
            if spec.kind is InputKind.NPM:
                fetched = _fetch_npm(client, spec.package or "", spec.version, workdir, limits)
            elif spec.kind is InputKind.PYPI:
                fetched = _fetch_pypi(client, spec.package or "", spec.version, workdir, limits)
            else:
                fetched = _fetch_github(client, spec, workdir, limits)
            fetched = replace(fetched, reputation=_reputation(client, fetched, select, limits))
        yield fetched
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _fetch_npm(
    client: SafeClient,
    name: str,
    version: str | None,
    workdir: Path,
    limits: Limits,
    reason: str = "source.requested_package",
    repository: str | None = None,
    revision: str | None = None,
    reference: str | None = None,
) -> FetchedSource:
    """Download, verify and extract an npm package"""

    release = npm.fetch_release(client, name, version)
    requested = version or LATEST_LABEL
    requested_version = None
    if requested != release.version:
        requested_version = requested
    download = npm.download_release(client, release, workdir / "package.tgz")
    root = extract_archive(download.path, workdir / "package", limits)
    source = AnalyzedSource(
        kind=SourceKind.NPM,
        name=release.name,
        version=release.version,
        requested_version=requested_version,
        revision=revision,
        reference=reference,
        integrity=release.integrity,
        url=release.tarball,
        artifact=NPM_ARTIFACT,
        origin=SourceOrigin.PUBLISHED_PACKAGE,
        reason=reason,
        repository=repository,
    )
    return FetchedSource(root, None, source)


def _fetch_pypi(
    client: SafeClient,
    name: str,
    version: str | None,
    workdir: Path,
    limits: Limits,
    reason: str = "source.requested_package",
    repository: str | None = None,
    revision: str | None = None,
    reference: str | None = None,
) -> FetchedSource:
    """Download, verify and extract a PyPI release"""

    release = pypi.fetch_release(client, name, version)
    requested_version = None
    if version is None:
        requested_version = LATEST_LABEL
    download = pypi.download_release(client, release, workdir / release.filename.replace("/", "_"))
    root = extract_archive(download.path, workdir / "package", limits)
    source = AnalyzedSource(
        kind=SourceKind.PYPI,
        name=release.name,
        version=release.version,
        requested_version=requested_version,
        revision=revision,
        reference=reference,
        integrity=f"sha256:{release.sha256}",
        url=release.url,
        artifact=release.artifact,
        origin=SourceOrigin.PUBLISHED_PACKAGE,
        reason=reason,
        repository=repository,
    )
    return FetchedSource(root, None, source)


def _fetch_github(client: SafeClient, spec: InputSpec, workdir: Path, limits: Limits) -> FetchedSource:
    """Download a GitHub commit, then prefer the matching published package"""

    source_api = github.GitHubSource(client)
    info = source_api.repository(spec.owner or "", spec.repo or "")
    owner, repo = info.owner, info.repo
    spec = resolve_tree_reference(spec, lambda ref: source_api.resolve_commit(owner, repo, ref) is not None)
    reference = spec.ref or info.default_branch
    sha = source_api.resolve_commit(owner, repo, reference)
    if sha is None:
        raise FetchError("fetch.github_ref_not_found", reference=reference)
    download = source_api.download(owner, repo, sha, workdir / "repo.tar.gz")
    root = extract_archive(download.path, workdir / "repo", limits)
    url = f"https://github.com/{owner}/{repo}/tree/{sha}"
    if spec.subdir:
        url = f"{url}/{spec.subdir}"
    github_source = AnalyzedSource(
        kind=SourceKind.GITHUB,
        name=f"{owner}/{repo}",
        revision=sha,
        reference=reference,
        subdir=spec.subdir,
        integrity=f"sha256:{download.sha256}",
        url=url,
        artifact=GITHUB_ARTIFACT,
        origin=SourceOrigin.GITHUB_CODE,
        reason="source.no_single_server",
    )
    detection = detect(root, spec.subdir, limits)
    if detection.status is not AnalysisStatus.OK or detection.server is None:
        return FetchedSource(root, spec.subdir, github_source)
    server_path = detection.server.path
    server_dir = root
    subdir = None
    if server_path != ".":
        server_dir = root.joinpath(*server_path.split("/"))
        subdir = server_path
    candidate, reason = published_candidate(server_dir)
    if candidate is None:
        return FetchedSource(root, spec.subdir, github_source.model_copy(update={"reason": reason}))
    try:
        if candidate.registry == NPM_REGISTRY:
            npm_release = npm.fetch_release(client, candidate.name, None)
            links = npm_links(npm_release.manifest)
        else:
            pypi_release = pypi.fetch_release(client, candidate.name, None)
            links = pypi_links(pypi_release.info)
    except FetchError as error:
        if error.code in NOT_PUBLISHED_CODES:
            update = {"reason": "source.package_not_published"}
            return FetchedSource(root, spec.subdir, github_source.model_copy(update=update))
        raise
    outcome = match_links(links, owner, repo, subdir)
    if not outcome.matched:
        return FetchedSource(root, spec.subdir, github_source.model_copy(update={"reason": outcome.reason}))
    repository = f"{owner}/{repo}"
    if candidate.registry == NPM_REGISTRY:
        return _fetch_npm(client, candidate.name, None, workdir, limits, outcome.reason, repository, sha, reference)
    return _fetch_pypi(client, candidate.name, None, workdir, limits, outcome.reason, repository, sha, reference)


def _reputation(client: SafeClient, fetched: FetchedSource, select: str | None, limits: Limits) -> Reputation:
    """Query OSV.dev for the analyzed package at its exact version and for its direct dependencies by name"""

    queries: list[PackageQuery] = []
    source = fetched.source
    ecosystem = PACKAGE_ECOSYSTEMS.get(source.kind)
    if ecosystem is not None and source.version:
        queries.append(PackageQuery(source.name, ecosystem, source.version, False))
    try:
        detection = detect(fetched.root, _join(fetched.subdir, select), limits)
    except McplainError:
        detection = None
    if detection is not None and detection.server is not None:
        folder = fetched.root
        if detection.server.path != ".":
            folder = fetched.root.joinpath(*detection.server.path.split("/"))
        dependency_ecosystem, names = direct_dependencies(folder, detection.server.language)
        if dependency_ecosystem is not None:
            queries.extend(PackageQuery(name, dependency_ecosystem, None, True) for name in names)
    return check_reputation(client, queries, limits)


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

    return Verdict(color=VerdictColor.GRAY, provisional=True)


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


def analyze_input(
    text: str,
    select: str | None = None,
    limits: Limits = DEFAULT_LIMITS,
    transport: httpx.BaseTransport | None = None,
) -> AnalysisResult:
    """Run the whole pipeline on what the user pasted"""

    ignored: list[str] = []
    try:
        spec = parse_input(text)
        ignored = spec.ignored_arguments
        selection = None
        if select:
            selection = parse_selection(select)
        if selection and spec.kind in (InputKind.GITHUB_REPO, InputKind.GITHUB_SUBDIR):
            spec = add_subdir(spec, selection)
            selection = None
        with fetch_source(spec, limits, transport, selection) as fetched:
            result = analyze_directory(
                fetched.root,
                source=fetched.source,
                subdir=fetched.subdir,
                select=selection,
                limits=limits,
                reputation=fetched.reputation,
            )
    except McplainError as error:
        result = error_result(error)
    result.ignored_arguments = ignored
    return result
