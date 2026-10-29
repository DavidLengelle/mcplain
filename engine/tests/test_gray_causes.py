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
