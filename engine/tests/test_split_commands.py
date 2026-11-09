"""A command line split into a list keeps its label: O02 when the AI names the program, no R09 without a shell"""

from pathlib import Path

import pytest

from mcplain.analyze import analyze_directory, not_checked

PYTHON_SERVER = '''import os
import shlex
import subprocess
from shlex import split as cut

from fastmcp import FastMCP


def launch(words):
    return subprocess.run(words)


def build():
    mcp = FastMCP("x")

    @mcp.tool()
    def act(command: str) -> str:
        """Act"""
        {body}
        return ""

    return mcp
'''
JAVASCRIPT_SERVER = '''import {{ exec, execFile, spawn, spawnSync }} from "child_process";
import {{ McpServer }} from "@modelcontextprotocol/sdk/server/mcp.js";

const server = new McpServer({{ name: "x", version: "1.0.0" }});

server.tool("act", "Act", {{ command: {{ type: "string" }} }}, async ({{ command }}) => {{
  {body}
  return {{ content: [] }};
}});
'''


def rules_of(folder: Path) -> set[str]:
    """Analyze a folder and return the rules of its verdict"""

    result = analyze_directory(folder, reputation=not_checked())
    return {alert.rule for alert in result.verdict.alerts}


def python_rules(folder: Path, body: str) -> set[str]:
    """Analyze one Python tool with the given body"""

    (folder / "server.py").write_text(PYTHON_SERVER.replace("{body}", body), encoding="utf-8")
    return rules_of(folder)


def javascript_rules(folder: Path, body: str) -> set[str]:
    """Analyze one TypeScript tool with the given body"""

    (folder / "package.json").write_text('{"name": "x", "version": "1.0.0", "main": "index.js"}', encoding="utf-8")
    (folder / "index.js").write_text(JAVASCRIPT_SERVER.format(body=body), encoding="utf-8")
    return rules_of(folder)


@pytest.mark.parametrize(
    "body",
    [
        "subprocess.run(shlex.split(command))",
        "subprocess.run(cut(command))",
        "subprocess.run(shlex.split(s=command))",
        "subprocess.run(command.split())",
        "subprocess.run(command.split(' '))",
        "words = shlex.split(command); subprocess.run(words)",
        "words = shlex.split(command); subprocess.run([words[0], 'x'])",
        "words = command.split(); subprocess.run([words[0], 'x'])",
        "subprocess.Popen(shlex.split(command))",
        "launch(shlex.split(command))",
        "subprocess.run(shlex.split(f'{command} --verbose'))",
    ],
)
def test_python_split_command_gives_o02_without_r09(tmp_path: Path, body: str) -> None:
    """The AI names the program of a split command, and no shell reads it"""

    rules = python_rules(tmp_path, body)
    assert "O02" in rules and "O08" in rules
    assert "R09" not in rules


@pytest.mark.parametrize(
    "body",
    [
        'subprocess.run(shlex.split(f"pytest {command}"))',
        'subprocess.run(shlex.split("pytest " + command))',
        'subprocess.run(shlex.split("pytest %s" % command))',
        'subprocess.run(shlex.split("pytest {}".format(command)))',
        'subprocess.run(f"pytest {command}".split())',
        'line = f"pytest {command}"; subprocess.run(shlex.split(line))',
        'words = shlex.split(f"pytest -q {command}"); subprocess.run([words[0], words[1]])',
        'subprocess.run(shlex.split("pytest " + command + " -q"))',
        'subprocess.run(shlex.split(f"/usr/bin/pytest {command}"))',
    ],
)
def test_python_fixed_program_gives_o08_without_o02(tmp_path: Path, body: str) -> None:
    """A word written in the code then a space fixes the program: the tool only runs commands"""

    rules = python_rules(tmp_path, body)
    assert "O08" in rules
    assert "O02" not in rules and "R09" not in rules


