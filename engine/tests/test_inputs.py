"""Tests for the strict parsing of user input"""

import pytest

from mcplain.errors import InputError
from mcplain.inputs import add_subdir, parse_input, parse_selection, resolve_tree_reference
from mcplain.models import InputKind


@pytest.mark.parametrize(
    "text",
    [
        "https://github.com/modelcontextprotocol/servers",
        "https://github.com/modelcontextprotocol/servers/",
        "https://github.com/modelcontextprotocol/servers.git",
        "  https://www.github.com/modelcontextprotocol/servers  ",
    ],
)
def test_github_repository_urls(text: str) -> None:
    """Accept repository URLs with or without .git and trailing slash"""

    spec = parse_input(text)
    assert spec.kind is InputKind.GITHUB_REPO
    assert spec.owner == "modelcontextprotocol"
    assert spec.repo == "servers"
    assert spec.ref is None


def test_github_tree_with_single_reference() -> None:
    """A /tree/<ref> URL without folder is a whole repository at a reference"""

    spec = parse_input("https://github.com/owner/repo/tree/v1.2.0")
    assert spec.kind is InputKind.GITHUB_REPO
    assert spec.ref == "v1.2.0"
    assert spec.tree_path is None


def test_github_tree_with_folder() -> None:
    """A /tree/<ref>/<path> URL keeps the full path until the reference is resolved"""

    spec = parse_input("https://github.com/modelcontextprotocol/servers/tree/main/src/fetch")
    assert spec.kind is InputKind.GITHUB_SUBDIR
    assert spec.tree_path == "main/src/fetch"


def test_tree_reference_with_slashes_is_resolved_by_prefix() -> None:
    """Try main, then feature/x, until a reference exists"""

    spec = parse_input("https://github.com/owner/repo/tree/feature/x/src/server")
    asked: list[str] = []

    def exists(ref: str) -> bool:
        """Pretend that only feature/x exists"""

        asked.append(ref)
        return ref == "feature/x"

    resolved = resolve_tree_reference(spec, exists)
    assert asked == ["feature", "feature/x"]
    assert resolved.ref == "feature/x"
    assert resolved.subdir == "src/server"
    assert resolved.kind is InputKind.GITHUB_SUBDIR
    assert resolved.tree_path is None


def test_tree_reference_covering_whole_path() -> None:
    """When the whole tree path is a reference, there is no subfolder"""

    spec = parse_input("https://github.com/owner/repo/tree/release/2026")
    resolved = resolve_tree_reference(spec, lambda ref: ref == "release/2026")
    assert resolved.kind is InputKind.GITHUB_REPO
    assert resolved.ref == "release/2026"
    assert resolved.subdir is None


def test_unknown_tree_reference() -> None:
    """Refuse a tree path when no prefix exists"""

    spec = parse_input("https://github.com/owner/repo/tree/nope/src")
    with pytest.raises(InputError) as error:
        resolve_tree_reference(spec, lambda ref: False)
    assert error.value.code == "input.reference_not_found"


@pytest.mark.parametrize(
    ("text", "package", "version"),
    [
        ("npx @modelcontextprotocol/server-filesystem", "@modelcontextprotocol/server-filesystem", None),
        ("npx -y @modelcontextprotocol/server-filesystem", "@modelcontextprotocol/server-filesystem", None),
        ("npx --yes server-memory@1.2.3", "server-memory", "1.2.3"),
        ("npx -y @scope/name@2026.8.31", "@scope/name", "2026.8.31"),
        ("npx some-server@latest", "some-server", "latest"),
        ("npx some-server@v1.0.0", "some-server", "1.0.0"),
    ],
)
def test_npx_commands(text: str, package: str, version: str | None) -> None:
    """Accept npx with optional -y or --yes, scoped names and versions"""

    spec = parse_input(text)
    assert spec.kind is InputKind.NPM
    assert spec.package == package
    assert spec.version == version


