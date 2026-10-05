"""Files of a job folder: the raw archive, job.json and reputation.json, written and read as plain data"""

import hashlib
import hmac
from pathlib import Path

from pydantic import ValidationError

from mcplain import __version__
from mcplain.config import DEFAULT_LIMITS, Limits
from mcplain.errors import JobError
from mcplain.models import ArchiveFormat, JobFile, Reputation, ReputationStatus
from mcplain.verdict import RULES_VERSION

JOB_FILE = "job.json"
REPUTATION_FILE = "reputation.json"
ARCHIVE_STEM = "source"
FILE_MODE = 0o644
CHUNK_SIZE = 64 * 1024


def archive_name(archive_format: ArchiveFormat) -> str:
    """Return the file name of the raw archive in a job folder"""

    return f"{ARCHIVE_STEM}.{archive_format.value}"


def write_job(folder: Path, job: JobFile, reputation: Reputation) -> None:
    """Write job.json and reputation.json next to the archive, all readable by the analysis user"""

    _write(folder / JOB_FILE, job.model_dump_json())
    _write(folder / REPUTATION_FILE, reputation.model_dump_json())
    (folder / job.archive).chmod(FILE_MODE)


def _write(path: Path, text: str) -> None:
    """Create one file that must not exist yet"""

    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)
    path.chmod(FILE_MODE)


def read_job(folder: Path, limits: Limits = DEFAULT_LIMITS) -> JobFile:
    """Read job.json and check the archive name and the engine and rules versions"""

    path = folder / JOB_FILE
    try:
        if path.stat().st_size > limits.max_json_bytes:
            raise JobError("analyze.job_invalid")
        job = JobFile.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as error:
        raise JobError("analyze.job_invalid") from error
    if job.archive != archive_name(job.archive_format):
        raise JobError("analyze.job_invalid")
    if job.engine_version != __version__ or job.rules_version != RULES_VERSION:
        raise JobError("analyze.job_version_mismatch", engine=__version__, rules=RULES_VERSION)
    return job


def verified_archive(folder: Path, job: JobFile) -> Path:
    """Return the archive path after checking that its sha256 is the one recorded at download"""

    path = folder / job.archive
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as error:
        raise JobError("analyze.job_invalid") from error
    if not hmac.compare_digest(digest.hexdigest(), job.archive_sha256):
        raise JobError("analyze.archive_mismatch")
    return path


def read_reputation(folder: Path, limits: Limits = DEFAULT_LIMITS) -> Reputation:
    """Read reputation.json; a missing or unreadable file means the reputation is unavailable"""

    path = folder / REPUTATION_FILE
    unavailable = Reputation(status=ReputationStatus.UNAVAILABLE)
    try:
        if path.stat().st_size > limits.max_json_bytes:
            return unavailable
        return Reputation.model_validate_json(path.read_bytes())
    except (OSError, ValidationError):
        return unavailable
