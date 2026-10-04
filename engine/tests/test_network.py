"""Tests against real registries, disabled by default: run with pytest -m network"""

import pytest

from mcplain.analyze import analyze_input
from mcplain.models import AnalysisStatus, SourceKind, SourceOrigin

pytestmark = pytest.mark.network


def test_github_subfolder_resolves_to_published_package() -> None:
    """The fetch server folder on GitHub is analyzed through its PyPI package"""

    result = analyze_input("https://github.com/modelcontextprotocol/servers/tree/main/src/fetch")
    assert result.status is AnalysisStatus.OK
    assert result.source is not None
    assert result.source.kind is SourceKind.PYPI
    assert result.source.origin is SourceOrigin.PUBLISHED_PACKAGE
    assert [tool.name for tool in result.servers[0].tools] == ["fetch"]


def test_npm_filesystem_server() -> None:
    """The filesystem server from npm declares its tools with registerTool"""

    result = analyze_input("npx -y @modelcontextprotocol/server-filesystem")
    assert result.status is AnalysisStatus.OK
    names = {tool.name for tool in result.servers[0].tools}
    assert {"read_text_file", "write_file", "list_directory"} <= names


def test_pypi_fetch_server() -> None:
    """The fetch server from PyPI is downloaded as a verified wheel"""

    result = analyze_input("uvx mcp-server-fetch")
    assert result.status is AnalysisStatus.OK
    assert result.source is not None
    assert result.source.artifact == "wheel"
    assert result.source.integrity is not None
