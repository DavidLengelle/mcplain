"""End-to-end tests of the offline analysis step on the fixture servers"""

from pathlib import Path

import pytest

from mcplain.analyze import analyze_directory
from mcplain.models import AnalysisStatus, VerdictColor


@pytest.mark.parametrize(
    ("folder", "status", "color"),
    [
        ("python_fastmcp_clean", AnalysisStatus.OK, VerdictColor.GREEN),
        ("python_fastmcp_poisoned", AnalysisStatus.OK, VerdictColor.RED),
        ("python_lowlevel", AnalysisStatus.OK, VerdictColor.ORANGE),
        ("python_alias", AnalysisStatus.OK, VerdictColor.ORANGE),
        ("python_env", AnalysisStatus.OK, VerdictColor.ORANGE),
        ("python_syntax_error", AnalysisStatus.OK, VerdictColor.GRAY),
        ("python_tests_subprocess", AnalysisStatus.OK, VerdictColor.GREEN),
        ("ts_registertool", AnalysisStatus.OK, VerdictColor.ORANGE),
        ("js_lowlevel", AnalysisStatus.OK, VerdictColor.ORANGE),
        ("monorepo", AnalysisStatus.MULTIPLE_SERVERS, VerdictColor.GRAY),
        ("go_server", AnalysisStatus.UNSUPPORTED_LANGUAGE, VerdictColor.GRAY),
        ("awesome_list", AnalysisStatus.NOT_A_SERVER, VerdictColor.GRAY),
        ("npm_compiled", AnalysisStatus.COMPILED, VerdictColor.GRAY),
    ],
)
def test_fixture_outcomes(fixtures: Path, folder: str, status: AnalysisStatus, color: VerdictColor) -> None:
    """Every fixture gets the expected status and verdict"""

    result = analyze_directory(fixtures / folder)
    assert result.status is status
    assert result.verdict.color is color


def test_poisoned_verdict_reasons(fixtures: Path) -> None:
    """The poisoned server asks for silence, asks for the SSH key and sends it: red"""

    verdict = analyze_directory(fixtures / "python_fastmcp_poisoned").verdict
    rules = {alert.rule for alert in verdict.alerts}
    assert {"R02", "R03", "R04"} <= rules
    assert ("O08", "sensitive_path") in [(alert.rule, alert.detail) for alert in verdict.alerts]
    assert "O07" in rules


def test_postmark_like_is_red_by_hidden_copy(fixtures: Path) -> None:
    """An e-mail server with a hard-coded Bcc to an outside address is red because of R05"""

    result = analyze_directory(fixtures / "postmark_like")
    assert result.status is AnalysisStatus.OK
    assert result.verdict.color is VerdictColor.RED
    assert "R05" in {alert.rule for alert in result.verdict.alerts}


def test_env_verdict_comes_from_the_secret_only(fixtures: Path) -> None:
    """PORT alone would be green: only API_KEY makes the server orange"""

    alerts = analyze_directory(fixtures / "python_env").verdict.alerts
    assert [(alert.rule, alert.detail) for alert in alerts] == [("O08", "env_read_secret")]


def test_tests_folder_is_reported_but_not_counted(fixtures: Path) -> None:
    """The subprocess call in tests/ is in the report and the verdict stays green"""

    result = analyze_directory(fixtures / "python_tests_subprocess")
    assert result.verdict.reasons == ["no_alert"]
    assert result.servers[0].findings[0].file == "tests/check_server.py"


def test_select_inside_monorepo(fixtures: Path) -> None:
    """--select picks one server of a monorepo"""

    result = analyze_directory(fixtures / "monorepo", select="src/a")
    assert result.status is AnalysisStatus.OK
    assert result.servers[0].path == "src/a"
    assert [tool.name for tool in result.servers[0].tools] == ["hello"]


def test_monorepo_lists_candidates(fixtures: Path) -> None:
    """multiple_servers carries the list of servers to choose from"""

    result = analyze_directory(fixtures / "monorepo")
    assert [candidate.path for candidate in result.available_servers] == ["src/a", "src/b"]


def test_compiled_files_are_listed(fixtures: Path) -> None:
    """The compiled result names the binary files"""

    assert analyze_directory(fixtures / "npm_compiled").compiled_files == ["bin/compiled-server"]


def test_missing_selection_is_an_error(fixtures: Path) -> None:
    """Selecting a folder that does not exist ends in an error result"""

    result = analyze_directory(fixtures / "monorepo", select="src/zzz")
    assert result.status is AnalysisStatus.ERROR
    assert result.error is not None
    assert result.error.code == "analyze.subdir_not_found"


def test_not_a_directory(tmp_path: Path) -> None:
    """A path that is not a folder ends in an error result"""

    result = analyze_directory(tmp_path / "missing")
    assert result.status is AnalysisStatus.ERROR


def test_analyzed_code_is_never_executed(tmp_path: Path) -> None:
    """Code that would create a file if it ran leaves no trace after analysis"""

    marker = tmp_path / "pwned"
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\ndependencies = ["mcp"]\n', encoding="utf-8")
    (tmp_path / "server.py").write_text(f"open({str(marker)!r}, 'w').write('x')\n", encoding="utf-8")
    (tmp_path / "setup.py").write_text(f"open({str(marker)!r}, 'w').write('x')\n", encoding="utf-8")
    result = analyze_directory(tmp_path)
    assert result.status is AnalysisStatus.OK
    assert not marker.exists()


def test_result_is_json_serializable(fixtures: Path) -> None:
    """The result round-trips through JSON"""

    result = analyze_directory(fixtures / "python_fastmcp_poisoned")
    restored = type(result).model_validate_json(result.model_dump_json())
    assert restored == result
