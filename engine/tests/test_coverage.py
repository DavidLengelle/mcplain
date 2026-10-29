"""Tests for the partial gray: what was checked in a server read only in part, and what was not"""

from pathlib import Path

import pytest

from mcplain.analyze import analyze_directory
from mcplain.cli import render
from mcplain.config import Limits
from mcplain.i18n import Translator, load_catalog
from mcplain.models import (
    AnalysisStatus,
    CoverageItem,
    CoverageKind,
    GrayCase,
    TrackingGap,
    VerdictColor,
)
from mcplain.verdict import COMPILED_REASON, DYNAMIC_DESCRIPTION_REASON, PARSE_ERROR_REASON, READING_CASES

PYPROJECT = '[project]\nname = "x"\nversion = "1"\ndependencies = ["mcp>=2"]\n'
HEADER = 'import subprocess\n\nfrom mcp.server import MCPServer\n\nmcp = MCPServer("x")\n'


def server(tmp_path: Path, body: str) -> Path:
    """Write a one-file Python server and return its folder"""

    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "server.py").write_text(HEADER + body, encoding="utf-8")
    return tmp_path


TRACKING = '''

class Index:
    def search(self, text):
        return text


def build(index):
    @mcp.tool()
    def find(text: str) -> str:
        """Find text"""
        return index.search(text)

    @mcp.tool()
    def count(text: str) -> int:
        """Count words"""
        return len(text.split())
'''


def test_a_server_read_in_part_says_what_was_checked_and_what_was_not(tmp_path: Path) -> None:
    """One tool followed out of two, every file read, and the call not followed with its place and its line"""

    result = analyze_directory(server(tmp_path, TRACKING))
    assert result.verdict.gray_case is GrayCase.INCOMPLETE_TRACKING
    coverage = result.verdict.coverage
    assert coverage is not None
    assert (coverage.tools_total, coverage.tools_followed) == (2, 1)
    assert (coverage.files_total, coverage.files_read) == (1, 1)
    item = coverage.not_checked[0]
    assert (item.kind, item.reason, item.name, item.file) == (
        CoverageKind.CALL,
        TrackingGap.UNKNOWN_TYPE.value,
        "find",
        "server.py",
    )
    assert item.snippet == "return index.search(text)"
    assert coverage.not_checked_count == 1


def test_network_not_followed_is_listed_with_its_import(fixtures: Path) -> None:
    """The library and the place of its import"""

    coverage = analyze_directory(fixtures / "python_network_elsewhere").verdict.coverage
    assert coverage is not None
    assert coverage.not_checked == [
        CoverageItem(kind=CoverageKind.NETWORK, reason="network_unresolved", name="httpx", file="clients.py", line=1)
    ]


def test_dynamic_descriptions_and_files_not_read_are_listed(tmp_path: Path) -> None:
    """A description built at startup, a file too large and a file with a syntax error"""

    body = '''

DESCRIPTION = "Echo" + str(len("x"))


@mcp.tool(description=DESCRIPTION.upper())
def echo(text: str) -> str:
    return text
'''
    folder = server(tmp_path, body)
    (folder / "big.py").write_text("x = 1\n" * 400, encoding="utf-8")
    (folder / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    coverage = analyze_directory(folder, limits=Limits(max_source_file_bytes=1000)).verdict.coverage
    assert coverage is not None
    kinds = {(item.kind, item.reason, item.file) for item in coverage.not_checked}
    assert (CoverageKind.DESCRIPTION, DYNAMIC_DESCRIPTION_REASON, "server.py") in kinds
    assert (CoverageKind.FILE, "too_large", "big.py") in kinds
    assert (CoverageKind.FILE, PARSE_ERROR_REASON, "broken.py") in kinds
    assert coverage.files_total == 3
    assert coverage.files_read == 1


def test_no_tool_found_is_listed(tmp_path: Path) -> None:
    """A server where no tool was recognized"""

    coverage = analyze_directory(server(tmp_path, "\n\ndef helper():\n    return 1\n")).verdict.coverage
    assert coverage is not None
    assert coverage.tools_total == 0
    assert coverage.not_checked == [CoverageItem(kind=CoverageKind.TOOLS, reason="no_tools_found")]


def test_the_list_is_cut_but_the_count_is_kept(tmp_path: Path) -> None:
    """More places than the limit: the list stops, the count says how many there were"""

    calls = "\n".join(f"        index.search(text + '{number}')" for number in range(40))
    body = f'''

class Index:
    def search(self, text):
        return text


def build(index):
    @mcp.tool()
    def find(text: str) -> str:
        """Find text"""
{calls}
        return text
'''
    coverage = analyze_directory(server(tmp_path, body)).verdict.coverage
    assert coverage is not None
    assert len(coverage.not_checked) == Limits().max_gap_places
    assert coverage.not_checked_count == Limits().max_gap_places


@pytest.mark.parametrize("fixture", ["python_fastmcp_clean", "official_fetch_like", "postmark_like", "go_server"])
def test_green_orange_red_and_other_grays_have_no_coverage(fixtures: Path, fixture: str) -> None:
    """Only a gray for a reading in part says what was checked"""

    result = analyze_directory(fixtures / fixture)
    assert result.verdict.coverage is None
    if result.verdict.color is VerdictColor.GRAY:
        assert result.verdict.gray_case not in READING_CASES
        assert result.status is not AnalysisStatus.OK


@pytest.mark.parametrize("language", ["en", "fr"])
def test_every_kind_and_reason_has_a_text(language: str) -> None:
    """The site and the command line need a text for each kind and each reason"""

    keys = set(load_catalog(language))
    reasons = [gap.value for gap in TrackingGap]
    reasons += [DYNAMIC_DESCRIPTION_REASON, PARSE_ERROR_REASON, COMPILED_REASON, "too_large"]
    reasons += ["network_unresolved", "no_tools_found"]
    expected = [f"coverage.kind.{kind.value}" for kind in CoverageKind]
    expected += [f"coverage.reason.{reason}" for reason in reasons]
    expected += ["coverage.checked", "coverage.nothing_found", "coverage.not_checked", "coverage.more"]
    assert [key for key in expected if key not in keys] == []


def test_the_command_line_shows_the_coverage(fixtures: Path) -> None:
    """Checked first, then what was not, then the gray sentence that stays"""

    text = render(analyze_directory(fixtures / "python_network_elsewhere"), Translator("en"))
    assert "Tools fully followed: 1 of 1. Files read: 2 of 2. Nothing suspicious in what was read." in text
    assert "Not checked:" in text
    assert "- Network library httpx clients.py:1: MCPlain did not see where it is used" in text
    assert "This does not mean this MCP is safe" in text
