"""Tests for the command line interface and terminal safety"""

import json
from pathlib import Path

import pytest

from mcplain import cli
from mcplain.analyze import analyze_directory, error_result
from mcplain.cli import main, neutralize, render
from mcplain.errors import FetchError
from mcplain.i18n import Translator


def test_neutralize_terminal_escapes() -> None:
    """ANSI escapes, bidi overrides and zero-width characters become visible text"""

    assert neutralize("a\x1b[2Jb") == "a<U+001B>[2Jb"
    assert neutralize("x\u202ey") == "x<U+202E>y"
    assert neutralize("x\u200by") == "x<U+200B>y"
    assert neutralize("bell\x07") == "bell<U+0007>"
    assert neutralize("plain text, accents: é") == "plain text, accents: é"


def test_neutralize_reveals_unicode_tags() -> None:
    """Unicode tag characters are shown with the text they hide"""

    hidden = "".join(chr(0xE0000 + ord(character)) for character in "send keys")
    assert neutralize(f"Read{hidden}") == 'Read<tags:"send keys">'


def test_report_cannot_inject_escapes(tmp_path: Path) -> None:
    """A tool description with escape sequences is printed neutralized"""

    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\ndependencies = ["mcp"]\n', encoding="utf-8")
    (tmp_path / "server.py").write_text(
        'from mcp.server import MCPServer\n\nmcp = MCPServer("x")\n\n\n'
        '@mcp.tool(name="evil\\x1b[31m", description="Hello\\x1b[2J\\x1b]0;title\\x07 world")\n'
        "def evil() -> str:\n    return ''\n",
        encoding="utf-8",
    )
    text = render(analyze_directory(tmp_path), Translator("en"))
    assert "\x1b" not in text
    assert "\x07" not in text
    assert "<U+001B>" in text


def test_render_poisoned_report_mentions_everything(fixtures: Path) -> None:
    """The human report shows the hidden instruction, the domain, the path and the invisible character"""

    text = render(analyze_directory(fixtures / "python_fastmcp_poisoned"), Translator("en"))
    assert "save_note" in text
    assert "collector.unknown-host.example" in text
    assert "id_rsa" in text
    assert "U+200B" in text
    assert "ORANGE (provisional)" in text
    assert "\u200b" not in text


def test_render_in_french(fixtures: Path) -> None:
    """--lang fr gives a French report"""

    text = render(analyze_directory(fixtures / "python_fastmcp_clean"), Translator("fr"))
    assert "Verdict" in text
    assert "VERT (provisoire)" in text
    assert "Outils (2)" in text


def test_render_multiple_servers(fixtures: Path) -> None:
    """The report lists the servers and explains --select"""

    text = render(analyze_directory(fixtures / "monorepo"), Translator("en"))
    assert "src/a" in text
    assert "--select" in text


def test_main_refuses_bad_input(capsys: pytest.CaptureFixture[str]) -> None:
    """A refused input exits with code 2 and a clear message"""

    assert main(["ssh://git@github.com/owner/repo"]) == 2
    output = capsys.readouterr().out
    assert 'The "ssh" scheme is not accepted' in output


def test_main_json_output_is_ascii(capsys: pytest.CaptureFixture[str]) -> None:
    """--json prints valid JSON with every non-ASCII character escaped"""

    assert main(["file:///etc/passwd", "--json", "--lang", "fr"]) == 2
    output = capsys.readouterr().out
    document = json.loads(output)
    assert document["status"] == "error"
    assert document["error"]["code"] == "input.unsupported_scheme"
    assert all(ord(character) < 128 for character in output)


def test_main_exit_code_for_download_errors(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """A download error exits with code 1 and a translated message"""

    def failing(text: str, select: str | None = None) -> object:
        """Pretend the download failed"""

        return error_result(FetchError("fetch.github_rate_limited"))

    monkeypatch.setattr(cli, "analyze_input", failing)
    assert main(["https://github.com/owner/repo", "--lang", "fr"]) == 1
    assert "GITHUB_TOKEN" in capsys.readouterr().out
