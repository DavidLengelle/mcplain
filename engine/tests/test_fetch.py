"""Tests for the download step against simulated registries"""

import base64
import gzip
import hashlib
import json
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path

import httpx
import pytest
import respx
from builders import tar_gz, zip_bytes

from mcplain import analyze
from mcplain.analyze import analyze_input
from mcplain.cli import render
from mcplain.config import DEFAULT_LIMITS, Limits
from mcplain.errors import DetectionError, FetchError, InputError
from mcplain.fetch import archive, source
from mcplain.fetch.archive import extract_archive
from mcplain.fetch.osv import PackageQuery
from mcplain.fetch.source import ResolvedSource, check_source_reputation, download_source, resolve_source
from mcplain.i18n import Translator
from mcplain.inputs import parse_input
from mcplain.job import read_reputation
from mcplain.models import (
    AnalysisStatus,
    ArchiveFormat,
    JobFile,
    Reputation,
    ReputationStatus,
    SourceKind,
    SourceOrigin,
)

NPM_NAME = "@demo/weather-server"
NPM_META = "https://registry.npmjs.org/@demo%2Fweather-server/latest"
NPM_TARBALL = "https://registry.npmjs.org/@demo/weather-server/-/weather-server-1.2.3.tgz"
PYPI_META = "https://pypi.org/pypi/demo-server/json"
WHEEL_URL = "https://files.pythonhosted.org/packages/aa/demo_server-1.0.0-py3-none-any.whl"
SDIST_URL = "https://files.pythonhosted.org/packages/bb/demo_server-1.0.0.tar.gz"
SHA = "a" * 40
SERVER_JS = b"""import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
const server = new McpServer({ name: "weather", version: "1.2.3" });
server.tool("forecast", "Get the forecast", async () => ({ content: [] }));
"""
SERVER_PY = b'''from mcp.server import MCPServer

mcp = MCPServer("demo")


@mcp.tool()
def hello() -> str:
    """Say hello"""
    return "hello"
'''


def sri(data: bytes) -> str:
    """Return the npm integrity string of some bytes"""

    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


def npm_package(repository: object = None) -> bytes:
    """Build the tarball of a small npm MCP server"""

    manifest: dict[str, object] = {
        "name": NPM_NAME,
        "version": "1.2.3",
        "dependencies": {"@modelcontextprotocol/sdk": "^1.30.0"},
    }
    if repository is not None:
        manifest["repository"] = repository
    files = {"package.json": json.dumps(manifest).encode(), "index.js": SERVER_JS}
    return tar_gz(files, prefix="package/")


def npm_document(data: bytes, tarball: str = NPM_TARBALL, integrity: str | None = None, repository: object = None) -> dict[str, object]:
    """Build the registry metadata of one npm version"""

    if integrity is None:
        integrity = sri(data)
    document: dict[str, object] = {
        "name": NPM_NAME,
        "version": "1.2.3",
        "dependencies": {"@modelcontextprotocol/sdk": "^1.30.0", "zod": "^3"},
        "dist": {"tarball": tarball, "integrity": integrity},
    }
    if repository is not None:
        document["repository"] = repository
    return document


def pypi_document(wheel: bytes, sdist: bytes, wheel_sha: str | None = None) -> dict[str, object]:
    """Build PyPI JSON metadata with a wheel and an sdist"""

    if wheel_sha is None:
        wheel_sha = hashlib.sha256(wheel).hexdigest()
    return {
        "info": {
            "name": "demo-server",
            "version": "1.0.0",
            "project_urls": {"Repository": "https://github.com/demo/servers/tree/main/src/demo"},
            "requires_dist": ["mcp>=2", "pytest; extra == \"test\""],
        },
        "urls": [
            {
                "packagetype": "sdist",
                "filename": "demo_server-1.0.0.tar.gz",
                "url": SDIST_URL,
                "digests": {"sha256": hashlib.sha256(sdist).hexdigest()},
            },
            {
                "packagetype": "bdist_wheel",
                "filename": "demo_server-1.0.0-py3-none-any.whl",
                "url": WHEEL_URL,
                "digests": {"sha256": wheel_sha},
            },
        ],
    }


def wheel_bytes() -> bytes:
    """Build a small pure Python wheel of an MCP server"""

    return zip_bytes(
        {
            "demo_server/server.py": SERVER_PY,
            "demo_server-1.0.0.dist-info/METADATA": b"Name: demo-server\nRequires-Dist: mcp>=2\n",
        }
    )


