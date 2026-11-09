"""Damn Vulnerable MCP Server: each challenge is read by the engine, never run, and graded against engine/tests/data/dvmcp.toml"""

import os
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pytest

from mcplain import __version__
from mcplain.analyze import analyze_directory, not_checked
from mcplain.models import AnalysisResult, VerdictColor
from mcplain.verdict import RULES_VERSION

ENGINE = Path(__file__).resolve().parents[1]
REPOSITORY = ENGINE.parent
EXPECTED = ENGINE / "tests" / "data" / "dvmcp.toml"
CLONE = ENGINE / "tests" / "fixtures" / "external" / "dvmcp"
FETCH_SCRIPT = REPOSITORY / "scripts" / "fetch-dvmcp.sh"
REPORT = REPOSITORY / "bench" / "private" / "dvmcp.md"
REQUIRE_VARIABLE = "MCPLAIN_REQUIRE_DVMCP"
COLORS = {color.value for color in VerdictColor}
SCOPE_IN = "in"
SCOPE_OUT = "out"


class Grade(StrEnum):
    """Class that lists how a challenge is judged"""

    OK = "OK"
    ACCEPTABLE = "ACCEPTABLE"
    OUT_OF_SCOPE = "HORS PORTEE"
    FAIL = "ECHEC"


@dataclass
class Challenge:
    """Class that holds the expected answer of one challenge, read from dvmcp.toml"""

    id: int
    name: str
    folder: str
    color: list[str]
    accept: list[str]
    rules: list[str]
    scope: str
    reason: str = ""


@dataclass
class Judgement:
    """Class that holds the grade of one challenge and what the engine answered"""

    grade: Grade
    color: str
    rules: list[str]
    gray_case: str | None


def load_expected() -> dict:
    """Read the pinned commit and the expected answers"""

    return tomllib.loads(EXPECTED.read_text(encoding="utf-8"))


def load_challenges() -> list[Challenge]:
    """Return every challenge of dvmcp.toml"""

    return [Challenge(**entry) for entry in load_expected()["challenge"]]


def judge(challenge: Challenge, result: AnalysisResult) -> Judgement:
    """Grade an analysis: OK, ACCEPTABLE, out of scope or fail; green on an in-scope challenge is always a fail"""

    color = result.verdict.color.value
    rules = sorted({alert.rule for alert in result.verdict.alerts})
    gray_case = None
    if result.verdict.gray_case is not None:
        gray_case = result.verdict.gray_case.value
    grade = Grade.FAIL
    if challenge.scope == SCOPE_OUT:
        grade = Grade.OUT_OF_SCOPE
    elif color != VerdictColor.GREEN.value:
        has_rule = not challenge.rules or bool(set(challenge.rules) & set(rules))
        if color in challenge.color and (has_rule or color == VerdictColor.GRAY.value):
            grade = Grade.OK
        elif color in challenge.accept:
            grade = Grade.ACCEPTABLE
    return Judgement(grade=grade, color=color, rules=rules, gray_case=gray_case)


def clone_commit() -> str | None:
    """Read the commit of the clone from its files, without running anything; None when there is no clone"""

    head = CLONE / ".git" / "HEAD"
    if not head.is_file():
        return None
    return head.read_text(encoding="utf-8").strip()


