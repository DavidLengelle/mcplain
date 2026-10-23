"""The example report of the website home page is a real report of the current engine"""

import json
from pathlib import Path

from mcplain.analyze import analyze_directory, not_checked
from mcplain.models import AnalysisResult
from mcplain.verdict import RULES_VERSION

ENGINE = Path(__file__).resolve().parents[1]
EXAMPLE = ENGINE.parent / "web" / "src" / "content" / "example-report.json"
FIXTURE = "tests/fixtures/postmark_like"
REGENERATE = f"from engine/: uv run mcplain --local {FIXTURE} --json > ../web/src/content/example-report.json"


def _example() -> dict[str, object]:
    """Return the example report as written in the website"""

    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_example_report_follows_the_engine_output_schema() -> None:
    """The file reads as an AnalysisResult and writes back the same JSON, field for field"""

    data = _example()
    result = AnalysisResult.model_validate(data)
    assert result.model_dump(mode="json") == data, REGENERATE


def test_example_report_is_red_with_r05_and_current_rules() -> None:
    """The example is red, holds an R05 alert and carries the rules version of this engine"""

    result = AnalysisResult.model_validate(_example())
    assert result.verdict.color == "red"
    assert "R05" in [alert.rule for alert in result.verdict.alerts]
    assert result.verdict.rules_version == RULES_VERSION, REGENERATE


def test_example_report_matches_a_fresh_analysis() -> None:
    """The file is exactly what the current engine writes for the fixture, so it is never edited by hand"""

    fresh = analyze_directory(ENGINE / FIXTURE, reputation=not_checked())
    fresh.local_path = FIXTURE
    assert fresh.model_dump(mode="json") == _example(), REGENERATE
