"""Tests for incomplete tracking, dispatch tables, package class instances and code outside the tools"""

from pathlib import Path

import pytest

from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.adapters.python import PythonAdapter
from mcplain.capabilities import Capability
from mcplain.config import Limits
from mcplain.models import OutsideKind, ServerAnalysis, Tool, TrackingGap

PYTHON_HEADER = '''import os
import subprocess
from mcp.server import Server
from mcp.types import Tool
from fastmcp import FastMCP

'''
JAVASCRIPT_HEADER = '''import { execSync } from "child_process";
import fs from "fs";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

'''


def write(folder: Path, name: str, text: str) -> None:
    """Write one source file"""

    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def python(tmp_path: Path, body: str, limits: Limits = Limits()) -> ServerAnalysis:
    """Analyze one Python server file"""

    write(tmp_path, "server.py", PYTHON_HEADER + body)
    return PythonAdapter(limits).analyze(tmp_path)


def javascript(tmp_path: Path, body: str) -> ServerAnalysis:
    """Analyze one JavaScript server file"""

    write(tmp_path, "index.js", JAVASCRIPT_HEADER + body)
    return JavaScriptAdapter().analyze(tmp_path)


def tool(analysis: ServerAnalysis, name: str) -> Tool:
    """Return the tool with a given name"""

    for item in analysis.tools:
        if item.name == name:
            return item
    raise AssertionError(name)


def capabilities(item: Tool) -> set[Capability]:
    """Return the capabilities found for a tool"""

    return {finding.capability for finding in item.findings}


LOW_LEVEL_TABLE = '''

def run_echo(arguments):
    return subprocess.run(["echo", arguments["text"]])


def remove_file(arguments):
    os.remove(arguments["path"])


HANDLERS = {"echo": run_echo, "remove": remove_file}


def build():
    server = Server("x")

    @server.list_tools()
    async def list_tools():
        return [Tool(name="echo", description="Echo", inputSchema={}), Tool(name="remove", description="Remove", inputSchema={})]

    @server.call_tool()
    async def call_tool(name, arguments):
        {call}
    return server
'''


@pytest.mark.parametrize(
    "call",
    [
        "return HANDLERS[name](arguments)",
        "return HANDLERS.get(name)(arguments)",
        "handler = HANDLERS[name]\n        return handler(arguments)",
    ],
)
def test_python_dispatch_table_gives_each_tool_its_handler(tmp_path: Path, call: str) -> None:
    """A dict of handlers keyed by tool name sends each handler to its own tool"""

    analysis = python(tmp_path, LOW_LEVEL_TABLE.replace("{call}", call))
    assert capabilities(tool(analysis, "echo")) == {Capability.PROCESS_EXEC}
    assert capabilities(tool(analysis, "remove")) == {Capability.FS_WRITE}
    assert tool(analysis, "echo").gaps == []
    assert [finding.function for finding in tool(analysis, "remove").findings] == ["remove_file"]


@pytest.mark.parametrize(
    ("call", "gap"),
    [
        ("return self_made[name](arguments)", TrackingGap.DICT_CALL),
        ("return getattr(module, 'handle_' + name)(arguments)", TrackingGap.DYNAMIC_ATTRIBUTE),
        ("return globals()[name](arguments)", TrackingGap.DYNAMIC_ATTRIBUTE),
        ("handler = registry.get(name)\n        return handler(arguments)", TrackingGap.DICT_CALL),
    ],
)
def test_python_unresolved_dispatch_is_a_gap(tmp_path: Path, call: str, gap: TrackingGap) -> None:
    """A call through an unknown dict, getattr or globals() makes the tracking incomplete"""

    analysis = python(tmp_path, LOW_LEVEL_TABLE.replace("{call}", call))
    assert tool(analysis, "echo").findings == []
    assert tool(analysis, "echo").gaps == [gap]


