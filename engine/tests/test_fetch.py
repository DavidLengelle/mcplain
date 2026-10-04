"""Tests for the download step against simulated registries"""

import base64
import hashlib
import json
import tempfile
from pathlib import Path

import httpx
import pytest
import respx
from builders import tar_gz, zip_bytes

from mcplain.analyze import analyze_input, fetch_source
from mcplain.cli import render
from mcplain.config import Limits
from mcplain.errors import FetchError, InputError
from mcplain.i18n import Translator
from mcplain.inputs import parse_input
from mcplain.models import AnalysisStatus, SourceKind, SourceOrigin

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


@pytest.fixture
def workdirs(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record the temporary folders created by fetch_source"""

    created: list[Path] = []
    original = tempfile.mkdtemp

    def recording_mkdtemp(*args: object, **kwargs: object) -> str:
        """Create a temporary folder and remember it"""

        path = original(*args, **kwargs)
        created.append(Path(path))
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", recording_mkdtemp)
    return created


@respx.mock
def test_npm_package_is_downloaded_verified_and_cleaned(workdirs: list[Path]) -> None:
    """Download an npm package, check sha512, extract it and remove the folder afterwards"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(200, content=data))
    with fetch_source(parse_input(f"npx -y {NPM_NAME}")) as fetched:
        assert (fetched.root / "package.json").is_file()
        assert fetched.source.kind is SourceKind.NPM
        assert fetched.source.version == "1.2.3"
        assert fetched.source.integrity == sri(data)
        assert fetched.source.origin is SourceOrigin.PUBLISHED_PACKAGE
    assert workdirs and not workdirs[0].exists()


@respx.mock
def test_wrong_npm_integrity_is_refused(workdirs: list[Path]) -> None:
    """Refuse a tarball whose sha512 does not match the registry"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data, integrity=sri(b"other"))))
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(200, content=data))
    with pytest.raises(FetchError) as error, fetch_source(parse_input(f"npx {NPM_NAME}")):
        pytest.fail("the package must not be extracted")
    assert error.value.code == "fetch.integrity_mismatch"
    assert workdirs and not workdirs[0].exists()


@respx.mock
def test_missing_npm_integrity_is_refused() -> None:
    """Refuse a package that has no sha512 integrity"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data, integrity="sha1-abc")))
    with pytest.raises(FetchError) as error, fetch_source(parse_input(f"npx {NPM_NAME}")):
        pytest.fail("the package must not be extracted")
    assert error.value.code == "fetch.integrity_missing"


@respx.mock
def test_redirect_to_other_host_is_refused() -> None:
    """Refuse a redirect that leaves the allow list, without contacting the other host"""

    data = npm_package()
    evil = respx.get("https://evil.example/pkg.tgz").mock(return_value=httpx.Response(200, content=data))
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    respx.get(NPM_TARBALL).mock(
        return_value=httpx.Response(302, headers={"Location": "https://evil.example/pkg.tgz"})
    )
    with pytest.raises(FetchError) as error, fetch_source(parse_input(f"npx {NPM_NAME}")):
        pytest.fail("the package must not be extracted")
    assert error.value.code == "fetch.host_not_allowed"
    assert not evil.called


@respx.mock
def test_redirect_inside_allow_list_is_followed() -> None:
    """Follow a redirect hop when the next host is allowed"""

    data = npm_package()
    moved = "https://registry.npmjs.org/moved.tgz"
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(301, headers={"Location": moved}))
    respx.get(moved).mock(return_value=httpx.Response(200, content=data))
    with fetch_source(parse_input(f"npx {NPM_NAME}")) as fetched:
        assert (fetched.root / "index.js").is_file()


@respx.mock
def test_tarball_on_other_host_is_refused() -> None:
    """Refuse a tarball URL that points outside the allow list"""

    data = npm_package()
    document = npm_document(data, tarball="https://cdn.evil.example/pkg.tgz")
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=document))
    with pytest.raises(FetchError) as error, fetch_source(parse_input(f"npx {NPM_NAME}")):
        pytest.fail("the package must not be extracted")
    assert error.value.code == "fetch.host_not_allowed"


@respx.mock
def test_plain_http_tarball_is_refused() -> None:
    """Refuse a tarball URL without HTTPS"""

    data = npm_package()
    document = npm_document(data, tarball="http://registry.npmjs.org/pkg.tgz")
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=document))
    with pytest.raises(FetchError) as error, fetch_source(parse_input(f"npx {NPM_NAME}")):
        pytest.fail("the package must not be extracted")
    assert error.value.code == "fetch.insecure_url"


@respx.mock
def test_download_over_size_limit_is_stopped() -> None:
    """Stop a download as soon as it passes the size limit"""

    data = npm_package()
    respx.get(NPM_META).mock(return_value=httpx.Response(200, json=npm_document(data)))
    respx.get(NPM_TARBALL).mock(return_value=httpx.Response(200, content=data))
    spec = parse_input(f"npx {NPM_NAME}")
    with pytest.raises(FetchError) as error, fetch_source(spec, Limits(max_download_bytes=50)):
        pytest.fail("the package must not be extracted")
    assert error.value.code == "fetch.too_large"


@respx.mock
def test_unknown_npm_package() -> None:
    """Report a package that the registry does not know"""

    respx.get(NPM_META).mock(return_value=httpx.Response(404, json={"error": "Not found"}))
    with pytest.raises(FetchError) as error, fetch_source(parse_input(f"npx {NPM_NAME}")):
        pytest.fail("nothing must be extracted")
    assert error.value.code == "fetch.npm_not_found"


