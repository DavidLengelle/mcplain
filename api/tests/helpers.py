"""Helpers shared by the API tests: settings and job folders built from the engine fixtures"""

import hashlib
import io
import tarfile
from pathlib import Path

from mcplain import __version__
from mcplain.job import write_job
from mcplain.models import (
    AnalyzedSource,
    ArchiveFormat,
    InputKind,
    InputSpec,
    JobFile,
    Reputation,
    ReputationStatus,
    SourceKind,
    SourceOrigin,
)
from mcplain.verdict import RULES_VERSION
from mcplain_api.settings import Settings

ENGINE_FIXTURES = Path(__file__).resolve().parents[2] / "engine" / "tests" / "fixtures"
REPUTATION_FILE = "reputation.json"
FOLDER_MODE = 0o755
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


def make_settings(**values: object) -> Settings:
    """Return settings for the tests, independent of the environment of the machine"""

    defaults: dict[str, object] = {"database_url": "sqlite://", "jobs_dir": Path("/tmp/mcplain-test-jobs")}
    defaults.update(values)
    return Settings(_env_file=None, **defaults)


def tar_gz_folder(folder: Path, prefix: str = "package/") -> bytes:
    """Build a tar.gz archive of every file below a fixture folder, read as bytes and never imported"""

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            content = path.read_bytes()
            info = tarfile.TarInfo(prefix + path.relative_to(folder).as_posix())
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def fixture_reputation(folder: Path) -> Reputation:
    """Return the OSV reputation a fixture ships as data, or a clean one"""

    path = folder / REPUTATION_FILE
    if path.is_file():
        return Reputation.model_validate_json(path.read_text(encoding="utf-8"))
    return Reputation(status=ReputationStatus.CHECKED)


def build_job(job_dir: Path, fixture: Path) -> JobFile:
    """Write a job folder readable by the atelier user, whose archive is built from a fixture folder"""

    data = tar_gz_folder(fixture)
    job_dir.mkdir(parents=True)
    job_dir.chmod(FOLDER_MODE)
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
    write_job(job_dir, job, fixture_reputation(fixture))
    return job