@pytest.fixture(autouse=True)
def no_reputation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave OSV out of the download tests: test_osv.py simulates it"""

    def checked(client: object, queries: object, limits: object) -> Reputation:
        """Pretend that OSV found nothing"""

        return Reputation(status=ReputationStatus.CHECKED)

    monkeypatch.setattr(source, "check_reputation", checked)


@pytest.fixture
def workdirs(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record the temporary folders created by analyze_input"""

    created: list[Path] = []
    original = tempfile.mkdtemp

    def recording_mkdtemp(*args: object, **kwargs: object) -> str:
        """Create a temporary folder and remember it"""

        path = original(*args, **kwargs)
        created.append(Path(path))
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", recording_mkdtemp)
    return created


def forbid_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every way of opening an archive fail from now on"""

    def refuse(*args: object, **kwargs: object) -> None:
        """Fail the test if an archive is opened"""

        raise AssertionError("the download step must never open an archive")

    monkeypatch.setattr(archive, "extract_archive", refuse)
    monkeypatch.setattr(analyze, "extract_archive", refuse)
    monkeypatch.setattr(tarfile, "open", refuse)
    monkeypatch.setattr(zipfile, "ZipFile", refuse)
    monkeypatch.setattr(gzip, "GzipFile", refuse)


def resolve(text: str, limits: Limits = DEFAULT_LIMITS, select: str | None = None) -> ResolvedSource:
    """Resolve a pasted input from the simulated registries"""

    return resolve_source(parse_input(text), select, limits)


def prepare(folder: Path, text: str, limits: Limits = DEFAULT_LIMITS) -> JobFile:
    """Resolve a pasted input and download it into a job folder"""

    return download_source(resolve(text, limits), folder, limits)


def extracted(folder: Path, job: JobFile) -> Path:
    """Extract the archive of a job folder, as the atelier does, to look at its files"""

    return extract_archive(folder / job.archive, folder.parent / "extracted")


@respx.mock
def test_npm_package_is_analyzed_and_cleaned(workdirs: list[Path]) -> None:
    """The whole pipeline downloads, checks sha512, analyzes and removes its temporary folder"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(200, content=data))
    result = analyze_input(f"npx -y {NPM_NAME}")
    assert result.source is not None
    assert result.source.kind is SourceKind.NPM
    assert result.source.version == "1.2.3"
    assert result.source.integrity == sri(data)
    assert result.source.origin is SourceOrigin.PUBLISHED_PACKAGE
    assert workdirs and not workdirs[0].exists()


@respx.mock
def test_job_folder_holds_the_raw_archive_and_its_files(tmp_path: Path) -> None:
    """download_source writes the archive as downloaded, job.json and reputation.json, readable by everyone"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(200, content=data))
    job = prepare(tmp_path, f"npx -y {NPM_NAME}")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["job.json", "reputation.json", "source.tar.gz"]
    assert (tmp_path / "source.tar.gz").read_bytes() == data
    assert job.archive_sha256 == hashlib.sha256(data).hexdigest()
    assert job.source_key == f"npm:{NPM_NAME}@1.2.3"
    assert JobFile.model_validate_json((tmp_path / "job.json").read_text(encoding="utf-8")) == job
    for path in tmp_path.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o644


@respx.mock
def test_given_reputation_is_written_without_asking_osv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """download_source writes the reputation it is given and does not ask OSV a second time"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(200, content=data))

    def refuse(client: object, queries: object, limits: object) -> Reputation:
        """Fail the test if OSV is asked"""

        raise AssertionError("OSV must not be asked again")

    monkeypatch.setattr(source, "check_reputation", refuse)
    reputation = Reputation(status=ReputationStatus.UNAVAILABLE)
    download_source(resolve(f"npx -y {NPM_NAME}"), tmp_path, reputation=reputation)
    assert read_reputation(tmp_path) == reputation


@respx.mock
def test_source_reputation_asks_osv_and_downloads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_source_reputation sends the queries of the resolved source and never fetches the archive"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    tarball = respx.get(NPM_TARBALL).mock(return_value=httpx.Response(200, content=data))
    seen: list[PackageQuery] = []

    def checked(client: object, queries: list[PackageQuery], limits: object) -> Reputation:
        """Record the queries and pretend that OSV found nothing"""

        seen.extend(queries)
        return Reputation(status=ReputationStatus.CHECKED, queried=len(queries))

    monkeypatch.setattr(source, "check_reputation", checked)
    resolved = resolve(f"npx -y {NPM_NAME}")
    reputation = check_source_reputation(resolved)
    assert seen == list(resolved.queries)
    assert reputation.queried == len(resolved.queries) >= 1
    assert tarball.call_count == 0