def test_python_method_of_unknown_object_is_a_gap(tmp_path: Path) -> None:
    """obj.search() where search is a method of a package class, but obj has no known type"""

    analysis = python(
        tmp_path,
        '''

class Index:
    def search(self, text):
        return subprocess.run(["echo", text])


def build(index):
    mcp = FastMCP("x")

    @mcp.tool()
    def find(text: str) -> str:
        """Find text"""
        return index.search(text)

    @mcp.tool()
    def count(text: str) -> int:
        """Count words"""
        return text.split().count("x")

    return mcp
''',
    )
    assert tool(analysis, "find").gaps == [TrackingGap.UNKNOWN_TYPE]
    assert tool(analysis, "count").gaps == []


def test_python_instance_of_package_class_is_followed(tmp_path: Path) -> None:
    """A variable or self attribute built from a package class gives its methods a known type"""

    analysis = python(
        tmp_path,
        '''

class Index:
    def search(self, text):
        return subprocess.run(["echo", text])


class Service:
    def __init__(self):
        self.index = Index()

    def lookup(self, text):
        return self.index.search(text)


def build():
    mcp = FastMCP("x")

    @mcp.tool()
    def find(text: str) -> str:
        """Find text"""
        index = Index()
        return index.search(text)

    @mcp.tool()
    def deep(text: str) -> str:
        """Find text through a service"""
        service = Service()
        return service.lookup(text)

    return mcp
''',
    )
    assert tool(analysis, "find").gaps == []
    assert capabilities(tool(analysis, "find")) == {Capability.PROCESS_EXEC}
    assert [step.function for step in tool(analysis, "deep").findings[0].call_chain] == [
        "Service.lookup",
        "Index.search",
    ]


def test_python_homonyms_are_ambiguous(tmp_path: Path) -> None:
    """Two module-level functions with the same name make the call ambiguous, overloads do not"""

    analysis = python(
        tmp_path,
        '''from typing import overload


def helper():
    return 1


def helper():
    return 2


@overload
def single(x: int) -> int: ...


@overload
def single(x: str) -> str: ...


def single(x):
    return x


def build():
    mcp = FastMCP("x")

    @mcp.tool()
    def twice() -> int:
        """Call a duplicated helper"""
        return helper()

    @mcp.tool()
    def typed() -> int:
        """Call an overloaded helper"""
        return single(1)

    return mcp
''',
    )
    assert tool(analysis, "twice").gaps == [TrackingGap.AMBIGUOUS]
    assert tool(analysis, "typed").gaps == []


def test_max_depth_is_a_gap(tmp_path: Path) -> None:
    """When the depth limit stops the walk before a call, the tracking is incomplete"""

    body = '''

def one():
    two()


def two():
    os.remove("x")


def build():
    mcp = FastMCP("x")

    @mcp.tool()
    def deep() -> None:
        """Go deep"""
        one()

    return mcp
'''
    shallow = python(tmp_path, body, Limits(max_call_depth=1))
    assert tool(shallow, "deep").gaps == [TrackingGap.MAX_DEPTH]
    enough = python(tmp_path, body, Limits(max_call_depth=2))
    assert tool(enough, "deep").gaps == []


JAVASCRIPT_TABLE = '''function runEcho(args) {
  return execSync("echo hello");
}

function removeFile(args) {
  return fs.unlinkSync(args.path);
}

const handlers = { echo: runEcho, "remove": removeFile };
const byMap = new Map([["echo", runEcho], ["remove", removeFile]]);

export function build(server) {
  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: [
    { name: "echo", description: "Echo", inputSchema: {} },
    { name: "remove", description: "Remove", inputSchema: {} },
  ] }));
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    {call}
  });
}
'''


@pytest.mark.parametrize(
    "call",
    [
        "return handlers[request.params.name](request.params.arguments);",
        "const handler = handlers[request.params.name];\n    return handler(request.params.arguments);",
        "return byMap.get(request.params.name)(request.params.arguments);",
    ],
)
def test_javascript_dispatch_table_gives_each_tool_its_handler(tmp_path: Path, call: str) -> None:
    """An object or a Map of handlers keyed by tool name sends each handler to its own tool"""

    analysis = javascript(tmp_path, JAVASCRIPT_TABLE.replace("{call}", call))
    assert capabilities(tool(analysis, "echo")) == {Capability.PROCESS_EXEC}
    assert capabilities(tool(analysis, "remove")) == {Capability.FS_WRITE}
    assert tool(analysis, "remove").gaps == []