def write_report(challenges: list[Challenge], judgements: dict[int, Judgement]) -> None:
    """Write the private report: expected and fired rules and the grades, never any code of the challenges"""

    lines = [
        "# DVMCP",
        "",
        f"Moteur {__version__}, règles version {RULES_VERSION}, commit {load_expected()['sha']}.",
        "Ce fichier ne sort jamais de cet ordinateur.",
        "",
        "| Défi | Nom | Portée | Couleur attendue | Règles attendues | Couleur | Règles | Cas gris | Classement |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for challenge in challenges:
        judgement = judgements[challenge.id]
        expected_colors = ", ".join(challenge.color) or "-"
        expected_rules = ", ".join(challenge.rules) or "-"
        fired = ", ".join(judgement.rules) or "-"
        gray_case = judgement.gray_case or "-"
        lines.append(
            f"| {challenge.id} | {challenge.name} | {challenge.scope} | {expected_colors} | {expected_rules} "
            f"| {judgement.color} | {fired} | {gray_case} | {judgement.grade.value} |"
        )
    to_review = [challenge.id for challenge in challenges if judgements[challenge.id].grade is Grade.ACCEPTABLE]
    if to_review:
        numbers = ", ".join(str(number) for number in to_review)
        lines += ["", f"Défis {numbers} : cas ACCEPTABLE, à revoir si des signalements montrent des pièges passés en orange."]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def judgements() -> dict[int, Judgement]:
    """Read every challenge once with the engine and write the private report; skip without a clone unless required"""

    commit = clone_commit()
    if commit is None:
        message = "DVMCP is not cloned: run scripts/fetch-dvmcp.sh to check the engine against it"
        if os.environ.get(REQUIRE_VARIABLE) == "1":
            pytest.fail(message, pytrace=False)
        pytest.skip(message)
    if commit != load_expected()["sha"]:
        pytest.fail("the DVMCP clone is not at the pinned commit: remove it and run scripts/fetch-dvmcp.sh", pytrace=False)
    challenges = load_challenges()
    results = {}
    for challenge in challenges:
        result = analyze_directory(CLONE / challenge.folder, reputation=not_checked())
        results[challenge.id] = judge(challenge, result)
    write_report(challenges, results)
    return results


@pytest.mark.parametrize("challenge", load_challenges(), ids=lambda challenge: f"challenge-{challenge.id}")
def test_challenge_is_not_a_failure(challenge: Challenge, judgements: dict[int, Judgement]) -> None:
    """Each challenge passes or fails, without any detail: the detail stays in the private report"""

    if judgements[challenge.id].grade is Grade.FAIL:
        pytest.fail(f"challenge {challenge.id} failed, details in bench/private/dvmcp.md", pytrace=False)


@pytest.mark.parametrize("identifier", [5, 10])
def test_challenges_decided_by_david_stay_acceptable_and_not_ok(identifier: int, judgements: dict[int, Judgement]) -> None:
    """Their answer stays red: an orange verdict is accepted with its written reason, never counted as OK"""

    challenge = next(item for item in load_challenges() if item.id == identifier)
    assert challenge.color == ["red"]
    assert "orange" in challenge.accept
    assert challenge.reason
    assert judgements[identifier].grade in {Grade.OK, Grade.ACCEPTABLE}
    if judgements[identifier].color == VerdictColor.ORANGE.value:
        assert judgements[identifier].grade is Grade.ACCEPTABLE


def test_expected_answers_are_well_formed() -> None:
    """Ten challenges, known colors, a scope, and green is never accepted for an in-scope challenge"""

    challenges = load_challenges()
    assert [challenge.id for challenge in challenges] == list(range(1, 11))
    for challenge in challenges:
        assert challenge.scope in {SCOPE_IN, SCOPE_OUT}
        assert set(challenge.accept) <= COLORS
        assert set(challenge.color) <= set(challenge.accept)
        if challenge.scope == SCOPE_IN:
            assert challenge.color
            assert VerdictColor.GREEN.value not in challenge.accept
        assert not challenge.folder.startswith("solutions")


def test_fetch_script_pins_the_same_commit_over_https() -> None:
    """The script clones the commit of dvmcp.toml, over HTTPS, and checks it"""

    text = FETCH_SCRIPT.read_text(encoding="utf-8")
    assert f'SHA="{load_expected()["sha"]}"' in text
    assert 'REPOSITORY="https://github.com/' in text
    assert "rev-parse HEAD" in text
    assert FETCH_SCRIPT.stat().st_mode & 0o111


def report_judge(scope: str, color: str, rules: list[str], answer: str, fired: list[str]) -> Grade:
    """Grade a made-up verdict with a made-up challenge"""

    challenge = Challenge(id=1, name="x", folder="x", color=[color], accept=[color, "gray"], rules=rules, scope=scope)
    alerts = [{"rule": rule, "color": answer, "kind": "power_to_know"} for rule in fired]
    verdict = {"color": answer, "alerts": alerts}
    if answer == "gray":
        verdict["gray_case"] = "no_tools_found"
    return judge(challenge, AnalysisResult.model_validate({"status": "ok", "verdict": verdict})).grade


def test_judge_grades() -> None:
    """OK needs the color and one expected rule, a color of accept is ACCEPTABLE, the rest is a fail"""

    assert report_judge(SCOPE_IN, "red", ["R09"], "red", ["R09"]) is Grade.OK
    assert report_judge(SCOPE_IN, "red", ["R09"], "red", ["R01"]) is Grade.ACCEPTABLE
    assert report_judge(SCOPE_IN, "red", ["R09"], "gray", []) is Grade.ACCEPTABLE
    assert report_judge(SCOPE_IN, "red", ["R09"], "orange", ["O08"]) is Grade.FAIL
    assert report_judge(SCOPE_OUT, "red", [], "green", []) is Grade.OUT_OF_SCOPE


def test_judge_green_on_an_in_scope_challenge_is_always_a_failure() -> None:
    """Green fails an in-scope challenge even if the file listed it by mistake"""

    assert report_judge(SCOPE_IN, "green", [], "green", []) is Grade.FAIL