@pytest.mark.parametrize(
    "body",
    [
        'subprocess.run(shlex.split(f"py{command} -q"))',
        "subprocess.run(shlex.split(f\"'py {command}' -q\"))",
        'subprocess.run(shlex.split(f"{command} pytest {command}"))',
        'subprocess.run(shlex.split(" " + command))',
    ],
)
def test_python_program_not_fixed_keeps_o02(tmp_path: Path, body: str) -> None:
    """Without a whole first word written in the code, the AI can still change the program"""

    assert "O02" in python_rules(tmp_path, body)


@pytest.mark.parametrize(
    ("body", "rule"),
    [
        ('subprocess.run(f"pytest {command}", shell=True)', "R09"),
        ('os.system(" ".join(shlex.split(f"pytest {command}")))', "R09"),
        ("subprocess.run(command, shell=True)", "O02"),
        ("subprocess.run(shlex.split(command), shell=True)", "O02"),
        ('subprocess.run(shlex.split(f"pytest {command}"), shell=True)', "R09"),
    ],
)
def test_python_shell_behaves_as_before(tmp_path: Path, body: str, rule: str) -> None:
    """With a shell, a pasted value is R09 and a whole command is O02, split or not"""

    assert rule in python_rules(tmp_path, body)


def test_python_list_argument_is_not_the_program(tmp_path: Path) -> None:
    """Split words given after a program written in the code are arguments"""

    rules = python_rules(tmp_path, 'subprocess.run(["git", *shlex.split(command)])')
    assert "O02" not in rules and "R09" not in rules


def test_python_plain_variable_list_stays_arguments(tmp_path: Path) -> None:
    """Without a split, a list held in a variable keeps its old reading"""

    assert "O02" not in python_rules(tmp_path, 'words = ["git", command]; subprocess.run(words)')


@pytest.mark.parametrize(
    "body",
    [
        'const words = command.split(" "); spawn(words[0], words.slice(1));',
        'const words = command.split(" "); spawnSync(words[0], []);',
        'const [program] = command.split(" "); execFile(program, []);',
        'spawn(command.split(" ")[0]);',
    ],
)
def test_javascript_split_command_gives_o02_without_r09(tmp_path: Path, body: str) -> None:
    """String.prototype.split keeps the label, on the whole list and on one element"""

    rules = javascript_rules(tmp_path, body)
    assert "O02" in rules and "O08" in rules
    assert "R09" not in rules


@pytest.mark.parametrize(
    "body",
    [
        'const words = `pytest ${command}`.split(" "); spawn(words[0], words.slice(1));',
        'const words = ("pytest " + command).split(" "); spawn(words[0], words.slice(1));',
        'const line = `pytest -q ${command}`; const words = line.split(" "); execFile(words[0], words.slice(1));',
    ],
)
def test_javascript_fixed_program_gives_o08_without_o02(tmp_path: Path, body: str) -> None:
    """A template or a concatenation that starts with a word and a space fixes the program"""

    rules = javascript_rules(tmp_path, body)
    assert "O08" in rules
    assert "O02" not in rules and "R09" not in rules


@pytest.mark.parametrize(
    "body",
    [
        'const words = `py${command} -q`.split(" "); spawn(words[0], words.slice(1));',
        'const words = `"py ${command}" -q`.split(" "); spawn(words[0], words.slice(1));',
    ],
)
def test_javascript_program_not_fixed_keeps_o02(tmp_path: Path, body: str) -> None:
    """Without a whole first word written in the code, the AI can still change the program"""

    assert "O02" in javascript_rules(tmp_path, body)


@pytest.mark.parametrize(
    ("body", "rule"),
    [
        ("exec(`pytest ${command}`);", "R09"),
        ("exec(command);", "O02"),
        ('exec(command.split(" ")[0]);', "O02"),
        ('exec(`pytest ${command}`.split(" ").join(" "));', "R09"),
    ],
)
def test_javascript_shell_behaves_as_before(tmp_path: Path, body: str, rule: str) -> None:
    """With a shell, a pasted value is R09 and a whole command is O02, split or not"""

    assert rule in javascript_rules(tmp_path, body)
