"""The corpus: MCP servers whose right answer is known, analyzed in local mode and graded OK, ACCEPTABLE or FAIL"""

import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import pytest

from mcplain import __version__
from mcplain.analyze import analyze_directory, not_checked
from mcplain.models import AnalysisResult, GrayCase, VerdictColor
from mcplain.verdict import RULES_VERSION

ENGINE = Path(__file__).resolve().parents[1]
REPOSITORY = ENGINE.parent
FIXTURES = ENGINE / "tests" / "fixtures"
PUBLIC = FIXTURES / "corpus"
PRIVATE = FIXTURES / "corpus-private"
PRIVATE_RELATIVE = "engine/tests/fixtures/corpus-private"
REPORT = REPOSITORY / "bench" / "private" / "corpus.md"
HOOK = REPOSITORY / ".githooks" / "pre-commit"
HONEST_COLORS = ("green", "orange", "gray")
MINIMUM_PER_COLOR = 5
COLORS = {color.value for color in VerdictColor}
GRAY_CASES = {case.value for case in GrayCase}


class Grade(StrEnum):
    """Class that lists how a corpus server is judged"""

    OK = "OK"
    ACCEPTABLE = "ACCEPTABLE"
    FAIL = "FAIL"


@dataclass
class Expected:
    """Class that holds the expected answer of one corpus server, read from its expected.toml"""

    name: str
    folder: Path
    color: str
    accept: list[str]
    rules: list[str]
    gray_case: str | None
    style: str
    tests: str
    known_gap: str | None = None
    trap: bool = False


@dataclass
class Judgement:
    """Class that holds the grade of one corpus server and what differs from the expected answer"""

    grade: Grade
    color: str
    rules: list[str]
    gray_case: str | None
    gaps: list[str] = field(default_factory=list)


def read_expected(folder: Path, name: str, trap: bool) -> Expected:
    """Read and check the expected.toml of one corpus server"""

    data = tomllib.loads((folder / "expected.toml").read_text(encoding="utf-8"))
    color = data["color"]
    accept = list(data["accept"])
    rules = sorted(data["rules"])
    gray_case = data.get("gray_case")
    assert color in COLORS, f"{name}: unknown color {color}"
    assert color in accept, f"{name}: accept must hold the expected color"
    assert set(accept) <= COLORS, f"{name}: unknown color in accept"
    assert all(isinstance(rule, str) and rule for rule in rules), f"{name}: rules must be rule ids"
    if color == VerdictColor.GRAY.value:
        assert gray_case in GRAY_CASES, f"{name}: a gray server needs a known gray_case"
    else:
        assert gray_case is None, f"{name}: gray_case is only for a gray server"
    assert data["style"].strip() and data["tests"].strip(), f"{name}: style and tests must be written"
    return Expected(
        name=name,
        folder=folder,
        color=color,
        accept=accept,
        rules=rules,
        gray_case=gray_case,
        style=data["style"],
        tests=data["tests"],
        known_gap=data.get("known_gap"),
        trap=trap,
    )


def public_corpus() -> list[Expected]:
    """Return every server of the public corpus, sorted by color then name"""

    entries = []
    for folder in sorted(path for path in PUBLIC.glob("*/*") if path.is_dir()):
        name = f"{folder.parent.name}/{folder.name}"
        entries.append(read_expected(folder, name, trap=False))
    return entries


def private_corpus() -> list[Path]:
    """Return the folders of the private corpus, which only exists on David's computer"""

    if not PRIVATE.is_dir():
        return []
    return sorted(path for path in PRIVATE.iterdir() if path.is_dir() and (path / "expected.toml").is_file())


def fired_rules(result: AnalysisResult) -> list[str]:
    """Return the rules of the alerts of a verdict, each one once"""

    return sorted({alert.rule for alert in result.verdict.alerts})


