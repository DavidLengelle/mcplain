"""Tests for the install rules: O10 against R08 for MCP client configurations, O11 against R10 at install time"""

import json
import shutil
from pathlib import Path

from mcplain.analyze import analyze_directory
from mcplain.lamps import LampId, LampState
from mcplain.models import AnalysisResult
from mcplain.rules.red import shortened


def rules(result: AnalysisResult) -> list[str]:
    """Return the rules of the alerts of a verdict"""

    return [alert.rule for alert in result.verdict.alerts]


def lamp(result: AnalysisResult, lamp_id: LampId) -> LampState:
    """Return the state of one lamp of the first server"""

    return next(item.state for item in result.servers[0].lamps if item.id is lamp_id)


def copy_fixture(fixtures: Path, tmp_path: Path, rule: str, case: str) -> Path:
    """Copy a rule fixture into a temporary folder to change it"""

    target = tmp_path / case
    shutil.copytree(fixtures / "rules" / rule / case, target)
    return target


def test_an_install_command_that_adds_the_server_to_claude_is_o10(fixtures: Path) -> None:
    """The setup bin, not the server, writes claude_desktop_config.json: orange O10 names Claude Desktop, no R08"""

    result = analyze_directory(fixtures / "rules" / "O10" / "positive")
    [alert] = [alert for alert in result.verdict.alerts if alert.rule == "O10"]
    assert alert.params == {"client": "Claude Desktop"}
    assert "R08" not in rules(result)
    assert result.servers[0].install_commands == ["setup.js"]
    assert lamp(result, LampId.FILES_WRITE) is LampState.ON


def test_a_tool_of_the_server_that_writes_a_client_config_stays_red(fixtures: Path) -> None:
    """engine/tests/fixtures/rules/R08/false_positive: a tool of the server writes the config, R08 stays red"""

    result = analyze_directory(fixtures / "rules" / "R08" / "false_positive")
    assert "R08" in rules(result)
    assert "O10" not in rules(result)


def test_a_client_config_written_by_npm_install_stays_red(fixtures: Path, tmp_path: Path) -> None:
    """The same setup.js run by a postinstall script is not a command the user runs: R08"""

    folder = copy_fixture(fixtures, tmp_path, "O10", "positive")
    manifest = json.loads((folder / "package.json").read_text())
    manifest["scripts"] = {"postinstall": "node setup.js"}
    (folder / "package.json").write_text(json.dumps(manifest))
    setup = folder / "setup.js"
    setup.write_text(setup.read_text() + "\naddToClaude();\n")
    result = analyze_directory(folder)
    assert "R08" in rules(result)
    assert "O10" not in rules(result)


def test_the_server_bin_that_writes_a_client_config_stays_red(fixtures: Path, tmp_path: Path) -> None:
    """When the server's own bin writes claude_desktop_config.json, it is the server: R08"""

    folder = copy_fixture(fixtures, tmp_path, "O10", "positive")
    (folder / "index.js").write_text((folder / "index.js").read_text() + "\n" + (folder / "setup.js").read_text())
    (folder / "setup.js").unlink()
    result = analyze_directory(folder)
    assert "R08" in rules(result)
    assert "O10" not in rules(result)


def test_an_install_command_that_edits_a_shell_startup_file_stays_red(fixtures: Path, tmp_path: Path) -> None:
    """The setup command appends to .bashrc, a startup file and not an MCP client config: R08"""

    folder = copy_fixture(fixtures, tmp_path, "O10", "positive")
    (folder / "setup.js").write_text(
        'import fs from "fs";\nimport os from "os";\nimport path from "path";\n\n'
        "export function addToPath() {\n"
        '  fs.appendFileSync(path.join(os.homedir(), ".bashrc"), "export PATH=$PATH:$HOME/.notes/bin\\n");\n'
        "}\n"
    )
    result = analyze_directory(folder)
    assert "R08" in rules(result)
    assert "O10" not in rules(result)


def test_a_plain_request_at_install_time_is_o11(fixtures: Path) -> None:
    """engine/tests/fixtures/rules/O11/positive pings a fixed address with nothing in it: O11 names the domain"""

    result = analyze_directory(fixtures / "rules" / "O11" / "positive")
    [alert] = [alert for alert in result.verdict.alerts if alert.rule == "O11"]
    assert alert.params == {"domain": "telemetry.attacker.invalid"}
    assert "R10" not in rules(result)
    assert lamp(result, LampId.INTERNET) is LampState.ON


def test_an_install_request_that_carries_user_and_machine_names_stays_red(fixtures: Path) -> None:
    """engine/tests/fixtures/rules/R10/positive sends the user and machine names: R10"""

    result = analyze_directory(fixtures / "rules" / "R10" / "positive")
    assert "R10" in rules(result)
    assert "O11" not in rules(result)


def test_an_install_request_built_from_an_environment_variable_stays_red(fixtures: Path) -> None:
    """engine/tests/fixtures/rules/R10/false_positive takes its mirror from a variable: not proven, so red"""

    assert "R10" in rules(analyze_directory(fixtures / "rules" / "R10" / "false_positive"))


def test_a_red_install_request_names_the_written_domains_and_what_the_install_code_reads(fixtures: Path) -> None:
    """R10 says, from the engine findings only, the domains written in the file and what the install code reads"""

    result = analyze_directory(fixtures / "rules" / "R10" / "false_positive")
    [alert] = [alert for alert in result.verdict.alerts if alert.rule == "R10"]
    assert alert.title == "rule.R10.request.plain_title"
    assert alert.params == {"domains": "downloads.example.invalid", "data": "NOTES_MIRROR"}