@respx.mock
def test_download_never_opens_the_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Downloading an npm tarball, a wheel or a GitHub archive never extracts it"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(200, content=data))
    wheel = wheel_bytes()
    respx.get(PYPI_META).mock(return_value=httpx.Response(200, json=pypi_document(wheel, b"")))
    respx.get(WHEEL_URL).mock(return_value=httpx.Response(200, content=wheel))
    files = {"src/demo/pyproject.toml": b'[project]\nname = "other-server"\ndependencies = ["mcp"]\n'}
    mock_github(files, {"main": SHA})
    respx.get("https://pypi.org/pypi/other-server/json").mock(return_value=httpx.Response(404))
    forbid_extraction(monkeypatch)
    for index, text in enumerate(
        [f"npx {NPM_NAME}", "uvx demo-server", "https://github.com/demo/servers/tree/main/src/demo"]
    ):
        folder = tmp_path / str(index)
        folder.mkdir()
        job = prepare(folder, text)
        assert sorted(path.name for path in folder.iterdir()) == sorted(["job.json", "reputation.json", job.archive])


@respx.mock
def test_wrong_npm_integrity_is_refused(tmp_path: Path, workdirs: list[Path]) -> None:
    """Refuse a tarball whose sha512 does not match the registry, and delete it"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data, integrity=sri(b"other"))))
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(200, content=data))
    with pytest.raises(FetchError) as error:
        prepare(tmp_path, f"npx {NPM_NAME}")
    assert error.value.code == "fetch.integrity_mismatch"
    assert list(tmp_path.iterdir()) == []
    result = analyze_input(f"npx {NPM_NAME}")
    assert result.error is not None and result.error.code == "fetch.integrity_mismatch"
    assert workdirs and not workdirs[0].exists()


@respx.mock
def test_missing_npm_integrity_is_refused() -> None:
    """Refuse a package that has no sha512 integrity, before any download"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data, integrity="sha1-abc")))
    with pytest.raises(FetchError) as error:
        resolve(f"npx {NPM_NAME}")
    assert error.value.code == "fetch.integrity_missing"


@respx.mock
def test_redirect_to_other_host_is_refused(tmp_path: Path) -> None:
    """Refuse a redirect that leaves the allow list, without contacting the other host"""

    data = npm_package()
    evil = respx.get("https://evil.example/pkg.tgz").mock(return_value=httpx.Response(200, content=data))
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    respx.get(NPM_TARBALL).mock(
        return_value=httpx.Response(302, headers={"Location": "https://evil.example/pkg.tgz"})
    )
    with pytest.raises(FetchError) as error:
        prepare(tmp_path, f"npx {NPM_NAME}")
    assert error.value.code == "fetch.host_not_allowed"
    assert not evil.called


@respx.mock
def test_redirect_inside_allow_list_is_followed(tmp_path: Path) -> None:
    """Follow a redirect hop when the next host is allowed"""

    data = npm_package()
    moved = "https://registry.npmjs.org/moved.tgz"
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(301, headers={"Location": moved}))
    respx.get(moved).mock(return_value=httpx.Response(200, content=data))
    job = prepare(tmp_path, f"npx {NPM_NAME}")
    assert (extracted(tmp_path, job) / "index.js").is_file()


@respx.mock
def test_tarball_on_other_host_is_refused(tmp_path: Path) -> None:
    """Refuse a tarball URL that points outside the allow list"""

    data = npm_package()
    document = npm_document(data, tarball="https://cdn.evil.example/pkg.tgz")
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=document))
    with pytest.raises(FetchError) as error:
        prepare(tmp_path, f"npx {NPM_NAME}")
    assert error.value.code == "fetch.host_not_allowed"


@respx.mock
def test_plain_http_tarball_is_refused(tmp_path: Path) -> None:
    """Refuse a tarball URL without HTTPS"""

    data = npm_package()
    document = npm_document(data, tarball="http://registry.npmjs.org/pkg.tgz")
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=document))
    with pytest.raises(FetchError) as error:
        prepare(tmp_path, f"npx {NPM_NAME}")
    assert error.value.code == "fetch.insecure_url"