def judge(expected: Expected, result: AnalysisResult) -> Judgement:
    """Grade an analysis against the expected answer: OK, ACCEPTABLE, or FAIL"""

    color = result.verdict.color.value
    rules = fired_rules(result)
    gray_case = None
    if result.verdict.gray_case is not None:
        gray_case = result.verdict.gray_case.value
    gaps = []
    if color != expected.color:
        gaps.append(f"color {color}, expected {expected.color}")
    missing = sorted(set(expected.rules) - set(rules))
    extra = sorted(set(rules) - set(expected.rules))
    if missing:
        gaps.append("missing rules " + ", ".join(missing))
    if extra:
        gaps.append("extra rules " + ", ".join(extra))
    if expected.gray_case is not None and gray_case != expected.gray_case:
        gaps.append(f"gray_case {gray_case}, expected {expected.gray_case}")
    grade = Grade.FAIL
    if not gaps:
        grade = Grade.OK
    elif color in expected.accept:
        grade = Grade.ACCEPTABLE
    if expected.trap and color == VerdictColor.GREEN.value:
        grade = Grade.FAIL
        gaps.append("a trap came out green")
    return Judgement(grade=grade, color=color, rules=rules, gray_case=gray_case, gaps=gaps)


def analyze(expected: Expected) -> Judgement:
    """Analyze one corpus server in local mode, without network and without reputation, and grade it"""

    return judge(expected, analyze_directory(expected.folder, reputation=not_checked()))


PUBLIC_CORPUS = public_corpus()


def corpus_case(expected: Expected) -> object:
    """Wrap a public corpus server as a test case; a known gap is a strict xfail, so a fix shows up"""

    marks = []
    if expected.known_gap is not None:
        marks.append(pytest.mark.xfail(reason=expected.known_gap, strict=True))
    return pytest.param(expected, id=expected.name, marks=marks)


@pytest.mark.parametrize("expected", [corpus_case(entry) for entry in PUBLIC_CORPUS])
def test_public_corpus_server_is_not_a_failure(expected: Expected) -> None:
    """Each honest server of the public corpus gets OK or ACCEPTABLE, never FAIL"""

    judgement = analyze(expected)
    assert judgement.grade is not Grade.FAIL, f"{expected.name}: " + "; ".join(judgement.gaps)


def test_public_corpus_holds_only_honest_servers_of_each_color() -> None:
    """The public corpus holds green, orange and gray servers only, at least five of each, filed by color"""

    folders = {path.name for path in PUBLIC.iterdir() if path.is_dir()}
    assert folders == set(HONEST_COLORS)
    for color in HONEST_COLORS:
        entries = [entry for entry in PUBLIC_CORPUS if entry.folder.parent.name == color]
        assert len(entries) >= MINIMUM_PER_COLOR, color
        assert all(entry.color == color for entry in entries)
        assert all(VerdictColor.RED.value not in entry.accept for entry in entries)


def test_corpus_files_have_no_test_names() -> None:
    """No corpus file is named like a test file, so no test runner ever picks one up"""

    names = [path.name for path in PUBLIC.rglob("*") if path.is_file()]
    assert names
    for name in names:
        assert not name.startswith("test_"), name
        assert not name.endswith("_test.py"), name
        assert name != "conftest.py"
        assert ".test." not in name and ".spec." not in name, name


def test_judge_grades_a_green_trap_as_a_failure() -> None:
    """For a trap, gray is ACCEPTABLE and green is always a FAIL, even if green were listed as acceptable"""

    trap = Expected(
        name="trap",
        folder=PUBLIC,
        color="red",
        accept=["red", "gray", "green"],
        rules=["R01"],
        gray_case=None,
        style="s",
        tests="t",
        trap=True,
    )
    gray = AnalysisResult.model_validate({"status": "ok", "verdict": {"color": "gray", "gray_case": "no_tools_found"}})
    green = AnalysisResult.model_validate({"status": "ok", "verdict": {"color": "green"}})
    assert judge(trap, gray).grade is Grade.ACCEPTABLE
    assert judge(trap, green).grade is Grade.FAIL