def test_a_red_install_request_without_reads_names_only_the_domains(fixtures: Path) -> None:
    """User and machine names are not findings of the engine: only the domain is named, nothing is invented"""

    result = analyze_directory(fixtures / "rules" / "R10" / "positive")
    [alert] = [alert for alert in result.verdict.alerts if alert.rule == "R10"]
    assert alert.title == "rule.R10.request_domains.plain_title"
    assert alert.params == {"domains": "telemetry.attacker.invalid"}


def test_a_long_list_of_install_reads_is_shortened() -> None:
    """Past the limit, the list keeps the first items and counts the others"""

    assert shortened(["A", "B", "C"], 2) == "A, B, +1"
    assert shortened(["A"], 2) == "A"


def install_package(tmp_path: Path, script: str, extra: dict[str, object] | None = None) -> Path:
    """Write a small server package whose postinstall runs download.js with the given text"""

    manifest: dict[str, object] = {
        "name": "notes-cli",
        "version": "2.1.0",
        "type": "module",
        "main": "index.js",
        "scripts": {"postinstall": "node download.js"},
        "dependencies": {"@modelcontextprotocol/sdk": "^1.0.0"},
    }
    manifest.update(extra or {})
    (tmp_path / "package.json").write_text(json.dumps(manifest))
    (tmp_path / "index.js").write_text(
        'import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";\n'
        "export function build() {\n  return new McpServer({ name: \"notes\", version: \"2.1.0\" });\n}\n"
    )
    (tmp_path / "download.js").write_text(script)
    return tmp_path


def test_a_program_downloaded_for_this_version_and_system_is_o11(tmp_path: Path) -> None:
    """The URL holds the package version, the platform, the architecture and the Node version: O11"""

    script = (
        'import https from "https";\nimport os from "os";\nimport pkg from "./package.json" with { type: "json" };\n'
        "const base = \"https://downloads.example.invalid\";\n"
        "const file = `notes-${pkg.version}-${process.platform}-${os.arch()}-node${process.versions.node}.tgz`;\n"
        "https.get(`${base}/${file}`);\n"
    )
    result = analyze_directory(install_package(tmp_path, script))
    assert [alert.params for alert in result.verdict.alerts if alert.rule == "O11"] == [
        {"domain": "downloads.example.invalid"}
    ]
    assert "R10" not in rules(result)


def test_the_version_read_with_require_is_plain(tmp_path: Path) -> None:
    """require("./package.json").version is the package version"""

    script = (
        'const https = require("https");\nconst version = require("./package.json").version;\n'
        'https.get("https://downloads.example.invalid/notes-" + version + ".tgz");\n'
    )
    result = analyze_directory(install_package(tmp_path, script, {"type": "commonjs"}))
    assert "O11" in rules(result)
    assert "R10" not in rules(result)


def test_a_curl_of_a_written_address_in_an_install_hook_is_o11(tmp_path: Path) -> None:
    """postinstall: curl -fsSL -o bin/notes https://downloads.example.invalid/notes.tgz downloads a fixed file"""

    command = "curl -fsSL -o bin/notes.tgz https://downloads.example.invalid/notes.tgz"
    folder = install_package(tmp_path, "", {"scripts": {"postinstall": command}})
    result = analyze_directory(folder)
    assert [alert.params for alert in result.verdict.alerts if alert.rule == "O11"] == [
        {"domain": "downloads.example.invalid"}
    ]
    assert "R10" not in rules(result)


SETUP_PY = '''import platform
import urllib.request

from setuptools import setup
from setuptools.command.install import install

VERSION = "2.1.0"


class FetchBinary(install):
    def run(self):
        url = f"https://downloads.example.invalid/notes-{VERSION}-{platform.system()}-{platform.machine()}.tgz"
        urllib.request.urlopen(url)
        install.run(self)


setup(name="notes-cli", version=VERSION, cmdclass={"install": FetchBinary})
'''


def test_a_python_setup_download_for_this_system_is_o11(tmp_path: Path) -> None:
    """setup.py fetches a file named with the version, the system and the machine: O11"""

    (tmp_path / "pyproject.toml").write_text('[project]\nname = "notes-cli"\nversion = "2.1.0"\ndependencies = ["mcp>=1"]\n')
    (tmp_path / "setup.py").write_text(SETUP_PY)
    (tmp_path / "server.py").write_text(
        'from mcp.server.fastmcp import FastMCP\n\nmcp = FastMCP("notes")\n\n\n@mcp.tool()\ndef count() -> str:\n'
        '    """Count the notes"""\n\n    return "0"\n'
    )
    result = analyze_directory(tmp_path)
    assert [alert.params for alert in result.verdict.alerts if alert.rule == "O11"] == [
        {"domain": "downloads.example.invalid"}
    ]
    assert "R10" not in rules(result)


def lit_lamps(result: AnalysisResult) -> set[LampId]:
    """Return the lamps of the first server that are on or red"""

    return {item.id for item in result.servers[0].lamps if item.state is not LampState.OFF}


def test_the_lamps_of_the_three_new_rules(fixtures: Path) -> None:
    """O09 lights no lamp, O10 lights the files lamp, O11 the Internet lamp; none of them is red"""

    o09 = analyze_directory(fixtures / "rules" / "O09" / "positive")
    o10 = analyze_directory(fixtures / "rules" / "O10" / "positive")
    o11 = analyze_directory(fixtures / "rules" / "O11" / "positive")
    assert lit_lamps(o09) == set()
    assert LampId.FILES_WRITE in lit_lamps(o10)
    assert LampId.INTERNET in lit_lamps(o11)
    for result in (o09, o10, o11):
        assert all(item.state is not LampState.DANGER for item in result.servers[0].lamps)
