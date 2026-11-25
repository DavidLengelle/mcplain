"""A call that may reach server code but that the call graph cannot resolve leaves the tool unfollowed, with its precise cause"""

from pathlib import Path

import pytest

from mcplain.analyze import analyze_directory
from mcplain.capabilities import Capability
from mcplain.models import CoverageKind, GrayCase, TrackingGap, UnresolvedCause, VerdictColor

CORPUS = Path(__file__).parent / "fixtures" / "corpus"

CASES: list[tuple[str, str, UnresolvedCause]] = [
    ("notes-alias-js", "show_note", UnresolvedCause.ALIAS),
    ("notes-alias-py", "show_note", UnresolvedCause.ALIAS),
    ("notes-factory-js", "show_note", UnresolvedCause.RETURNED_FUNCTION),
    ("notes-closure-py", "show_note", UnresolvedCause.RETURNED_FUNCTION),
    ("notes-lambda-py", "show_note", UnresolvedCause.LAMBDA),
    ("notes-partial-py", "show_note", UnresolvedCause.PARTIAL),
    ("notes-object-method-js", "show_note", UnresolvedCause.OBJECT_METHOD),
    ("notes-object-arrow-js", "show_note", UnresolvedCause.OBJECT_METHOD),
    ("notes-wrapper-js", "show_note", UnresolvedCause.WRAPPER),
    ("notes-call-apply-js", "show_note", UnresolvedCause.CALL_APPLY),
    ("notes-server-method-js", "show_note", UnresolvedCause.SERVER_METHOD),
    ("calculator-operator-table", "calculate", UnresolvedCause.FUNCTION_TABLE),
]


@pytest.mark.parametrize(("name", "tool_name", "cause"), CASES)
def test_an_unresolved_call_keeps_the_tool_unfollowed(name: str, tool_name: str, cause: UnresolvedCause) -> None:
    """The tool gets the unresolved_call gap with its cause, counts in what was not checked, and the verdict is gray"""

    result = analyze_directory(CORPUS / "gray" / name)
    tool = next(item for item in result.servers[0].tools if item.name == tool_name)
    assert tool.gaps == [TrackingGap.UNRESOLVED_CALL]
    assert [place.cause for place in tool.gap_places] == [cause]
    assert result.verdict.color is VerdictColor.GRAY
    assert result.verdict.gray_case is GrayCase.INCOMPLETE_TRACKING
    coverage = result.verdict.coverage
    assert coverage is not None
    assert coverage.tools_followed == 0
    calls = [item for item in coverage.not_checked if item.kind is CoverageKind.CALL]
    assert [(item.name, item.reason, item.cause) for item in calls] == [(tool_name, TrackingGap.UNRESOLVED_CALL.value, cause)]


def test_a_direct_call_stays_followed_and_green() -> None:
    """The witness: the same server with a direct call is followed, lights its lamp and stays green"""

    result = analyze_directory(CORPUS / "green" / "notes-direct-call")
    tool = result.servers[0].tools[0]
    assert tool.gaps == []
    assert {finding.capability for finding in tool.findings} == {Capability.FS_READ}
    assert result.verdict.color is VerdictColor.GREEN


def test_a_lambda_without_code_is_no_gap(tmp_path: Path) -> None:
    """A lambda that holds no call and no finding cannot do anything: calling it by name leaves nothing unread"""

    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.1.0"\ndependencies = ["fastmcp>=2"]\n')
    (tmp_path / "server.py").write_text(
        "from fastmcp import FastMCP\n\nfirst = lambda items: items[0]\n\n\n"
        "def build() -> FastMCP:\n    mcp = FastMCP(\"x\")\n\n    @mcp.tool()\n"
        "    def pick(items: list[str]) -> str:\n        \"\"\"Pick the first item\"\"\"\n        return first(items)\n\n"
        "    return mcp\n"
    )
    result = analyze_directory(tmp_path)
    assert result.servers[0].tools[0].gaps == []
    assert result.verdict.color is VerdictColor.GREEN


def test_a_map_lookup_is_no_object_method(tmp_path: Path) -> None:
    """handlers.get(name) on a Map of package functions is a lookup, not a method of an object literal"""

    (tmp_path / "package.json").write_text('{"name": "x", "version": "1.0.0", "dependencies": {"@modelcontextprotocol/sdk": "^1"}}')
    (tmp_path / "index.js").write_text(
        'import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";\n'
        'function upper(text) { return text.toUpperCase(); }\n'
        'const handlers = new Map([["upper", upper]]);\n'
        'export function build() {\n'
        '  const server = new McpServer({ name: "x", version: "1.0.0" });\n'
        '  server.registerTool("upper", { description: "Upper case" }, async (args) => {\n'
        '    const known = handlers.has("upper");\n'
        '    return { content: [{ type: "text", text: String(known) }] };\n'
        '  });\n'
        '  return server;\n'
        '}\n'
    )
    result = analyze_directory(tmp_path)
    assert result.servers[0].tools[0].gaps == []


def test_names_that_hold_each_other_end_the_search(tmp_path: Path) -> None:
    """state = next(state), or two names wrapped in each other: the search stops at its depth limit, without a crash"""

    (tmp_path / "package.json").write_text('{"name": "x", "version": "1.0.0", "dependencies": {"@modelcontextprotocol/sdk": "^1"}}')
    (tmp_path / "index.js").write_text(
        'import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";\n'
        "function next(value) { return value; }\n"
        "export function build() {\n"
        '  const server = new McpServer({ name: "x", version: "1.0.0" });\n'
        "  let state = next(state);\n"
        "  let first = next(second);\n"
        "  let second = next(first);\n"
        '  server.registerTool("step", { description: "Step" }, async (args) => {\n'
        "    state = next(state);\n"
        "    first(args);\n"
        "    state(args);\n"
        '    return { content: [{ type: "text", text: "ok" }] };\n'
        "  });\n"
        "  return server;\n"
        "}\n"
    )
    result = analyze_directory(tmp_path)
    assert result.status.value == "ok"
    assert result.servers[0].tools[0].gaps == [TrackingGap.UNRESOLVED_CALL]