@respx.mock
def test_pypi_prefers_pure_wheel_and_checks_sha256() -> None:
    """Choose the pure Python wheel over the sdist and verify its sha256"""

    wheel = wheel_bytes()
    sdist = tar_gz({"PKG-INFO": b"Name: demo-server"}, prefix="demo_server-1.0.0/")
    respx.get(PYPI_META).mock(return_value=httpx.Response(200, json=pypi_document(wheel, sdist)))
    wheel_route = respx.get(WHEEL_URL).mock(return_value=httpx.Response(200, content=wheel))
    sdist_route = respx.get(SDIST_URL).mock(return_value=httpx.Response(200, content=sdist))
    with fetch_source(parse_input("uvx demo-server")) as fetched:
        assert fetched.source.artifact == "wheel"
        assert fetched.source.integrity == "sha256:" + hashlib.sha256(wheel).hexdigest()
        assert (fetched.root / "demo_server" / "server.py").is_file()
    assert wheel_route.called
    assert not sdist_route.called


@respx.mock
def test_wrong_pypi_sha256_is_refused() -> None:
    """Refuse a wheel whose sha256 does not match PyPI"""

    wheel = wheel_bytes()
    document = pypi_document(wheel, b"", wheel_sha=hashlib.sha256(b"other").hexdigest())
    respx.get(PYPI_META).mock(return_value=httpx.Response(200, json=document))
    respx.get(WHEEL_URL).mock(return_value=httpx.Response(200, content=wheel))
    with pytest.raises(FetchError) as error, fetch_source(parse_input("uvx demo-server")):
        pytest.fail("the wheel must not be extracted")
    assert error.value.code == "fetch.integrity_mismatch"


def mock_github(repo_files: dict[str, bytes], refs: dict[str, str | None]) -> None:
    """Mock the GitHub API and codeload for the demo/servers repository"""

    respx.get("https://api.github.com/repos/demo/servers").mock(
        return_value=httpx.Response(200, json={"full_name": "demo/servers", "default_branch": "main", "size": 10})
    )
    for ref, sha in refs.items():
        route = respx.get(f"https://api.github.com/repos/demo/servers/commits/{ref}")
        if sha is None:
            route.mock(return_value=httpx.Response(422, json={"message": "No commit found"}))
        else:
            route.mock(return_value=httpx.Response(200, text=sha))
    respx.get(f"https://codeload.github.com/demo/servers/tar.gz/{SHA}").mock(
        return_value=httpx.Response(200, content=tar_gz(repo_files, prefix=f"servers-{SHA}/"))
    )


@respx.mock
def test_github_tree_reference_with_slash() -> None:
    """Resolve feature/x as the reference and keep src/demo as the folder"""

    files = {"src/demo/pyproject.toml": b'[project]\nname = "demo-server"\ndependencies = ["mcp"]\n'}
    files["src/demo/server.py"] = SERVER_PY
    mock_github(files, {"feature": None, "feature%2Fx": SHA})
    respx.get(PYPI_META).mock(return_value=httpx.Response(404))
    with fetch_source(parse_input("https://github.com/demo/servers/tree/feature/x/src/demo")) as fetched:
        assert fetched.source.kind is SourceKind.GITHUB
        assert fetched.source.reference == "feature/x"
        assert fetched.source.revision == SHA
        assert fetched.subdir == "src/demo"
        assert fetched.source.origin is SourceOrigin.GITHUB_CODE
        assert fetched.source.reason == "source.package_not_published"


@respx.mock
def test_github_prefers_matching_published_package() -> None:
    """Analyze the published package when its metadata points back to the same folder"""

    files = {"src/demo/pyproject.toml": b'[project]\nname = "demo-server"\ndependencies = ["mcp"]\n'}
    files["src/demo/server.py"] = SERVER_PY
    mock_github(files, {"main": SHA})
    wheel = wheel_bytes()
    respx.get(PYPI_META).mock(return_value=httpx.Response(200, json=pypi_document(wheel, b"")))
    respx.get(WHEEL_URL).mock(return_value=httpx.Response(200, content=wheel))
    with fetch_source(parse_input("https://github.com/demo/servers/tree/main/src/demo")) as fetched:
        assert fetched.source.kind is SourceKind.PYPI
        assert fetched.source.origin is SourceOrigin.PUBLISHED_PACKAGE
        assert fetched.source.reason == "source.published_matches_directory"
        assert fetched.source.repository == "demo/servers"
        assert fetched.source.reference == "main"


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
    with fetch_source(parse_input("https://github.com/demo/servers")) as fetched:
        assert fetched.source.kind is SourceKind.GITHUB
        assert fetched.source.origin is SourceOrigin.GITHUB_CODE
        assert fetched.source.reason == "source.package_repository_mismatch"


@respx.mock
def test_github_rate_limit_is_reported() -> None:
    """Explain the GitHub rate limit instead of failing silently"""

    respx.get("https://api.github.com/repos/demo/servers").mock(
        return_value=httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={"message": "rate limit"})
    )
    with pytest.raises(FetchError) as error, fetch_source(parse_input("https://github.com/demo/servers")):
        pytest.fail("nothing must be downloaded")
    assert error.value.code == "fetch.github_rate_limited"


@respx.mock
def test_unknown_tree_reference_becomes_input_error() -> None:
    """Report a tree path whose reference does not exist"""

    mock_github({}, {"nope": None, "nope%2Fsrc": None})
    spec = parse_input("https://github.com/demo/servers/tree/nope/src")
    with pytest.raises(InputError) as error, fetch_source(spec):
        pytest.fail("nothing must be downloaded")
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
