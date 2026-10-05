"""Network steps of an analysis: resolve a source from metadata, then download its raw archive; never extracts"""

import hmac
from dataclasses import dataclass
from pathlib import Path

import httpx

from mcplain import __version__
from mcplain.config import DEFAULT_LIMITS, Limits
from mcplain.dependencies import (
    NPM_ECOSYSTEM,
    PYPI_ECOSYSTEM,
    npm_dependency_names,
    pypi_dependency_names,
    pyproject_dependency_names,
)
from mcplain.errors import ArchiveError, DetectionError, FetchError
from mcplain.fetch import github, npm, pypi
from mcplain.fetch.http import Download, SafeClient
from mcplain.fetch.osv import PackageQuery, check_reputation
from mcplain.fetch.resolve import (
    NPM_REGISTRY,
    ManifestFiles,
    match_links,
    npm_links,
    published_candidate,
    pypi_links,
)
from mcplain.inputs import add_subdir, normalize_pypi_name, resolve_tree_reference
from mcplain.job import archive_name, write_job
from mcplain.manifests import parse_json_object, parse_setup_cfg, parse_toml
from mcplain.models import (
    AnalyzedSource,
    ArchiveFormat,
    InputKind,
    InputSpec,
    JobFile,
    Reputation,
    SourceKind,
    SourceOrigin,
)
from mcplain.verdict import RULES_VERSION

GITHUB_ARTIFACT = "github_tarball"
NPM_ARTIFACT = "npm_tarball"
LATEST_LABEL = "latest"
NOT_PUBLISHED_CODES: frozenset[str] = frozenset({"fetch.npm_not_found", "fetch.pypi_not_found"})
GITHUB_KINDS: frozenset[InputKind] = frozenset({InputKind.GITHUB_REPO, InputKind.GITHUB_SUBDIR})
PACKAGE_JSON = "package.json"
PYPROJECT = "pyproject.toml"
SETUP_CFG = "setup.cfg"
ZIP_SUFFIXES: tuple[str, ...] = (".whl", ".zip")
TAR_GZ_SUFFIXES: tuple[str, ...] = (".tar.gz", ".tgz")
TAR_SUFFIX = ".tar"


@dataclass(frozen=True)
class ResolvedSource:
    """Class that says what to download and why, decided from metadata only"""

    spec: InputSpec
    select: str | None
    source: AnalyzedSource
    source_key: str
    download_url: str
    archive_format: ArchiveFormat
    expected_sha256: str | None = None
    expected_sha512: bytes | None = None
    queries: tuple[PackageQuery, ...] = ()


def resolve_source(
    spec: InputSpec,
    select: str | None = None,
    limits: Limits = DEFAULT_LIMITS,
    transport: httpx.BaseTransport | None = None,
) -> ResolvedSource:
    """Find the exact version or commit to analyze and the file to download, reading metadata only"""

    if select and spec.kind in GITHUB_KINDS:
        spec = add_subdir(spec, select)
        select = None
    with SafeClient(limits, github.github_host_headers(), transport) as client:
        if spec.kind is InputKind.NPM:
            release = npm.fetch_release(client, spec.package or "", spec.version)
            return _npm_source(spec, select, release, _requested_npm(spec.version, release.version))
        if spec.kind is InputKind.PYPI:
            pypi_release = pypi.fetch_release(client, spec.package or "", spec.version)
            return _pypi_source(spec, select, pypi_release, _requested_pypi(spec.version))
        return _resolve_github(client, spec, limits)


def check_source_reputation(
    resolved: ResolvedSource,
    limits: Limits = DEFAULT_LIMITS,
    transport: httpx.BaseTransport | None = None,
) -> Reputation:
    """Ask OSV.dev about the resolved package and its direct dependencies, without downloading anything"""

    with SafeClient(limits, github.github_host_headers(), transport) as client:
        return check_reputation(client, list(resolved.queries), limits)