def test_judge_needs_the_rules_for_ok() -> None:
    """The right color with other rules is ACCEPTABLE, another color outside accept is a FAIL"""

    entry = PUBLIC_CORPUS[0]
    expected = Expected(
        name="x", folder=entry.folder, color="orange", accept=["orange"], rules=["O02"], gray_case=None, style="s", tests="t"
    )
    other_rule = AnalysisResult.model_validate(
        {"status": "ok", "verdict": {"color": "orange", "alerts": [{"rule": "O08", "color": "orange", "kind": "power_to_know"}]}}
    )
    right = AnalysisResult.model_validate(
        {"status": "ok", "verdict": {"color": "orange", "alerts": [{"rule": "O02", "color": "orange", "kind": "power_to_know"}]}}
    )
    gray = AnalysisResult.model_validate({"status": "ok", "verdict": {"color": "gray", "gray_case": "no_tools_found"}})
    assert judge(expected, right).grade is Grade.OK
    assert judge(expected, other_rule).grade is Grade.ACCEPTABLE
    assert judge(expected, gray).grade is Grade.FAIL


def git_available() -> bool:
    """Tell whether git and the repository are there, which is not the case in every copy of the code"""

    return shutil.which("git") is not None and (REPOSITORY / ".git").exists()


def git(*args: str) -> str:
    """Run a read-only git command in the repository and return its output"""

    completed = subprocess.run(["git", *args], cwd=REPOSITORY, capture_output=True, text=True, check=False)
    return completed.stdout


@pytest.mark.skipif(not git_available(), reason="git or the repository is not available")
def test_no_private_corpus_file_is_tracked_by_git() -> None:
    """Not one file of the private corpus is in the git index"""

    assert git("ls-files", "--", PRIVATE_RELATIVE) == ""
    assert git("ls-files", "--", ":(glob)**/corpus-private/**") == ""


@pytest.mark.skipif(not git_available(), reason="git or the repository is not available")
def test_private_corpus_is_ignored_by_git() -> None:
    """The private corpus folder and anything inside it are ignored"""

    assert git("check-ignore", f"{PRIVATE_RELATIVE}/").strip() != ""
    assert git("check-ignore", f"{PRIVATE_RELATIVE}/trap/expected.toml").strip() != ""


def test_pre_commit_hook_refuses_the_private_corpus() -> None:
    """The versioned pre-commit hook is executable and refuses any staged corpus-private path"""

    text = HOOK.read_text(encoding="utf-8")
    assert HOOK.stat().st_mode & 0o111
    assert "git diff --cached --name-only" in text
    assert "corpus-private" in text
    assert "exit 1" in text


def report_line(name: str, expected: str, judgement: Judgement) -> str:
    """Write one line of the private report: the name, the colors and the grade, never the content"""

    return f"| {name} | {expected} | {judgement.color} | {judgement.grade.value} |"


def test_private_corpus_report() -> None:
    """On David's computer only: grade the private traps and write bench/private/corpus.md, without failing"""

    folders = private_corpus()
    if not folders:
        pytest.skip("no private corpus on this computer")
    lines = [
        "# Corpus privé",
        "",
        f"Moteur {__version__}, règles version {RULES_VERSION}. Ce fichier ne sort jamais de cet ordinateur.",
        "",
        "| Piège | Attendu | Obtenu | Classement |",
        "| --- | --- | --- | --- |",
    ]
    for folder in folders:
        try:
            expected = read_expected(folder, folder.name, trap=True)
        except (AssertionError, KeyError, tomllib.TOMLDecodeError):
            lines.append(f"| {folder.name} | ? | ? | expected.toml invalide |")
            continue
        lines.append(report_line(folder.name, expected.color, analyze(expected)))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def corpus_entry(name: str) -> Expected:
    """Return one server of the public corpus by its name"""

    return next(entry for entry in PUBLIC_CORPUS if entry.name == name)


def test_echo_terminal_gets_its_whole_answer() -> None:
    """A command split with shlex keeps the label: the terminal gives O02 and O08, no R09"""

    judgement = analyze(corpus_entry("orange/echo-terminal"))
    assert judgement.grade is Grade.OK
    assert judgement.rules == ["O02", "O08"]


def test_native_launcher_is_orange_and_says_what_it_could_not_read() -> None:
    """The launcher gives O08, and the report says that the rest of the server could not be read"""

    entry = corpus_entry("orange/native-launcher")
    assert analyze(entry).grade is Grade.OK
    coverage = analyze_directory(entry.folder, reputation=not_checked()).verdict.coverage
    assert coverage is not None
    assert coverage.not_checked
