"""Tests for require() of a JSON file: a file read when every possible path ends with .json written in the code"""

from pathlib import Path

import pytest

from mcplain.analyze import analyze_directory
from mcplain.capabilities import Capability
from mcplain.lamps import LampId, LampState
from mcplain.models import AnalysisResult

PACKAGE = '{"name": "version-reader", "version": "1.0.0", "type": "module", "dependencies": {"@modelcontextprotocol/sdk": "^1.30.0"}}'
HEADER = '''import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

const require = createRequire(import.meta.url);
const moduleDir = "/opt/version-reader";

'''
FOOTER = '''

const server = new McpServer({ name: "version-reader", version: readVersion() });
server.registerTool("version", { description: "Tell the version" }, async () => ({ content: [{ type: "text", text: readVersion() }] }));
'''
CANDIDATES = '''export function readVersion() {
  const candidates = [path.join(moduleDir, "package.json"), path.join(moduleDir, "..", "package.json")];
  for (const candidate of candidates) {
    try {
      return require(candidate).version;
    } catch {
      continue;
    }
  }
  return "0.0.0";
}'''


def analyze(tmp_path: Path, body: str) -> AnalysisResult:
    """Analyze a one-file server built around a readVersion function"""

    (tmp_path / "package.json").write_text(PACKAGE, encoding="utf-8")
    (tmp_path / "index.js").write_text(HEADER + body + FOOTER, encoding="utf-8")
    return analyze_directory(tmp_path)


def capabilities(result: AnalysisResult) -> dict[Capability, list[str | None]]:
    """Return the details of the findings of the server and of its tools, by capability"""

    server = result.servers[0]
    found: dict[Capability, set[str | None]] = {}
    for finding in server.findings + [item for tool in server.tools for item in tool.findings]:
        found.setdefault(finding.capability, set()).add(finding.detail)
    return {capability: sorted(details, key=str) for capability, details in found.items()}


def lamp(result: AnalysisResult, lamp_id: LampId) -> LampState:
    """Return the state of one lamp of the server"""

    return next(item.state for item in result.servers[0].lamps if item.id is lamp_id)


def test_two_literal_json_paths_are_a_file_read(tmp_path: Path) -> None:
    """require(candidate) over two paths that end with package.json: no O08, the files lamp instead of the commands lamp"""

    result = analyze(tmp_path, CANDIDATES)
    found = capabilities(result)
    assert Capability.DYNAMIC_CODE not in found
    assert found[Capability.FS_READ] == ["require(.json)"]
    assert "O08" not in [alert.rule for alert in result.verdict.alerts]
    assert lamp(result, LampId.FILES_READ) is LampState.ON
    assert lamp(result, LampId.COMMANDS) is LampState.OFF


@pytest.mark.parametrize(
    "body",
    [
        'export function readVersion(ext) {\n  return require("./config" + ext).version;\n}',
        'export function readVersion() {\n  return require(moduleDir + "/data.JSON").version;\n}',
        "export function readVersion(name) {\n  return require(`${moduleDir}/${name}`).version;\n}",
        CANDIDATES.replace("for (const candidate", "for (let candidate"),
        CANDIDATES.replace('path.join(moduleDir, "..", "package.json")', "process.argv[2]"),
        'export function readVersion(name) {\n  return require(path.join(moduleDir, name)).version;\n}',
    ],
    ids=["computed_extension", "upper_case_extension", "template_ends_with_a_value", "let_loop", "unknown_element", "joined_name"],
)
def test_a_path_not_fully_written_stays_dynamic_code(tmp_path: Path, body: str) -> None:
    """Node runs .JSON or any unknown extension as JavaScript: anything not surely .json keeps O08"""

    result = analyze(tmp_path, body)
    assert capabilities(result)[Capability.DYNAMIC_CODE] == ["require()"]
    assert "O08" in [alert.rule for alert in result.verdict.alerts]
    assert lamp(result, LampId.COMMANDS) is LampState.ON


def test_a_sensitive_json_path_keeps_the_sensitive_path_rules(tmp_path: Path) -> None:
    """A JSON read of a sensitive file is not dynamic code, but the sensitive path is still reported"""

    body = 'export function readVersion() {\n  return require(path.join(os.homedir(), ".docker/config.json")).auths;\n}'
    result = analyze(tmp_path, body)
    found = capabilities(result)
    assert Capability.DYNAMIC_CODE not in found
    assert found[Capability.FS_READ] == ["require(.json)"]
    assert Capability.SENSITIVE_PATH in found
    assert lamp(result, LampId.SECRETS) is LampState.ON
    assert "O08" in [alert.rule for alert in result.verdict.alerts]
