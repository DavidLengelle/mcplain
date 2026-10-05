"""Tests of the offline job step: a job folder holds a raw archive, job.json and reputation.json"""

import hashlib
import json
from pathlib import Path

import pytest
from builders import tar_gz_folder

from mcplain import __version__, atelier
from mcplain.analyze import analyze_directory, analyze_job
from mcplain.job import write_job
from mcplain.models import (
    AnalysisResult,
    AnalysisStatus,
    AnalyzedSource,
    ArchiveFormat,
    InputKind,
    InputSpec,
    JobFile,
    Reputation,
    ReputationStatus,
    SourceKind,
    SourceOrigin,
    VerdictColor,
)
from mcplain.verdict import RULES_VERSION

PACKAGE_SOURCE = AnalyzedSource(
    kind=SourceKind.NPM,
    name="fixture",
    version="1.0.0",
    integrity="sha512-test",
    url="https://registry.npmjs.org/fixture/-/fixture-1.0.0.tgz",
    artifact="npm_tarball",
    origin=SourceOrigin.PUBLISHED_PACKAGE,
    reason="source.requested_package",
)
CHECKED = Reputation(status=ReputationStatus.CHECKED)
REPUTATION_FILE = "reputation.json"


def build_job(
    job_dir: Path,
    fixture: Path,
    reputation: Reputation = CHECKED,
    source: AnalyzedSource = PACKAGE_SOURCE,
    select: str | None = None,
    engine_version: str = __version__,
) -> JobFile:
    """Write a job folder whose archive is built by the test from a fixture folder"""

    data = tar_gz_folder(fixture)
    job_dir.mkdir()
    (job_dir / "source.tar.gz").write_bytes(data)
    job = JobFile(
        spec=InputSpec(kind=InputKind.NPM, package="fixture", ignored_arguments=["--port", "3000"]),
        source=source,
        select=select,
        archive="source.tar.gz",
        archive_format=ArchiveFormat.TAR_GZ,
        archive_sha256=hashlib.sha256(data).hexdigest(),
        source_key="npm:fixture@1.0.0",
        engine_version=engine_version,
        rules_version=RULES_VERSION,
    )
    write_job(job_dir, job, reputation)
    return job


@pytest.mark.parametrize(
    "folder",
    ["python_fastmcp_clean", "python_fastmcp_poisoned", "postmark_like", "official_fetch_like", "ts_registertool", "monorepo"],
)
def test_job_gives_the_same_result_as_the_folder(fixtures: Path, tmp_path: Path, folder: str) -> None:
    """Analyzing the archive of a fixture gives exactly what analyze_directory gives on the fixture itself"""

    build_job(tmp_path / "input", fixtures / folder)
    from_job = analyze_job(tmp_path / "input", tmp_path / "work")
    from_folder = analyze_directory(fixtures / folder, source=PACKAGE_SOURCE, reputation=CHECKED)
    from_folder.ignored_arguments = ["--port", "3000"]
    assert from_job.model_dump() == from_folder.model_dump()


def test_selection_is_applied(fixtures: Path, tmp_path: Path) -> None:
    """The select of job.json picks one server of the package"""

    build_job(tmp_path / "input", fixtures / "monorepo", select="src/a")
    result = analyze_job(tmp_path / "input", tmp_path / "work")
    assert result.status is AnalysisStatus.OK
    assert result.servers[0].path == "src/a"


def test_github_folder_is_applied(fixtures: Path, tmp_path: Path) -> None:
    """The folder of GitHub code recorded in the source is the place where the server is looked for"""

    source = AnalyzedSource(
        kind=SourceKind.GITHUB,
        name="demo/servers",
        revision="a" * 40,
        reference="main",
        subdir="src/b",
        url="https://github.com/demo/servers/tree/" + "a" * 40 + "/src/b",
        artifact="github_tarball",
        origin=SourceOrigin.GITHUB_CODE,
        reason="source.no_package_manifest",
    )
    build_job(tmp_path / "input", fixtures / "monorepo", source=source)
    result = analyze_job(tmp_path / "input", tmp_path / "work")
    assert result.status is AnalysisStatus.OK
    assert result.servers[0].path == "src/b"


def test_reputation_file_feeds_r11(fixtures: Path, tmp_path: Path) -> None:
    """The reputation.json of the R11 fixture, given to the job, makes R11 fire"""

    folder = fixtures / "rules" / "R11" / "positive"
    reputation = Reputation.model_validate_json((folder / REPUTATION_FILE).read_text(encoding="utf-8"))
    build_job(tmp_path / "input", folder, reputation=reputation)
    result = analyze_job(tmp_path / "input", tmp_path / "work")
    assert result.reputation == reputation
    assert result.verdict.color is VerdictColor.RED
    assert "R11" in {alert.rule for alert in result.verdict.alerts}


def test_missing_reputation_file_is_unavailable(fixtures: Path, tmp_path: Path) -> None:
    """Without reputation.json the reputation is unavailable, never checked"""

    build_job(tmp_path / "input", fixtures / "python_fastmcp_clean")
    (tmp_path / "input" / REPUTATION_FILE).unlink()
    result = analyze_job(tmp_path / "input", tmp_path / "work")
    assert result.reputation is not None
    assert result.reputation.status is ReputationStatus.UNAVAILABLE


