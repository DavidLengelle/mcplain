"""Tests against real registries, disabled by default: run with pytest -m network"""

import pytest

from mcplain.analyze import analyze_input
from mcplain.capabilities import Capability
from mcplain.models import AnalysisStatus, ReputationStatus, SourceKind, SourceOrigin, UrlKind, VerdictColor

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


def test_real_fetch_tool_reaches_the_network_through_fetch_url() -> None:
    """The fetch tool shows network via fetch_url with a dynamic URL"""

    result = analyze_input("uvx mcp-server-fetch")
    [fetch] = result.servers[0].tools
    network = [finding for finding in fetch.findings if finding.capability is Capability.NETWORK]
    assert any(
        [step.function for step in finding.call_chain] == ["fetch_url"] and finding.url_kind is UrlKind.DYNAMIC
        for finding in network
    )


def test_real_filesystem_tools_all_show_capabilities() -> None:
    """write_file writes via writeFileContent and every tool but list_allowed_directories has a capability"""

    result = analyze_input("npx -y @modelcontextprotocol/server-filesystem@latest")
    tools = {tool.name: tool for tool in result.servers[0].tools}
    write = [finding for finding in tools["write_file"].findings if finding.capability is Capability.FS_WRITE]
    assert [step.function for step in write[0].call_chain] == ["writeFileContent"]
    empty = sorted(name for name, tool in tools.items() if not tool.findings)
    assert empty == ["list_allowed_directories"]


def test_reputation_is_checked_on_osv() -> None:
    """The fetch server and its direct dependencies are checked on OSV.dev, with no malicious report"""

    result = analyze_input("uvx mcp-server-fetch")
    assert result.reputation is not None
    assert result.reputation.status is ReputationStatus.CHECKED
    assert result.reputation.queried >= 5
    assert result.reputation.packages == []


def test_fetch_is_orange_by_open_network() -> None:
    """The fetch tool reaches any address the AI gives: orange by O01, and no red rule"""

    verdict = analyze_input("uvx mcp-server-fetch").verdict
    rules = {alert.rule for alert in verdict.alerts}
    assert verdict.color is VerdictColor.ORANGE
    assert "O01" in rules
    assert not any(rule.startswith("R") for rule in rules)
    open_network = [alert for alert in verdict.alerts if alert.rule == "O01"]
    assert open_network[0].function == "fetch_url"


def test_filesystem_is_orange_by_powerful_capability() -> None:
    """The filesystem server writes files: orange by O08, no red rule and no annotation mismatch"""

    verdict = analyze_input("npx -y @modelcontextprotocol/server-filesystem").verdict
    rules = {alert.rule for alert in verdict.alerts}
    assert verdict.color is VerdictColor.ORANGE
    assert "O08" in rules
    assert "O04" not in rules
    assert not any(rule.startswith("R") for rule in rules)