@pytest.mark.parametrize(
    "call",
    [
        "return registry[request.params.name](request.params.arguments);",
        "return this[request.params.name](request.params.arguments);",
        "return registry.get(request.params.name)(request.params.arguments);",
    ],
)
def test_javascript_unresolved_dispatch_is_a_gap(tmp_path: Path, call: str) -> None:
    """A call through an unknown object, Map or this[name] makes the tracking incomplete"""

    analysis = javascript(tmp_path, JAVASCRIPT_TABLE.replace("{call}", call))
    assert tool(analysis, "echo").findings == []
    assert tool(analysis, "echo").gaps == [TrackingGap.DICT_CALL]


def test_javascript_instances_and_unknown_objects(tmp_path: Path) -> None:
    """new Store() gives a known type, an untyped parameter with a package method name does not"""

    analysis = javascript(
        tmp_path,
        '''class Store {
  purge(path) {
    return fs.unlinkSync(path);
  }
}

export function build(server, store) {
  server.tool("known", "Known", async ({ path }) => {
    const local = new Store();
    return local.purge(path);
  });
  server.tool("unknown", "Unknown", async ({ path }) => store.purge(path));
  server.tool("log", "Log", async ({ path }) => console.log(path));
}
''',
    )
    assert capabilities(tool(analysis, "known")) == {Capability.FS_WRITE}
    assert tool(analysis, "known").gaps == []
    assert tool(analysis, "unknown").gaps == [TrackingGap.UNKNOWN_TYPE]
    assert tool(analysis, "log").gaps == []


def test_python_code_outside_tools_is_split_by_when_it_runs(tmp_path: Path) -> None:
    """Module-level code and entry points run at startup, setup.py at install, the rest is never called"""

    write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "x"\ndependencies = ["mcp"]\n\n[project.scripts]\nx = "pkg.server:main"\n',
    )
    write(tmp_path, "pkg/__init__.py", "")
    write(
        tmp_path,
        "pkg/server.py",
        '''import os
import subprocess

TOKEN = os.environ.get("API_TOKEN")


def prepare():
    os.makedirs("/tmp/x.invalid")


def unused():
    subprocess.run(["echo", "never"])


def main():
    prepare()
''',
    )
    write(tmp_path, "setup.py", 'import os\n\n\ndef helper():\n    os.remove("x")\n')
    analysis = PythonAdapter().analyze(tmp_path)
    kinds = {(finding.capability, finding.outside) for finding in analysis.findings}
    assert (Capability.ENV_READ_SECRET, OutsideKind.STARTUP) in kinds
    assert (Capability.FS_WRITE, OutsideKind.STARTUP) in kinds
    assert (Capability.PROCESS_EXEC, OutsideKind.NEVER_CALLED) in kinds
    assert [finding.outside for finding in analysis.findings if finding.file == "setup.py"] == [OutsideKind.INSTALL]


def test_javascript_callbacks_at_module_level(tmp_path: Path) -> None:
    """A map callback at module level runs at startup, an event callback is never called by a tool"""

    write(
        tmp_path,
        "package.json",
        '{"name": "x", "bin": "index.js", "scripts": {"postinstall": "node scripts/setup.js"}}',
    )
    write(
        tmp_path,
        "index.js",
        '''import fs from "fs";

const roots = process.argv.slice(2).map((dir) => fs.realpathSync(dir));
process.on("SIGHUP", () => fs.rmSync("/tmp/x.invalid"));
''',
    )
    write(tmp_path, "scripts/setup.js", 'import fs from "fs";\n\nexport function prepare() {\n  fs.mkdirSync("cache");\n}\n')
    analysis = JavaScriptAdapter().analyze(tmp_path)
    kinds = {(finding.file, finding.capability, finding.outside) for finding in analysis.findings}
    assert ("index.js", Capability.FS_READ, OutsideKind.STARTUP) in kinds
    assert ("index.js", Capability.FS_WRITE, OutsideKind.NEVER_CALLED) in kinds
    assert ("scripts/setup.js", Capability.FS_WRITE, OutsideKind.INSTALL) in kinds