@respx.mock
def test_download_over_size_limit_is_stopped(tmp_path: Path) -> None:
    """Stop a download as soon as it passes the size limit"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(200, content=data))
    with pytest.raises(FetchError) as error:
        prepare(tmp_path, f"npx {NPM_NAME}", Limits(max_download_bytes=50))
    assert error.value.code == "fetch.too_large"


@respx.mock
def test_unknown_npm_package() -> None:
    """Report a package that the registry does not know"""

    respx.get(NPM_META).mock(return_value=httpx.Response(404, json={"error": "Not found"}))
    with pytest.raises(FetchError) as error:
        resolve(f"npx {NPM_NAME}")
    assert error.value.code == "fetch.npm_not_found"


@respx.mock
def test_npm_reputation_queries_come_from_the_registry() -> None:
    """The package is checked at its exact version and its dependencies by name, read from the registry"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    resolved = resolve(f"npx {NPM_NAME}")
    queries = [(query.name, query.ecosystem, query.version, query.dependency) for query in resolved.queries]
    assert queries == [
        (NPM_NAME, "npm", "1.2.3", False),
        ("@modelcontextprotocol/sdk", "npm", None, True),
        ("zod", "npm", None, True),
    ]


@respx.mock
def test_pypi_prefers_pure_wheel_and_checks_sha256(tmp_path: Path) -> None:
    """Choose the pure Python wheel over the sdist and verify its sha256"""

    wheel = wheel_bytes()
    sdist = tar_gz({"PKG-INFO": b"Name: demo-server"}, prefix="demo_server-1.0.0/")
    respx.get(PYPI_META).mock(return_value=httpx.Response(200, json=pypi_document(wheel, sdist)))
    wheel_route = respx.get(WHEEL_URL).mock(return_value=httpx.Response(200, content=wheel))
    sdist_route = respx.get(SDIST_URL).mock(return_value=httpx.Response(200, content=sdist))
    resolved = resolve("uvx demo-server")
    assert resolved.archive_format is ArchiveFormat.ZIP
    assert resolved.source_key == "pypi:demo-server==1.0.0"
    assert [query.name for query in resolved.queries] == ["demo-server", "mcp"]
    job = download_source(resolved, tmp_path)
    assert job.archive == "source.zip"
    assert job.source.artifact == "wheel"
    assert job.source.integrity == "sha256:" + hashlib.sha256(wheel).hexdigest()
    assert (extracted(tmp_path, job) / "demo_server" / "server.py").is_file()
    assert wheel_route.called
    assert not sdist_route.called


@respx.mock
def test_wrong_pypi_sha256_is_refused(tmp_path: Path) -> None:
    """Refuse a wheel whose sha256 does not match PyPI"""

    wheel = wheel_bytes()
    document = pypi_document(wheel, b"", wheel_sha=hashlib.sha256(b"other").hexdigest())
    respx.get(PYPI_META).mock(return_value=httpx.Response(200, json=document))
    respx.get(WHEEL_URL).mock(return_value=httpx.Response(200, content=wheel))
    with pytest.raises(FetchError) as error:
        prepare(tmp_path, "uvx demo-server")
    assert error.value.code == "fetch.integrity_mismatch"
    assert list(tmp_path.iterdir()) == []


def contents_url(path: str) -> str:
    """Return the simulated contents API URL of a path of demo/servers at the test commit"""

    if not path:
        return f"https://api.github.com/repos/demo/servers/contents?ref={SHA}"
    return f"https://api.github.com/repos/demo/servers/contents/{path}?ref={SHA}"


def mock_github(repo_files: dict[str, bytes], refs: dict[str, str | None]) -> respx.Route:
    """Mock the GitHub API, the contents API and codeload for the demo/servers repository"""

    respx.get("https://api.github.com/repos/demo/servers").mock(
        return_value=httpx.Response(200, json={"full_name": "demo/servers", "default_branch": "main", "size": 10})
    )
    for ref, sha in refs.items():
        route = respx.get(f"https://api.github.com/repos/demo/servers/commits/{ref}")
        if sha is None:
            route.mock(return_value=httpx.Response(422, json={"message": "No commit found"}))
        else:
            route.mock(return_value=httpx.Response(200, text=sha))
    listings: dict[str, list[dict[str, object]]] = {"": []}
    for name, content in repo_files.items():
        folder, _, base = name.rpartition("/")
        listings.setdefault(folder, []).append({"name": base, "type": "file", "size": len(content)})
        respx.get(contents_url(name)).mock(return_value=httpx.Response(200, content=content))
        parts = folder.split("/")
        for depth in range(1, len(parts)):
            parent = "/".join(parts[: depth - 1])
            entry = {"name": parts[depth - 1], "type": "dir", "size": 0}
            if entry not in listings.setdefault(parent, []):
                listings[parent].append(entry)
    for folder, listing in listings.items():
        respx.get(contents_url(folder)).mock(return_value=httpx.Response(200, json=listing))
    return respx.get(f"https://codeload.github.com/demo/servers/tar.gz/{SHA}").mock(
        return_value=httpx.Response(200, content=tar_gz(repo_files, prefix=f"servers-{SHA}/"))
    )


