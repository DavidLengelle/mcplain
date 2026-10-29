"""Tests for the gray causes found by the bench: each fix reproduces its pattern on harmless code"""

from pathlib import Path

from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.analyze import analyze_directory
from mcplain.capabilities import Capability
from mcplain.models import ServerAnalysis, Tool, VerdictColor


def tool(analysis: ServerAnalysis, name: str) -> Tool:
    """Return one tool of an analysis by name"""

    return next(item for item in analysis.tools if item.name == name)


def capabilities(item: Tool) -> set[Capability]:
    """Return the capabilities found for a tool"""

    return {finding.capability for finding in item.findings}


def write(folder: Path, name: str, text: str) -> None:
    """Write one file of a test package"""

    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_python_methods_of_a_class_reexported_by_a_package_are_followed(fixtures: Path) -> None:
    """from .storage import NoteStore, where storage/__init__.py re-exports it: instance and class methods are followed"""

    result = analyze_directory(fixtures / "python_imported_class")
    server = result.servers[0]
    for name in ("read_note", "count_notes"):
        assert capabilities(tool(server, name)) == {Capability.FS_READ}
        assert tool(server, name).gaps == []
    chain = [step.function for step in tool(server, "read_note").findings[0].call_chain]
    assert chain == ["NoteStore.read"]
    assert result.verdict.color is VerdictColor.GREEN


def test_javascript_methods_of_a_class_reexported_by_an_index_are_followed(tmp_path: Path) -> None:
    """import { Store } from "./lib/index.js", which re-exports it: the method of the instance is followed"""

    write(tmp_path, "package.json", '{"name": "notes", "type": "module"}')
    write(tmp_path, "lib/store.js", 'import fs from "fs";\nexport class Store {\n  read(name) {\n    return fs.readFileSync(name, "utf8");\n  }\n}\n')
    write(tmp_path, "lib/index.js", 'export { Store } from "./store.js";\n')
    write(
        tmp_path,
        "index.js",
        'import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";\nimport { Store } from "./lib/index.js";\n'
        'const server = new McpServer({ name: "notes", version: "1.0.0" });\n'
        'server.registerTool("read_note", { description: "Read a note" }, async () => {\n'
        '  const store = new Store();\n  return { content: [{ type: "text", text: store.read("a.txt") }] };\n});\n',
    )
    analysis = JavaScriptAdapter().analyze(tmp_path)
    assert capabilities(tool(analysis, "read_note")) == {Capability.FS_READ}
    assert tool(analysis, "read_note").gaps == []


def test_a_table_of_outside_functions_without_capability_is_followed(fixtures: Path) -> None:
    """OPERATORS[type(node.op)](left, right), with operator.add and the like: nothing is left unread"""

    result = analyze_directory(fixtures / "python_operator_table")
    calculate = tool(result.servers[0], "calculate")
    assert calculate.gaps == []
    assert calculate.findings == []
    assert result.verdict.color is VerdictColor.GREEN


TABLE_SERVER = '''import operator
import subprocess

from mcp.server import MCPServer

from helpers import shout

mcp = MCPServer("x")
{table}


@mcp.tool()
def run(name: str, value: str) -> str:
    """Run one action"""
    return str(TABLE[name](value))
'''


def table_tool(tmp_path: Path, table: str) -> Tool:
    """Analyze a server that calls through one dict and return its tool"""

    write(tmp_path, "pyproject.toml", '[project]\nname = "x"\nversion = "1"\ndependencies = ["mcp>=2"]\n')
    write(tmp_path, "helpers.py", 'import os\n\n\ndef shout(value):\n    """Write the value"""\n    os.remove(value)\n')
    write(tmp_path, "server.py", TABLE_SERVER.replace("{table}", table))
    return tool(analyze_directory(tmp_path).servers[0], "run")


def test_a_table_with_a_package_function_follows_it(tmp_path: Path) -> None:
    """A computed key still reaches every package function of the table"""

    run = table_tool(tmp_path, "TABLE = {len: shout, str: operator.neg}")
    assert run.gaps == []
    assert capabilities(run) == {Capability.FS_WRITE}


def test_a_table_that_holds_a_capability_keeps_its_gap(tmp_path: Path) -> None:
    """subprocess.run in a table is not inert: the call stays not followed"""

    assert table_tool(tmp_path, 'TABLE = {"a": operator.add, "b": subprocess.run}').gaps == ["dict_call"]


def test_a_table_with_an_unknown_value_keeps_its_gap(tmp_path: Path) -> None:
    """A local name or a lambda is not known: the call stays not followed"""

    assert table_tool(tmp_path, 'action = None\nTABLE = {"a": operator.add, "b": action}').gaps == ["dict_call"]
    assert table_tool(tmp_path, 'TABLE = {"a": lambda value: value}').gaps == ["dict_call"]
    assert table_tool(tmp_path, "TABLE = {}").gaps == ["dict_call"]
