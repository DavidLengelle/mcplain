"""Tests of real ateliers: they need Docker and the image built with docker build -f docker/atelier.Dockerfile"""

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import docker
import pytest
from docker import DockerClient
from docker.errors import ImageNotFound, NotFound
from docker.models.containers import Container
from helpers import ENGINE_FIXTURES, build_job, make_settings
from mcplain.models import VerdictColor

from mcplain_api.launcher import ATELIER_INVALID_RESULT, ATELIER_TIMEOUT, atelier_options, run_atelier

pytestmark = pytest.mark.docker

IMAGE = "mcplain-atelier:dev"
PROXY_CONFIG = {"proxies": {"default": {"httpProxy": "http://proxy.invalid:3128", "noProxy": "localhost"}}}
PROBE = """
echo "net=$(ls /sys/class/net | tr '\\n' ' ')"
if touch /probe 2>/dev/null; then echo root=writable; else echo root=readonly; fi
cp /bin/true /work/probe
if /work/probe 2>/dev/null; then echo work=exec; else echo work=noexec; fi
if touch /job/input/probe 2>/dev/null; then echo input=writable; else echo input=readonly; fi
echo "uid=$(id -u)"
echo "gid=$(id -g)"
echo "proxy=$(env | grep -ci proxy)"
echo "socket=$(grep -c docker.sock /proc/self/mounts)"
echo "caps=$(grep CapEff /proc/self/status | tr -d '\\t' | cut -d: -f2)"
echo "nonewprivs=$(grep NoNewPrivs /proc/self/status | tr -d '\\t' | cut -d: -f2)"
echo "seccomp=$(grep '^Seccomp:' /proc/self/status | tr -d '\\t' | cut -d: -f2)"
python -c "import importlib.util as u; print('imports=' + ','.join(m for m in ('fastapi', 'psycopg', 'docker', 'sqlalchemy') if u.find_spec(m)))"
"""


class RecordingContainers:
    """Class that creates real containers and remembers their identifiers"""

    def __init__(self, client: DockerClient) -> None:
        """Wrap the real containers collection"""

        self.client = client
        self.created: list[str] = []

    def create(self, image: str, **options: Any) -> Container:
        """Create a container and remember it"""

        container = self.client.containers.create(image, **options)
        self.created.append(container.id)
        return container


class RecordingClient:
    """Class that behaves like a DockerClient for run_atelier and records the created containers"""

    def __init__(self, client: DockerClient) -> None:
        """Hold the recording collection"""

        self.containers = RecordingContainers(client)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[DockerClient]:
    """Return a Docker client whose configuration file holds a proxy, to prove that ateliers never get it"""

    config = tmp_path / "docker-config"
    config.mkdir()
    (config / "config.json").write_text(json.dumps(PROXY_CONFIG), encoding="utf-8")
    monkeypatch.setenv("DOCKER_CONFIG", str(config))
    docker_client = docker.from_env()
    try:
        docker_client.images.get(IMAGE)
    except ImageNotFound:
        pytest.fail(f"build the image first: docker build -f docker/atelier.Dockerfile -t {IMAGE} .")
    yield docker_client
    docker_client.close()


def input_folder(tmp_path: Path) -> Path:
    """Create an empty job input folder readable by the atelier user"""

    folder = tmp_path / "input"
    folder.mkdir()
    folder.chmod(0o755)
    return folder


def test_atelier_is_closed(client: DockerClient, tmp_path: Path) -> None:
    """Only lo, read-only root and input, noexec /work, uid 10001, no proxy, no socket, no capability, no driver"""

    container = client.containers.create(IMAGE, entrypoint=["sh", "-c", PROBE], **atelier_options(input_folder(tmp_path)))
    try:
        container.start()
        assert container.wait(timeout=60)["StatusCode"] == 0
        output = container.logs(stdout=True, stderr=False).decode()
    finally:
        container.remove(force=True)
    report = dict(line.split("=", 1) for line in output.strip().splitlines())
    assert report == {
        "net": "lo ",
        "root": "readonly",
        "work": "noexec",
        "input": "readonly",
        "uid": "10001",
        "gid": "10001",
        "proxy": "0",
        "socket": "0",
        "caps": "0000000000000000",
        "nonewprivs": "1",
        "seccomp": "2",
        "imports": "",
    }


def test_timeout_gives_gray_and_removes_the_container(client: DockerClient, tmp_path: Path) -> None:
    """A command longer than the 2 s limit gives atelier_timeout, and its container is gone"""

    recording = RecordingClient(client)
    start = time.monotonic()
    run = run_atelier(
        recording,
        input_folder(tmp_path),
        make_settings(atelier_timeout=2),
        test_entrypoint=["python", "-c", "import time; time.sleep(60)"],
    )
    assert time.monotonic() - start < 20
    assert (run.result, run.error_code) == (None, ATELIER_TIMEOUT)
    [identifier] = recording.containers.created
    with pytest.raises(NotFound):
        client.containers.get(identifier)


def test_more_than_five_megabytes_on_stdout_is_invalid(client: DockerClient, tmp_path: Path) -> None:
    """An output over 5 MB gives atelier_invalid_result, and its container is gone"""

    recording = RecordingClient(client)
    run = run_atelier(
        recording,
        input_folder(tmp_path),
        make_settings(),
        test_entrypoint=["python", "-c", "import sys; sys.stdout.write('x' * 6_000_000)"],
    )
    assert (run.result, run.error_code) == (None, ATELIER_INVALID_RESULT)
    [identifier] = recording.containers.created
    with pytest.raises(NotFound):
        client.containers.get(identifier)


@pytest.mark.parametrize(
    ("fixture", "red_rule"),
    [("postmark_like", "R05"), ("python_fastmcp_clean", None), ("rules/R11/positive", "R11")],
)
def test_end_to_end_without_network(client: DockerClient, tmp_path: Path, fixture: str, red_rule: str | None) -> None:
    """Jobs built from fixtures are analyzed by the real image: red with the right rule, or not red"""

    build_job(tmp_path / "input", ENGINE_FIXTURES / fixture)
    run = run_atelier(client, tmp_path / "input", make_settings())
    assert run.error_code is None, run.stderr
    assert run.result is not None
    rules = {alert.rule for alert in run.result.verdict.alerts}
    if red_rule is None:
        assert run.result.verdict.color is not VerdictColor.RED
    else:
        assert run.result.verdict.color is VerdictColor.RED
        assert red_rule in rules