def download_source(
    resolved: ResolvedSource,
    job_input_dir: Path,
    limits: Limits = DEFAULT_LIMITS,
    transport: httpx.BaseTransport | None = None,
    reputation: Reputation | None = None,
) -> JobFile:
    """Stream the raw archive into a job folder, check its digest, ask OSV unless given, write job.json; never extracts"""

    archive = job_input_dir / archive_name(resolved.archive_format)
    with SafeClient(limits, github.github_host_headers(), transport) as client:
        download = client.download(resolved.download_url, archive)
        try:
            _check_digest(resolved, download)
        except FetchError:
            archive.unlink(missing_ok=True)
            raise
        if reputation is None:
            reputation = check_reputation(client, list(resolved.queries), limits)
    source = resolved.source
    if source.integrity is None:
        source = source.model_copy(update={"integrity": f"sha256:{download.sha256}"})
    job = JobFile(
        spec=resolved.spec,
        source=source,
        select=resolved.select,
        archive=archive.name,
        archive_format=resolved.archive_format,
        archive_sha256=download.sha256,
        source_key=resolved.source_key,
        engine_version=__version__,
        rules_version=RULES_VERSION,
    )
    write_job(job_input_dir, job, reputation)
    return job


def _check_digest(resolved: ResolvedSource, download: Download) -> None:
    """Refuse a downloaded file whose digest differs from the one announced by the registry"""

    name = resolved.source.name
    if resolved.expected_sha512 is not None and not hmac.compare_digest(resolved.expected_sha512, download.sha512):
        raise FetchError("fetch.integrity_mismatch", package=name)
    if resolved.expected_sha256 is not None and not hmac.compare_digest(resolved.expected_sha256, download.sha256):
        raise FetchError("fetch.integrity_mismatch", package=name)


def _requested_npm(version: str | None, resolved_version: str) -> str | None:
    """Return the version label the user asked for when it differs from the resolved version"""

    requested = version or LATEST_LABEL
    if requested != resolved_version:
        return requested
    return None


def _requested_pypi(version: str | None) -> str | None:
    """Return latest when the user gave no PyPI version"""

    if version is None:
        return LATEST_LABEL
    return None


def _npm_source(
    spec: InputSpec,
    select: str | None,
    release: npm.NpmRelease,
    requested_version: str | None,
    reason: str = "source.requested_package",
    repository: str | None = None,
    revision: str | None = None,
    reference: str | None = None,
) -> ResolvedSource:
    """Describe the npm tarball to download, its sha512 and the packages to check on OSV"""

    expected = npm.expected_sha512(release.integrity)
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
    queries = [PackageQuery(release.name, NPM_ECOSYSTEM, release.version, False)]
    queries.extend(PackageQuery(name, NPM_ECOSYSTEM, None, True) for name in npm_dependency_names(release.manifest))
    return ResolvedSource(
        spec=spec,
        select=select,
        source=source,
        source_key=f"npm:{release.name}@{release.version}",
        download_url=release.tarball,
        archive_format=ArchiveFormat.TAR_GZ,
        expected_sha512=expected,
        queries=tuple(queries),
    )


def _pypi_source(
    spec: InputSpec,
    select: str | None,
    release: pypi.PypiRelease,
    requested_version: str | None,
    reason: str = "source.requested_package",
    repository: str | None = None,
    revision: str | None = None,
    reference: str | None = None,
) -> ResolvedSource:
    """Describe the PyPI file to download, its sha256 and the packages to check on OSV"""

    if not pypi.SHA256_PATTERN.match(release.sha256):
        raise FetchError("fetch.integrity_missing")
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
    queries = [PackageQuery(release.name, PYPI_ECOSYSTEM, release.version, False)]
    queries.extend(PackageQuery(name, PYPI_ECOSYSTEM, None, True) for name in pypi_dependency_names(release.info))
    return ResolvedSource(
        spec=spec,
        select=select,
        source=source,
        source_key=f"pypi:{normalize_pypi_name(release.name)}=={release.version}",
        download_url=release.url,
        archive_format=pypi_archive_format(release.filename),
        expected_sha256=release.sha256,
        queries=tuple(queries),
    )


def pypi_archive_format(filename: str) -> ArchiveFormat:
    """Return the archive format of a PyPI file from its name"""

    lower = filename.lower()
    if lower.endswith(ZIP_SUFFIXES):
        return ArchiveFormat.ZIP
    if lower.endswith(TAR_GZ_SUFFIXES):
        return ArchiveFormat.TAR_GZ
    if lower.endswith(TAR_SUFFIX):
        return ArchiveFormat.TAR
    raise ArchiveError("archive.unknown_format")