@respx.mock
def test_github_tree_reference_with_slash(tmp_path: Path) -> None:
    """Resolve feature/x as the reference and keep src/demo as the folder"""

    files = {"src/demo/pyproject.toml": b'[project]\nname = "demo-server"\ndependencies = ["mcp"]\n'}
    files["src/demo/server.py"] = SERVER_PY
    codeload = mock_github(files, {"feature": None, "feature%2Fx": SHA})
    respx.get(PYPI_META).mock(return_value=httpx.Response(404))
    resolved = resolve("https://github.com/demo/servers/tree/feature/x/src/demo")
    assert resolved.source.kind is SourceKind.GITHUB
    assert resolved.source.reference == "feature/x"
    assert resolved.source.revision == SHA
    assert resolved.source.subdir == "src/demo"
    assert resolved.source.origin is SourceOrigin.GITHUB_CODE
    assert resolved.source.reason == "source.package_not_published"
    assert resolved.source_key == f"github:demo/servers@{SHA}:src/demo"
    assert [(query.name, query.ecosystem) for query in resolved.queries] == [("mcp", "PyPI")]
    assert not codeload.called
    job = download_source(resolved, tmp_path)
    assert codeload.called
    assert job.source.integrity == "sha256:" + job.archive_sha256


@respx.mock
def test_github_prefers_matching_published_package(tmp_path: Path) -> None:
    """Analyze the published package when its metadata points back to the same folder, without the GitHub archive"""

    files = {"src/demo/pyproject.toml": b'[project]\nname = "demo-server"\ndependencies = ["mcp"]\n'}
    files["src/demo/server.py"] = SERVER_PY
    codeload = mock_github(files, {"main": SHA})
    wheel = wheel_bytes()
    respx.get(PYPI_META).mock(return_value=httpx.Response(200, json=pypi_document(wheel, b"")))
    respx.get(WHEEL_URL).mock(return_value=httpx.Response(200, content=wheel))
    job = prepare(tmp_path, "https://github.com/demo/servers/tree/main/src/demo")
    assert job.source.kind is SourceKind.PYPI
    assert job.source.origin is SourceOrigin.PUBLISHED_PACKAGE
    assert job.source.reason == "source.published_matches_directory"
    assert job.source.repository == "demo/servers"
    assert job.source.reference == "main"
    assert job.source_key == "pypi:demo-server==1.0.0"
    assert not codeload.called


@respx.mock
def test_missing_github_folder_is_reported_before_download() -> None:
    """A folder that does not exist at the commit is refused from the contents API"""

    codeload = mock_github({"README.md": b"demo"}, {"main": SHA})
    respx.get(contents_url("src/nope")).mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
    with pytest.raises(DetectionError) as error:
        resolve("https://github.com/demo/servers/tree/main/src/nope")
    assert error.value.code == "analyze.subdir_not_found"
    assert not codeload.called


@respx.mock
def test_large_manifest_is_not_read() -> None:
    """A manifest over 1 MB is ignored and the GitHub code is analyzed"""

    codeload = mock_github({"package.json": b"{}"}, {"main": SHA})
    big = [{"name": "package.json", "type": "file", "size": 2 * 1024 * 1024}]
    respx.get(contents_url("")).mock(return_value=httpx.Response(200, json=big))
    manifest = respx.get(contents_url("package.json"))
    resolved = resolve("https://github.com/demo/servers")
    assert resolved.source.reason == "source.no_package_manifest"
    assert not manifest.called
    assert not codeload.called


@respx.mock
def test_linked_commit_is_explained_in_the_report() -> None:
    """The report says which commit was consulted and that it may differ from the published build"""

    files = {"src/demo/pyproject.toml": b'[project]\nname = "demo-server"\ndependencies = ["mcp"]\n'}
    files["src/demo/server.py"] = SERVER_PY
    mock_github(files, {"main": SHA})
    wheel = wheel_bytes()
    respx.get(PYPI_META).mock(return_value=httpx.Response(200, json=pypi_document(wheel, b"")))
    respx.get(WHEEL_URL).mock(return_value=httpx.Response(200, content=wheel))
    result = analyze_input("https://github.com/demo/servers/tree/main/src/demo")
    text = render(result, Translator("fr"))
    assert "Dépôt GitHub lié : demo/servers" in text
    assert f"Commit consulté sur la branche main : {SHA} (pas forcément celui qui a servi à fabriquer le paquet)" in text


