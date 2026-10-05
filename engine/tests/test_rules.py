"""Tests for the rule cards and for the fixtures of every rule: positive, near miss and known false positive"""

import json
import re
from pathlib import Path

import httpx
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
BROWSER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
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


@pytest.mark.network
def test_every_source_url_answers() -> None:
    """Each source quoted by a rule answers without an HTTP error"""

    urls = sorted({source.url for rule in RULES for source in rule.sources})
    failures = []
    with httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": BROWSER_AGENT}) as client:
        for url in urls:
            try:
                status = client.get(url).status_code
            except httpx.HTTPError as error:
                failures.append((url, type(error).__name__))
                continue
            if status >= 400 and status != 429:
                failures.append((url, str(status)))
    assert failures == []


@pytest.mark.parametrize("rule", RULES, ids=[rule.identifier for rule in RULES])
def test_orange_rules_are_powers_to_know(rule: object) -> None:
    """Every orange rule is a power to be aware of; no red rule is"""

    assert (rule.kind is AlertKind.POWER_TO_KNOW) is (rule.color is VerdictColor.ORANGE)

