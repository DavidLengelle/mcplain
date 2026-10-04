"""Tests for the title and behavior hints declared by tool authors"""

from pathlib import Path

from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.adapters.python import PythonAdapter
from mcplain.analyze import analyze_directory
from mcplain.cli import render
from mcplain.i18n import Translator
from mcplain.models import ServerAnalysis, Tool


def tool(analysis: ServerAnalysis, name: str) -> Tool:
    """Return the tool with a given name"""

    for item in analysis.tools:
        if item.name == name:
            return item
    raise AssertionError(name)


def python(tmp_path: Path, source: str) -> ServerAnalysis:
    """Analyze one Python file"""

    (tmp_path / "server.py").write_text(source, encoding="utf-8")
    return PythonAdapter().analyze(tmp_path)


def typescript(tmp_path: Path, source: str) -> ServerAnalysis:
    """Analyze one TypeScript file"""

    (tmp_path / "index.ts").write_text(source, encoding="utf-8")
    return JavaScriptAdapter().analyze(tmp_path)


def test_python_decorator_forms(tmp_path: Path) -> None:
    """A dict, ToolAnnotations in snake_case (SDK v2) and in camelCase (SDK v1) are read"""

    analysis = python(
        tmp_path,
        '''from mcp.server import MCPServer
from mcp.types import ToolAnnotations

mcp = MCPServer("x")
READ_ONLY = True


@mcp.tool(title="Search the catalog", annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def search() -> str:
    """Search"""
    return ""


@mcp.tool(annotations={"title": "Delete everything", "readOnlyHint": False, "destructiveHint": True})
def delete() -> str:
    """Delete"""
    return ""


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=READ_ONLY, idempotentHint=None))
def computed() -> str:
    """Computed"""
    return ""


@mcp.tool(annotations=build_annotations())
def dynamic() -> str:
    """Dynamic"""
    return ""
''',
    )
    search = tool(analysis, "search")
    assert search.title == "Search the catalog"
    assert search.annotations == {"readOnlyHint": True, "openWorldHint": False}
    delete = tool(analysis, "delete")
    assert delete.title == "Delete everything"
    assert delete.annotations == {"readOnlyHint": False, "destructiveHint": True}
    assert tool(analysis, "computed").annotations == {"readOnlyHint": "computed"}
    assert tool(analysis, "dynamic").annotations_are_dynamic


def test_python_low_level_tool(tmp_path: Path) -> None:
    """Tool(annotations=...) of the low-level server is read"""

    analysis = python(
        tmp_path,
        '''from mcp.types import Tool, ToolAnnotations

WIPE = Tool(
    name="wipe",
    title="Wipe the disk",
    description="Wipe",
    inputSchema={"type": "object", "properties": {}},
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
''',
    )
    wipe = tool(analysis, "wipe")
    assert wipe.title == "Wipe the disk"
    assert wipe.annotations == {"readOnlyHint": False, "destructiveHint": True}


def test_typescript_forms(tmp_path: Path) -> None:
    """registerTool, server.tool, addTool and low-level objects carry annotations"""

    analysis = typescript(
        tmp_path,
        """const flags = computeFlags();
server.registerTool(
  "clear-catalog",
  {
    title: "Clear the catalog",
    description: "Remove every product",
    annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: true },
  },
  async () => ({ content: [] }),
);
server.tool("peek", "Peek", { id: z.string() }, { readOnlyHint: true, openWorldHint: flags.open }, async () => ({}));
server.addTool({ name: "ping", description: "Ping", annotations: flags, execute: async () => "pong" });
server.setRequestHandler("tools/list", async () => ({
  tools: [{ name: "list", description: "List", inputSchema: {}, annotations: { readOnlyHint: true } }],
}));
""",
    )
    clear = tool(analysis, "clear-catalog")
    assert clear.title == "Clear the catalog"
    assert clear.annotations == {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True}
    assert tool(analysis, "peek").annotations == {"readOnlyHint": True, "openWorldHint": "computed"}
    assert tool(analysis, "ping").annotations_are_dynamic
    assert tool(analysis, "list").annotations == {"readOnlyHint": True}


def test_announcements_are_displayed(tmp_path: Path) -> None:
    """The report shows what each tool announces"""

    (tmp_path / "package.json").write_text('{"name": "x", "dependencies": {"@modelcontextprotocol/sdk": "1"}}')
    typescript(
        tmp_path,
        """server.registerTool("wipe", { title: "Wipe", description: "Wipe", annotations: { readOnlyHint: false, destructiveHint: true } }, async () => ({}));
""",
    )
    text = render(analyze_directory(tmp_path), Translator("fr"))
    assert 'il annonce : titre "Wipe"; lecture seule : non; destructif : oui' in text
