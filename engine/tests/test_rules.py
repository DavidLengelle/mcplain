"""Tests for the rule cards and for the fixtures of every rule: positive, near miss and known false positive"""

import json
import re
from pathlib import Path

import pytest

from mcplain.analyze import analyze_directory
from mcplain.models import AlertKind, AnalysisResult, Reputation, VerdictColor
from mcplain.rules.base import TEXT_FIELDS
from mcplain.verdict import DEFAULT_REGISTRY

LOCALES = Path(__file__).parents[1] / "src" / "mcplain" / "locales"
CASES: dict[str, bool] = {"positive": True, "near_miss": False, "false_positive": True}
REPUTATION_FILE = "reputation.json"
IDENTIFIER_PATTERN = re.compile(r"^[RO]\d{2}$")
SLUG_PATTERN = re.compile(r"^[a-z]+(?:-[a-z]+)*$")
REVIEWED_SOURCES = Path(__file__).parent / "data" / "rule_sources.json"
RULES = DEFAULT_REGISTRY.rules()


def catalog(language: str) -> dict[str, str]:
    """Load one locale file"""

    return json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))


def analyze_fixture(folder: Path) -> AnalysisResult:
    """Analyze a rule fixture, with the OSV reputation it ships as data when there is one"""

    reputation = None
    if (folder / REPUTATION_FILE).is_file():
        reputation = Reputation.model_validate_json((folder / REPUTATION_FILE).read_text(encoding="utf-8"))
    return analyze_directory(folder, reputation=reputation)


@pytest.mark.parametrize("rule", RULES, ids=[rule.identifier for rule in RULES])
def test_rule_card_is_complete(rule: object) -> None:
    """Every rule has an identifier, a slug, a color, a kind, sources and texts in English and French"""

    assert IDENTIFIER_PATTERN.match(rule.identifier)
    assert SLUG_PATTERN.match(rule.slug)
    assert rule.color in (VerdictColor.RED, VerdictColor.ORANGE)
    assert rule.identifier[0] == {VerdictColor.RED: "R", VerdictColor.ORANGE: "O"}[rule.color]
    assert rule.kind in AlertKind
    assert rule.sources
    for source in rule.sources:
        assert source.name
        assert source.url.startswith("https://")
    for language in ("en", "fr"):
        texts = catalog(language)
        for field in TEXT_FIELDS:
            assert texts.get(rule.text_key(field), "").strip(), (language, rule.text_key(field))


def test_rules_have_unique_identifiers_and_slugs() -> None:
    """No two rules share an identifier or a slug"""

    assert len({rule.identifier for rule in RULES}) == len(RULES)
    assert len({rule.slug for rule in RULES}) == len(RULES)


@pytest.mark.parametrize(
    ("identifier", "case"),
    [(rule.identifier, case) for rule in RULES for case in CASES],
)
def test_rule_fixture(fixtures: Path, identifier: str, case: str) -> None:
    """A positive fixture fires the rule, a near miss does not, a known false positive still does"""

    folder = fixtures / "rules" / identifier / case
    assert folder.is_dir(), folder
    result = analyze_fixture(folder)
    fired = [alert for alert in result.verdict.alerts if alert.rule == identifier]
    assert bool(fired) is CASES[case], [(alert.rule, alert.detail) for alert in result.verdict.alerts]


def test_every_source_url_is_in_the_reviewed_list() -> None:
    """The sources quoted by the rules are exactly the reviewed links recorded in the repository, all in https"""

    recorded = json.loads(REVIEWED_SOURCES.read_text(encoding="utf-8"))
    urls = sorted({source.url for rule in RULES for source in rule.sources})
    assert urls == recorded["urls"]
    assert all(url.startswith("https://") for url in urls)


@pytest.mark.parametrize("rule", RULES, ids=[rule.identifier for rule in RULES])
def test_orange_rules_are_powers_to_know(rule: object) -> None:
    """Every orange rule is a power to be aware of; no red rule is"""

    assert (rule.kind is AlertKind.POWER_TO_KNOW) is (rule.color is VerdictColor.ORANGE)


def test_closed_world_tool_that_only_reads_the_network(fixtures: Path) -> None:
    """A tool that says openWorldHint false and only makes a GET request still fires O04"""

    result = analyze_fixture(fixtures / "rules" / "O04" / "closed_world_get")
    [tool] = result.servers[0].tools
    [finding] = tool.findings
    assert finding.sends is False
    fired = [alert for alert in result.verdict.alerts if alert.rule == "O04"]
    assert [(alert.tool, alert.detail) for alert in fired] == [("status", "openWorldHint: network")]


def test_open_network_cites_the_most_direct_request_first(fixtures: Path) -> None:
    """The request that receives the AI value as is comes before the robots.txt request built from it"""

    result = analyze_fixture(fixtures / "rules" / "O01" / "robots_check_first")
    fired = [alert for alert in result.verdict.alerts if alert.rule == "O01"]
    assert fired
    assert fired[0].function == "fetch_url"
    assert [step.function for step in fired[0].steps] == ["fetch_url"]
    assert [alert.function for alert in fired[1:]] in ([], ["check_robots"])
