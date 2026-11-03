"""Tests for the install rules: O10 against R08 for MCP client configurations, O11 against R10 at install time"""

import json
import shutil
from pathlib import Path

from mcplain.analyze import analyze_directory
from mcplain.lamps import LampId, LampState
from mcplain.models import AnalysisResult


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