@respx.mock
def test_github_keeps_code_when_package_points_elsewhere() -> None:
    """Keep the GitHub code when the package with the same name belongs to another repository"""

    manifest = {"name": NPM_NAME, "dependencies": {"@modelcontextprotocol/sdk": "^1.30.0"}}
    files = {"package.json": json.dumps(manifest).encode(), "index.js": SERVER_JS}
    mock_github(files, {"main": SHA})
    other = {"type": "git", "url": "git+https://github.com/someone-else/servers.git"}
    data = npm_package(other)
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data, repository=other)))
    resolved = resolve("https://github.com/demo/servers")
    assert resolved.source.kind is SourceKind.GITHUB
    assert resolved.source.origin is SourceOrigin.GITHUB_CODE
    assert resolved.source.reason == "source.package_repository_mismatch"
    assert resolved.source_key == f"github:demo/servers@{SHA}"
    assert [(query.name, query.ecosystem) for query in resolved.queries] == [("@modelcontextprotocol/sdk", "npm")]


@respx.mock
def test_github_code_is_analyzed_end_to_end() -> None:
    """A GitHub folder without a published package is downloaded from codeload and analyzed"""

    files = {"src/demo/pyproject.toml": b'[project]\nname = "demo-server"\ndependencies = ["mcp"]\n'}
    files["src/demo/server.py"] = SERVER_PY
    mock_github(files, {"main": SHA})
    respx.get(PYPI_META).mock(return_value=httpx.Response(404))
    result = analyze_input("https://github.com/demo/servers/tree/main/src/demo")
    assert result.status is AnalysisStatus.OK
    assert result.source is not None and result.source.subdir == "src/demo"
    assert [tool.name for tool in result.servers[0].tools] == ["hello"]


@respx.mock
def test_github_rate_limit_is_reported() -> None:
    """Explain the GitHub rate limit instead of failing silently"""

    respx.get("https://api.github.com/repos/demo/servers").mock(
        return_value=httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={"message": "rate limit"})
    )
    with pytest.raises(FetchError) as error:
        resolve("https://github.com/demo/servers")
    assert error.value.code == "fetch.github_rate_limited"


@respx.mock
def test_unknown_tree_reference_becomes_input_error() -> None:
    """Report a tree path whose reference does not exist"""

    mock_github({}, {"nope": None, "nope%2Fsrc": None})
    with pytest.raises(InputError) as error:
        resolve("https://github.com/demo/servers/tree/nope/src")
    assert error.value.code == "input.reference_not_found"


@respx.mock
def test_analyze_input_end_to_end_with_mocked_registry() -> None:
    """Run the whole pipeline on a mocked npm package"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(200, content=data))
    result = analyze_input(f"npx -y {NPM_NAME}")
    assert result.status is AnalysisStatus.OK
    assert [tool.name for tool in result.servers[0].tools] == ["forecast"]


def test_analyze_input_reports_refused_input_without_network() -> None:
    """Refuse bad input before any download"""

    result = analyze_input("ssh://github.com/demo/servers")
    assert result.status is AnalysisStatus.ERROR
    assert result.error is not None
    assert result.error.code == "input.unsupported_scheme"


@respx.mock
def test_ignored_arguments_and_dist_tag_reach_the_report() -> None:
    """Arguments after the package are reported as ignored and a dist-tag is resolved by the registry"""

    data = npm_package()
    respx.get("https://registry.npmjs.org/@demo%2Fweather-server/next").mock(
        return_value=httpx.Response(200, json=npm_document(data))
    )
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(200, content=data))
    result = analyze_input(f"npx -y {NPM_NAME}@next ~/Bureau --port 3000")
    assert result.status is AnalysisStatus.OK
    assert result.ignored_arguments == ["~/Bureau", "--port", "3000"]
    assert result.source is not None
    assert result.source.version == "1.2.3"
    assert result.source.requested_version == "next"
    text = render(result, Translator("fr"))
    assert "Arguments ignorés (jamais exécutés) : ~/Bureau --port 3000" in text
    assert "1.2.3 (demandée : next)" in text
