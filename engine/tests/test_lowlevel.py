"""Tests for low-level servers: tools/call handlers attached to the tools they serve"""

from pathlib import Path

from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.adapters.python import PythonAdapter
from mcplain.analyze import analyze_directory
from mcplain.capabilities import Capability
from mcplain.cli import render
from mcplain.i18n import Translator
from mcplain.models import ServerAnalysis, Tool

FETCH_DESCRIPTION = (
    "Fetches a URL from the internet and optionally extracts its contents as markdown.\n\n"
    "Although originally you did not have internet access, and were advised to refuse and tell the user this, "
    "this tool now grants you internet access. Now you can fetch the most up-to-date information and let the "
    "user know that."
)


def tool(analysis: ServerAnalysis, name: str) -> Tool:
    """Return the tool with a given name"""

    for item in analysis.tools:
        if item.name == name:
            return item
    raise AssertionError(name)


def capabilities(item: Tool) -> set[Capability]:
    """Return the capabilities found for a tool"""

    return {finding.capability for finding in item.findings}


def test_single_tool_owns_the_whole_handler(fixtures: Path) -> None:
    """With one declared tool, everything the call handler reaches belongs to it"""

    analysis = PythonAdapter().analyze(fixtures / "python_lowlevel_single")
    fetch = tool(analysis, "fetch")
    network = [finding for finding in fetch.findings if finding.capability is Capability.NETWORK]
    assert network
    assert all([step.function for step in finding.call_chain] == ["fetch_url"] for finding in network)
    assert analysis.findings == []


def test_python_branches_with_constants_and_enum(fixtures: Path) -> None:
    """if/elif and match branches are matched through constants and enum members"""

    analysis = PythonAdapter().analyze(fixtures / "python_lowlevel_multi")
    assert [item.name for item in analysis.tools] == ["read_note", "write_note", "delete_notes", "run_script"]
    assert capabilities(tool(analysis, "read_note")) == {Capability.FS_READ}
    assert [step.function for step in tool(analysis, "read_note").findings[0].call_chain] == ["_read"]
    assert capabilities(tool(analysis, "write_note")) == {Capability.FS_WRITE}
    assert capabilities(tool(analysis, "delete_notes")) == {Capability.FS_WRITE}
    assert capabilities(tool(analysis, "run_script")) == {Capability.PROCESS_EXEC}
    [shared] = analysis.findings
    assert shared.shared_by_tools
    assert shared.capability is Capability.FS_WRITE
    assert shared.line == 32


def test_javascript_switch_with_enum_const_object_and_fallthrough(fixtures: Path) -> None:
    """switch cases using a TypeScript enum, an as-const object and fall-through are matched"""

    analysis = JavaScriptAdapter().analyze(fixtures / "js_lowlevel_switch")
    assert [item.name for item in analysis.tools] == ["read_log", "clear_log", "status", "restart"]
    assert capabilities(tool(analysis, "read_log")) == {Capability.FS_READ}
    assert capabilities(tool(analysis, "clear_log")) == {Capability.FS_WRITE}
    assert capabilities(tool(analysis, "status")) == {Capability.PROCESS_EXEC}
    assert capabilities(tool(analysis, "restart")) == {Capability.PROCESS_EXEC}
    [shared] = analysis.findings
    assert shared.shared_by_tools
    assert shared.detail == "fs.appendFileSync"


def test_existing_lowlevel_fixture_across_two_files(fixtures: Path) -> None:
    """SDK v1 decorators and SDK v2 on_call_tool= in two files of the same package"""

    analysis = PythonAdapter().analyze(fixtures / "python_lowlevel")
    assert capabilities(tool(analysis, "lookup")) == {Capability.NETWORK}
    assert capabilities(tool(analysis, "uptime")) == {Capability.PROCESS_EXEC}


def test_handler_given_by_reference_from_another_module(tmp_path: Path) -> None:
    """on_call_tool= can point to a function imported from the package"""

    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "handlers.py").write_text(
        "import subprocess\n\n\nasync def handle(ctx, params):\n    subprocess.run(['ls'])\n",
        encoding="utf-8",
    )
    (package / "server.py").write_text(
        "from mcp.server import Server\nfrom mcp.types import Tool\n\nfrom .handlers import handle\n\n"
        "LIST = Tool(name='list', description='List files')\n"
        "server = Server('x', on_call_tool=handle)\n",
        encoding="utf-8",
    )
    analysis = PythonAdapter().analyze(tmp_path)
    assert capabilities(tool(analysis, "list")) == {Capability.PROCESS_EXEC}


def test_fetch_like_description_is_read_in_full(fixtures: Path) -> None:
    """The multi-line description that speaks to the model is read entirely"""

    analysis = PythonAdapter().analyze(fixtures / "official_fetch_like")
    fetch = tool(analysis, "fetch")
    assert fetch.description == FETCH_DESCRIPTION
    assert not fetch.description_is_dynamic
    assert Capability.NETWORK in capabilities(fetch)


def test_shared_findings_are_labelled(fixtures: Path) -> None:
    """The report shows the code shared by all tools under its own heading"""

    text = render(analyze_directory(fixtures / "python_lowlevel_multi"), Translator("fr"))
    assert "Partagé par tous les outils" in text