def _resolve_github(client: SafeClient, spec: InputSpec, limits: Limits) -> ResolvedSource:
    """Pin a GitHub commit, read the manifests of the folder through the API, then prefer the matching package"""

    source_api = github.GitHubSource(client)
    info = source_api.repository(spec.owner or "", spec.repo or "")
    owner, repo = info.owner, info.repo
    spec = resolve_tree_reference(spec, lambda ref: source_api.resolve_commit(owner, repo, ref) is not None)
    reference = spec.ref or info.default_branch
    sha = source_api.resolve_commit(owner, repo, reference)
    if sha is None:
        raise FetchError("fetch.github_ref_not_found", reference=reference)
    folder = spec.subdir or ""
    files = source_api.folder_files(owner, repo, sha, folder)
    if files is None and folder:
        raise DetectionError("analyze.subdir_not_found", path=folder)
    manifests = _read_manifests(source_api, owner, repo, sha, folder, files or {}, limits)
    candidate, reason = published_candidate(manifests)
    if candidate is None:
        return _github_source(spec, owner, repo, sha, reference, reason, manifests)
    try:
        if candidate.registry == NPM_REGISTRY:
            npm_release = npm.fetch_release(client, candidate.name, None)
            links = npm_links(npm_release.manifest)
        else:
            pypi_release = pypi.fetch_release(client, candidate.name, None)
            links = pypi_links(pypi_release.info)
    except FetchError as error:
        if error.code in NOT_PUBLISHED_CODES:
            return _github_source(spec, owner, repo, sha, reference, "source.package_not_published", manifests)
        raise
    outcome = match_links(links, owner, repo, spec.subdir)
    if not outcome.matched:
        return _github_source(spec, owner, repo, sha, reference, outcome.reason, manifests)
    repository = f"{owner}/{repo}"
    if candidate.registry == NPM_REGISTRY:
        requested = _requested_npm(None, npm_release.version)
        return _npm_source(spec, None, npm_release, requested, outcome.reason, repository, sha, reference)
    requested = _requested_pypi(None)
    return _pypi_source(spec, None, pypi_release, requested, outcome.reason, repository, sha, reference)


def _read_manifests(
    source_api: github.GitHubSource,
    owner: str,
    repo: str,
    sha: str,
    folder: str,
    files: dict[str, int],
    limits: Limits,
) -> ManifestFiles:
    """Read the package manifests of one folder through the contents API, each one 1 MB at most"""

    texts: dict[str, str] = {}
    for name in (PACKAGE_JSON, PYPROJECT, SETUP_CFG):
        size = files.get(name)
        if size is None or size > limits.max_manifest_bytes:
            continue
        path = name
        if folder:
            path = f"{folder}/{name}"
        texts[name] = source_api.file_text(owner, repo, sha, path, limits.max_manifest_bytes)
    package_json = None
    pyproject = None
    setup_cfg = None
    if PACKAGE_JSON in texts:
        package_json = parse_json_object(texts[PACKAGE_JSON])
    if PYPROJECT in texts:
        pyproject = parse_toml(texts[PYPROJECT])
    if SETUP_CFG in texts:
        setup_cfg = parse_setup_cfg(texts[SETUP_CFG])
    return ManifestFiles(package_json=package_json, pyproject=pyproject, setup_cfg=setup_cfg)


def _github_source(
    spec: InputSpec,
    owner: str,
    repo: str,
    sha: str,
    reference: str,
    reason: str,
    manifests: ManifestFiles,
) -> ResolvedSource:
    """Describe the GitHub archive of one commit; its sha256 is only known after the download"""

    url = f"https://github.com/{owner}/{repo}/tree/{sha}"
    source_key = f"github:{owner}/{repo}@{sha}"
    if spec.subdir:
        url = f"{url}/{spec.subdir}"
        source_key = f"{source_key}:{spec.subdir}"
    source = AnalyzedSource(
        kind=SourceKind.GITHUB,
        name=f"{owner}/{repo}",
        revision=sha,
        reference=reference,
        subdir=spec.subdir,
        url=url,
        artifact=GITHUB_ARTIFACT,
        origin=SourceOrigin.GITHUB_CODE,
        reason=reason,
    )
    queries = [PackageQuery(name, NPM_ECOSYSTEM, None, True) for name in npm_dependency_names(manifests.package_json)]
    queries.extend(
        PackageQuery(name, PYPI_ECOSYSTEM, None, True) for name in pyproject_dependency_names(manifests.pyproject)
    )
    return ResolvedSource(
        spec=spec,
        select=None,
        source=source,
        source_key=source_key,
        download_url=github.archive_url(owner, repo, sha),
        archive_format=ArchiveFormat.TAR_GZ,
        queries=tuple(queries),
    )