@pytest.mark.parametrize(
    ("text", "package", "version"),
    [
        ("uvx mcp-server-fetch", "mcp-server-fetch", None),
        ("uvx mcp-server-fetch==2026.8.18", "mcp-server-fetch", "2026.8.18"),
        ("uvx Mcp_Server.Fetch", "mcp-server-fetch", None),
        ("uvx mcp-server-time@1.0.0", "mcp-server-time", "1.0.0"),
        ("uvx mcp-server-time@latest", "mcp-server-time", None),
    ],
)
def test_uvx_commands(text: str, package: str, version: str | None) -> None:
    """Accept uvx with an optional exact version and normalize the name"""

    spec = parse_input(text)
    assert spec.kind is InputKind.PYPI
    assert spec.package == package
    assert spec.version == version


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("", "input.empty"),
        ("   ", "input.empty"),
        ("ssh://git@github.com/owner/repo.git", "input.unsupported_scheme"),
        ("git://github.com/owner/repo.git", "input.unsupported_scheme"),
        ("file:///etc/passwd", "input.unsupported_scheme"),
        ("ext::sh -c touch% /tmp/pwned", "input.unsupported_scheme"),
        ("git@github.com:owner/repo.git", "input.unsupported_scheme"),
        ("http://github.com/owner/repo", "input.unsupported_scheme"),
        ("https://gitlab.com/owner/repo", "input.unsupported_host"),
        ("https://github.com.evil.example/owner/repo", "input.unsupported_host"),
        ("https://user:pass@github.com/owner/repo", "input.credentials_in_url"),
        ("https://github.com:8443/owner/repo", "input.unsupported_host"),
        ("https://github.com/owner/repo/../../etc", "input.path_traversal"),
        ("https://github.com/owner/repo/tree/main/../secret", "input.path_traversal"),
        ("https://github.com/owner/repo/tree/main/%2e%2e/x", "input.invalid_path"),
        ("https://github.com/owner", "input.missing_repository"),
        ("https://github.com/", "input.missing_repository"),
        ("https://github.com/owner/repo/blob/main/server.py", "input.unsupported_github_path"),
        ("https://github.com/owner/repo/tree", "input.missing_reference"),
        ("https://github.com/owner/repo?tab=readme", "input.unexpected_url_parts"),
        ("https://github.com/-bad-/repo", "input.invalid_owner"),
        ("https://github.com/owner/repo extra", "input.unexpected_arguments"),
        ("github.com/owner/repo", "input.unrecognized"),
        ("hello", "input.unrecognized"),
        ("npx", "input.missing_package"),
        ("npx -y", "input.missing_package"),
        ("npx -y pkg --stdio", "input.unexpected_arguments"),
        ("npx pkg /tmp/allowed", "input.unexpected_arguments"),
        ("npx -p other pkg", "input.unexpected_arguments"),
        ("npx github:owner/repo", "input.npm_not_registry"),
        ("npx ./local-folder", "input.npm_not_registry"),
        ("npx https://evil.example/pkg.tgz", "input.npm_not_registry"),
        ("npx Bad_Name", "input.invalid_npm_name"),
        ("npx .hidden", "input.npm_not_registry"),
        ("npx _private", "input.invalid_npm_name"),
        ("npx node_modules", "input.invalid_npm_name"),
        ("npx @scope/a/b", "input.invalid_npm_name"),
        ("npx pkg@^1.0.0", "input.version_range_unsupported"),
        ("npx pkg@", "input.invalid_npm_version"),
        ("uvx", "input.missing_package"),
        ("uvx --from git+https://github.com/x/y tool", "input.unexpected_arguments"),
        ("uvx mcp-server-fetch --help", "input.unexpected_arguments"),
        ("uvx mcp[cli]", "input.pypi_extras_unsupported"),
        ("uvx mcp>=1.0", "input.version_range_unsupported"),
        ("uvx mcp==abc", "input.invalid_pypi_version"),
        ("uvx -bad-", "input.unexpected_arguments"),
        ("uvx bad-", "input.invalid_pypi_name"),
        ("https://github.com/owner/repo\x1b[31m", "input.control_characters"),
        ("npx pkg\u200b", "input.control_characters"),
    ],
)
def test_refused_inputs(text: str, code: str) -> None:
    """Refuse everything that is not one of the accepted formats, with a clear code"""

    with pytest.raises(InputError) as error:
        parse_input(text)
    assert error.value.code == code


def test_too_long_input() -> None:
    """Refuse inputs longer than the limit"""

    with pytest.raises(InputError) as error:
        parse_input("npx " + "a" * 3000)
    assert error.value.code == "input.too_long"


@pytest.mark.parametrize(("text", "expected"), [("src/fetch", "src/fetch"), ("./src/a/", "src/a")])
def test_valid_selection(text: str, expected: str) -> None:
    """Accept relative server folders for --select"""

    assert parse_selection(text) == expected


@pytest.mark.parametrize("text", ["../outside", "/etc", "src/../..", "a\\b", "%2e%2e", ""])
def test_invalid_selection(text: str) -> None:
    """Refuse --select values that could leave the source folder"""

    with pytest.raises(InputError) as error:
        parse_selection(text)
    assert error.value.code == "input.invalid_selection"


def test_add_subdir_to_repository_and_tree() -> None:
    """--select narrows a GitHub spec, before or after reference resolution"""

    repository = add_subdir(parse_input("https://github.com/owner/repo"), "src/a")
    assert repository.kind is InputKind.GITHUB_SUBDIR
    assert repository.subdir == "src/a"
    tree = add_subdir(parse_input("https://github.com/owner/repo/tree/main/src"), "a")
    assert tree.tree_path == "main/src/a"
