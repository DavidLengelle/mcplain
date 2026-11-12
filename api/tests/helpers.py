"""Helpers shared by the API tests: settings and job folders built from the engine fixtures"""

import hashlib
import io
import re
import tarfile
from pathlib import Path
from typing import Any

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

REPOSITORY = Path(__file__).resolve().parents[2]
ENGINE_FIXTURES = REPOSITORY / "engine" / "tests" / "fixtures"
SERVICE_LINE = re.compile(r"^  ([a-z_]+):\s*$")
REPUTATION_FILE = "reputation.json"
LAMP_IDS: tuple[str, ...] = ("files_read", "files_write", "internet", "commands", "secrets", "hidden_text")
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


def lamps_of(*lit: str, danger: tuple[str, ...] = ()) -> list[dict[str, object]]:
    """Return the six lamps of a report, with some of them on or in danger"""

    lamps: list[dict[str, object]] = []
    for lamp in LAMP_IDS:
        state = "off"
        if lamp in lit:
            state = "on"
        if lamp in danger:
            state = "danger"
        lamps.append({"id": lamp, "state": state})
    return lamps


def tool_report(name: str, description: str = "Says what it does.", lamps: list[dict[str, object]] | None = None) -> dict[str, object]:
    """Return one tool of a report, as the engine stores it"""

    return {
        "name": name,
        "description": description,
        "description_is_dynamic": False,
        "file": "server.py",
        "line": 1,
        "declaration": "decorator",
        "location_kind": "server_code",
        "lamps": lamps or lamps_of(),
    }


def report(tools: list[dict[str, object]], **server: object) -> dict[str, object]:
    """Return a stored report of one server holding some tools"""

    return {
        "status": "ok",
        "source": PACKAGE_SOURCE.model_dump(mode="json"),
        "servers": [{"path": ".", "language": "python", "tools": tools, "lamps": lamps_of(), **server}],
        "verdict": {"color": "orange", "rules_version": RULES_VERSION, "rules_count": 25},
    }


def compose_services() -> dict[str, str]:
    """Return the text of every service of compose.yaml, cut at its two-space indented name"""

    services: dict[str, list[str]] = {}
    inside = False
    current = None
    for line in (REPOSITORY / "compose.yaml").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith(" "):
            inside = line == "services:"
            current = None
            continue
        match = SERVICE_LINE.match(line)
        if inside and match is not None:
            current = match.group(1)
            services[current] = []
        elif current is not None:
            services[current].append(line)
    return {name: "\n".join(lines) for name, lines in services.items()}


def uncommented(block: str) -> str:
    """Remove the comment lines of a service"""

    return "\n".join(line for line in block.splitlines() if not line.strip().startswith("#"))


TEST_ALTCHA_KEY = "test only altcha key, never a real one"


def altcha_settings(**values: object) -> Settings:
    """Return test settings with a test ALTCHA key and the cheapest cost, so that each test solves its own challenges"""

    defaults: dict[str, object] = {"altcha_hmac_key": TEST_ALTCHA_KEY, "altcha_cost": 1}
    defaults.update(values)
    return make_settings(**defaults)


def altcha_headers(client: Any) -> dict[str, str]:
    """Ask the API for a challenge and solve it as the widget of a browser would"""

    from altcha import Challenge, Payload, solve_challenge

    challenge = Challenge.from_dict(client.get("/api/altcha/challenge").json())
    solution = solve_challenge(challenge)
    assert solution is not None
    return {"x-altcha": Payload(challenge, solution).to_base64()}


def post_analysis(client: Any, body: dict[str, object], headers: dict[str, str] | None = None) -> Any:
    """Ask for an analysis with a fresh ALTCHA solution, as the website does"""

    sent = altcha_headers(client)
    sent.update(headers or {})
    return client.post("/api/analyses", json=body, headers=sent)
