"""Atelier launcher: one hardened, disposable container without network for each analysis"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from docker import DockerClient
from docker.errors import DockerException
from docker.models.containers import Container
from docker.types import LogConfig, Mount, Ulimit
from pydantic import ValidationError

from mcplain.models import AnalysisResult
from mcplain_api.settings import Settings

ROLE_LABEL = "mcplain.role"
ATELIER_ROLE = "atelier"
JOB_INPUT_TARGET = "/job/input"
ATELIER_USER = "10001:10001"
NANO_CPUS_PER_CPU = 1_000_000_000
MAX_STDOUT_BYTES = 5 * 1024 * 1024
MAX_STDERR_CHARS = 2000
MAX_STDERR_BYTES = 4 * MAX_STDERR_CHARS
RUNNING_STATES: frozenset[str] = frozenset({"created", "running", "restarting", "paused"})
ATELIER_TIMEOUT = "atelier_timeout"
ATELIER_INVALID_RESULT = "atelier_invalid_result"
ATELIER_ERROR = "atelier_error"


@dataclass(frozen=True)
class AtelierRun:
    """Class that holds what an atelier produced: a validated result, or the code of a gray failure"""

    result: AnalysisResult | None
    error_code: str | None
    stderr: str = ""
    exit_code: int | None = None


def atelier_options(input_dir: Path) -> dict[str, Any]:
    """Return the only container options of an atelier: no network, no secret, read-only, one read-only folder"""

    return {
        "network_mode": "none",
        "read_only": True,
        "tmpfs": {
            "/work": "rw,noexec,nosuid,nodev,size=256m",
            "/tmp": "rw,noexec,nosuid,nodev,size=16m",
        },
        "user": ATELIER_USER,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
        "pids_limit": 64,
        "mem_limit": "1g",
        "memswap_limit": "1g",
        "nano_cpus": NANO_CPUS_PER_CPU,
        "ulimits": [Ulimit(name="nofile", soft=256, hard=256)],
        "environment": {},
        "use_config_proxy": False,
        "mounts": [Mount(target=JOB_INPUT_TARGET, source=str(input_dir), type="bind", read_only=True)],
        "log_config": LogConfig(type="json-file", config={"max-size": "5m", "max-file": "1"}),
        "labels": {ROLE_LABEL: ATELIER_ROLE},
    }


def run_atelier(
    client: DockerClient,
    input_dir: Path,
    settings: Settings,
    test_entrypoint: list[str] | None = None,
) -> AtelierRun:
    """Run one atelier on a job folder, wait for it with a time limit, read its result, and always remove it"""

    options = atelier_options(input_dir)
    if test_entrypoint is not None:
        options["entrypoint"] = test_entrypoint
    try:
        container = client.containers.create(settings.atelier_image, **options)
    except DockerException as error:
        return AtelierRun(None, ATELIER_ERROR, type(error).__name__)
    try:
        return _supervise(container, settings.atelier_timeout)
    except DockerException as error:
        return AtelierRun(None, ATELIER_ERROR, type(error).__name__)
    finally:
        _remove(container)


def _supervise(container: Container, timeout: int) -> AtelierRun:
    """Start the container, kill it after the time limit, then read and validate its standard output"""

    container.start()
    try:
        status = container.wait(timeout=timeout)
    except requests.exceptions.RequestException:
        container.reload()
        if container.status in RUNNING_STATES:
            container.kill()
            return AtelierRun(None, ATELIER_TIMEOUT, _stderr(container))
        status = container.wait(timeout=timeout)
    exit_code = status.get("StatusCode")
    stderr = _stderr(container)
    if exit_code != 0:
        return AtelierRun(None, ATELIER_ERROR, stderr, exit_code)
    stdout, complete = _read(container, True, MAX_STDOUT_BYTES)
    if not complete:
        return AtelierRun(None, ATELIER_INVALID_RESULT, stderr, exit_code)
    try:
        result = AnalysisResult.model_validate_json(stdout)
    except ValidationError:
        return AtelierRun(None, ATELIER_INVALID_RESULT, stderr, exit_code)
    return AtelierRun(result, None, stderr, exit_code)


def _read(container: Container, stdout: bool, limit: int) -> tuple[bytes, bool]:
    """Read at most limit bytes of one output stream of a stopped container, and tell whether it was complete"""

    data = bytearray()
    stream = container.logs(stdout=stdout, stderr=not stdout, stream=True, follow=False)
    try:
        for chunk in stream:
            data.extend(chunk)
            if len(data) > limit:
                return bytes(data[:limit]), False
    finally:
        stream.close()
    return bytes(data), True


def _stderr(container: Container) -> str:
    """Return the start of the error output, cut to 2000 characters, for the error log only"""

    try:
        data, _ = _read(container, False, MAX_STDERR_BYTES)
    except DockerException:
        return ""
    return data.decode("utf-8", errors="replace")[:MAX_STDERR_CHARS]


def _remove(container: Container) -> None:
    """Remove a container, running or not"""

    try:
        container.remove(force=True)
    except DockerException:
        return


def remove_orphans(client: DockerClient) -> int:
    """Remove every atelier container left behind, for example by a dispatcher that stopped abruptly"""

    containers = client.containers.list(all=True, filters={"label": f"{ROLE_LABEL}={ATELIER_ROLE}"})
    for container in containers:
        _remove(container)
    return len(containers)
