"""Tests for the call graph that attributes helper findings to tools"""

from pathlib import Path

from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.adapters.python import PythonAdapter
from mcplain.analyze import analyze_directory
from mcplain.capabilities import Capability
from mcplain.cli import render
from mcplain.config import Limits
from mcplain.i18n import Translator
from mcplain.models import Finding, ServerAnalysis, Tool


def tool(analysis: ServerAnalysis, name: str) -> Tool:
    """Return the tool with a given name"""

    for item in analysis.tools:
        if item.name == name:
            return item
    raise AssertionError(name)


def first(item: Tool, capability: Capability) -> Finding:
    """Return the nearest finding of a capability in a tool"""

    for finding in item.findings:
        if finding.capability is capability:
            return finding
    raise AssertionError(capability)


def chain(finding: Finding) -> list[str]:
    """Return the function names crossed to reach a finding"""

    return [step.function for step in finding.call_chain]


def write(folder: Path, name: str, text: str) -> None:
    """Write one source file"""

    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_js_helper_in_another_file(fixtures: Path) -> None:
    """A write done by a helper of ./lib.js belongs to the tool, via the helper"""

    analysis = JavaScriptAdapter().analyze(fixtures / "js_helper_call")
    finding = first(tool(analysis, "save_note"), Capability.FS_WRITE)
    assert chain(finding) == ["saveNote"]
    assert (finding.file, finding.line) == ("lib.js", 4)
    assert analysis.findings == []


def test_js_handlers_given_by_reference(fixtures: Path) -> None:
    """A const handler and a handler imported from a .ts file count as the tool body"""

    analysis = JavaScriptAdapter().analyze(fixtures / "js_handler_ref")
    read = first(tool(analysis, "read"), Capability.FS_READ)
    assert chain(read) == []
    assert read.function == "readHandler"
    delete = first(tool(analysis, "delete"), Capability.FS_WRITE)
    assert chain(delete) == []
    assert delete.file == "src/handlers.ts"


def test_python_helpers_in_other_modules(fixtures: Path) -> None:
    """Relative and absolute imports inside the package are followed, transitively"""

    analysis = PythonAdapter().analyze(fixtures / "python_helper_call")
    run = first(tool(analysis, "run"), Capability.PROCESS_EXEC)
    assert chain(run) == ["run_command", "_execute"]
    assert run.file == "notes_server/runner.py"
    disk = first(tool(analysis, "disk"), Capability.PROCESS_EXEC)
    assert chain(disk) == ["disk_usage"]
    assert analysis.findings == []


def test_call_cycle_terminates(tmp_path: Path) -> None:
    """a calls b and b calls a: the walk stops and the finding is reported once"""

    write(
        tmp_path,
        "server.py",
        '''import os
from fastmcp import FastMCP

mcp = FastMCP("x")


def a(n: int) -> None:
    b(n)


def b(n: int) -> None:
    os.remove("x")
    a(n)


@mcp.tool
def loop() -> None:
    """Loop forever"""
    a(1)
''',
    )
    loop = tool(PythonAdapter().analyze(tmp_path), "loop")
    assert [chain(finding) for finding in loop.findings] == [["a", "b"]]


def test_depth_limit(tmp_path: Path) -> None:
    """Calls deeper than the configured limit are not followed"""

    write(
        tmp_path,
        "server.py",
        '''import os
from fastmcp import FastMCP

mcp = FastMCP("x")


def one() -> None:
    two()


def two() -> None:
    os.remove("x")


@mcp.tool
def deep() -> None:
    """Go deep"""
    one()
''',
    )
    assert tool(PythonAdapter(Limits(max_call_depth=2)).analyze(tmp_path), "deep").findings
    shallow = PythonAdapter(Limits(max_call_depth=1)).analyze(tmp_path)
    assert tool(shallow, "deep").findings == []
    assert [finding.function for finding in shallow.findings] == ["two"]


def test_self_and_this_methods(tmp_path: Path) -> None:
    """self.x() in Python and this.x() in JavaScript reach methods of the same class"""

    write(
        tmp_path,
        "server.py",
        '''import shutil
from fastmcp import FastMCP

mcp = FastMCP("x")


class Cleaner:
    def clean(self) -> None:
        self._wipe()

    def _wipe(self) -> None:
        shutil.rmtree("/tmp/x")


@mcp.tool
def clean() -> None:
    """Clean"""
    Cleaner.clean(Cleaner())
''',
    )
    python_tool = tool(PythonAdapter().analyze(tmp_path), "clean")
    assert chain(first(python_tool, Capability.FS_WRITE)) == ["Cleaner.clean", "Cleaner._wipe"]
    javascript_dir = tmp_path / "js"
    write(
        javascript_dir,
        "index.js",
        '''import { execSync } from "child_process";

class Runner {
  run(command) {
    return this.exec(command);
  }

  exec(command) {
    return execSync(command);
  }
}

const runner = new Runner();
server.tool("run", "Run", async ({ command }) => ({ content: [{ type: "text", text: Runner.prototype.run.call(runner, command) }] }));
server.tool("direct", "Direct", async () => new Runner().exec("ls"));
''',
    )
    analysis = JavaScriptAdapter().analyze(javascript_dir)
    assert [finding.function for finding in analysis.findings] == ["exec"]


def test_enclosing_function_skips_anonymous_callbacks(tmp_path: Path) -> None:
    """A finding inside an anonymous callback names the enclosing named function or variable"""

    write(
        tmp_path,
        "index.js",
        '''import { createReadStream } from "fs";

async function readAsBase64(path) {
  return new Promise((resolve, reject) => {
    const stream = createReadStream(path);
    stream.on("end", () => resolve(""));
  });
}

const handler = async () => {
  [1, 2].map((value) => createReadStream(String(value)));
};
''',
    )
    analysis = JavaScriptAdapter().analyze(tmp_path)
    assert [finding.function for finding in analysis.findings] == ["readAsBase64", "handler"]


def test_report_shows_direct_and_via(fixtures: Path) -> None:
    """The CLI says how each capability is reached"""

    text = render(analyze_directory(fixtures / "js_helper_call"), Translator("en"))
    assert "fs_write (writes or deletes files): via saveNote (lib.js:4)" in text
    text = render(analyze_directory(fixtures / "js_handler_ref"), Translator("fr"))
    assert "fs_read (lit des fichiers) : directement (src/index.ts:9)" in text