def test_unreadable_job_is_gray(tmp_path: Path) -> None:
    """A job folder without job.json gives a gray error result"""

    (tmp_path / "input").mkdir()
    result = analyze_job(tmp_path / "input", tmp_path / "work")
    assert result.status is AnalysisStatus.ERROR
    assert result.error is not None and result.error.code == "analyze.job_invalid"
    assert result.verdict.color is VerdictColor.GRAY


def test_archive_name_must_match_its_format(fixtures: Path, tmp_path: Path) -> None:
    """job.json cannot point to another file than source.<format>"""

    build_job(tmp_path / "input", fixtures / "python_fastmcp_clean")
    path = tmp_path / "input" / "job.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["archive"] = "../other.tar.gz"
    path.write_text(json.dumps(document), encoding="utf-8")
    result = analyze_job(tmp_path / "input", tmp_path / "work")
    assert result.error is not None and result.error.code == "analyze.job_invalid"
    assert result.verdict.color is VerdictColor.GRAY


def test_other_engine_version_is_gray(fixtures: Path, tmp_path: Path) -> None:
    """A job prepared for another engine version is not analyzed"""

    build_job(tmp_path / "input", fixtures / "python_fastmcp_clean", engine_version="0.0.0")
    result = analyze_job(tmp_path / "input", tmp_path / "work")
    assert result.error is not None and result.error.code == "analyze.job_version_mismatch"
    assert result.verdict.color is VerdictColor.GRAY


def test_changed_archive_is_gray(fixtures: Path, tmp_path: Path) -> None:
    """An archive whose sha256 differs from job.json is not extracted"""

    build_job(tmp_path / "input", fixtures / "python_fastmcp_clean")
    archive = tmp_path / "input" / "source.tar.gz"
    archive.write_bytes(archive.read_bytes() + b"\0")
    result = analyze_job(tmp_path / "input", tmp_path / "work")
    assert result.error is not None and result.error.code == "analyze.archive_mismatch"
    assert result.source == PACKAGE_SOURCE
    assert result.verdict.color is VerdictColor.GRAY
    assert not (tmp_path / "work").exists()


def test_unknown_archive_format_is_gray(tmp_path: Path) -> None:
    """Bytes that are not an archive give a gray error result"""

    job_dir = tmp_path / "input"
    job_dir.mkdir()
    data = b"not an archive"
    (job_dir / "source.tar.gz").write_bytes(data)
    job = JobFile(
        spec=InputSpec(kind=InputKind.NPM, package="fixture"),
        source=PACKAGE_SOURCE,
        archive="source.tar.gz",
        archive_format=ArchiveFormat.TAR_GZ,
        archive_sha256=hashlib.sha256(data).hexdigest(),
        source_key="npm:fixture@1.0.0",
        engine_version=__version__,
        rules_version=RULES_VERSION,
    )
    write_job(job_dir, job, CHECKED)
    result = analyze_job(job_dir, tmp_path / "work")
    assert result.error is not None and result.error.code == "archive.unknown_format"
    assert result.verdict.color is VerdictColor.GRAY


def test_command_prints_one_json_line(fixtures: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """mcplain-analyze writes the result as one JSON line on stdout and exits with 0"""

    build_job(tmp_path / "input", fixtures / "python_fastmcp_poisoned")
    code = atelier.main(["--input", str(tmp_path / "input"), "--work", str(tmp_path / "work")])
    out = capsys.readouterr().out
    assert code == 0
    assert out.endswith("\n") and out.count("\n") == 1
    result = AnalysisResult.model_validate_json(out)
    assert result.verdict.color is VerdictColor.RED


def test_command_exits_with_0_on_a_gray_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A gray error result is still a result: exit code 0"""

    (tmp_path / "input").mkdir()
    code = atelier.main(["--input", str(tmp_path / "input"), "--work", str(tmp_path / "work")])
    result = AnalysisResult.model_validate_json(capsys.readouterr().out)
    assert code == 0
    assert result.verdict.color is VerdictColor.GRAY


def test_command_exits_with_1_without_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unexpected failure writes nothing on stdout and exits with 1"""

    def broken(job_input_dir: Path, work_dir: Path) -> AnalysisResult:
        """Fail like a bug would"""

        raise RuntimeError("secret detail")

    monkeypatch.setattr(atelier, "analyze_job", broken)
    code = atelier.main(["--input", str(tmp_path), "--work", str(tmp_path / "work")])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "RuntimeError" in captured.err
    assert "secret detail" not in captured.err


def test_command_keeps_stray_prints_off_stdout(
    fixtures: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Anything printed during the analysis goes to stderr; stdout holds only the result"""

    def noisy(job_input_dir: Path, work_dir: Path) -> AnalysisResult:
        """Print a line, then analyze"""

        print("noise")
        return analyze_job(job_input_dir, work_dir)

    build_job(tmp_path / "input", fixtures / "python_fastmcp_clean")
    monkeypatch.setattr(atelier, "analyze_job", noisy)
    atelier.main(["--input", str(tmp_path / "input"), "--work", str(tmp_path / "work")])
    captured = capsys.readouterr()
    assert "noise" in captured.err
    AnalysisResult.model_validate_json(captured.out)
