"""Technical inspection of the atelier options, and the launcher logic with a fake Docker client"""

import copy
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import requests
from docker.errors import APIError, ImageNotFound
from docker.types import LogConfig, Mount, Ulimit
from helpers import ENGINE_FIXTURES, make_settings
from mcplain.analyze import analyze_directory
from mcplain.lamps import LAMP_ORDER

from mcplain_api import launcher
from mcplain_api.launcher import (
    ATELIER_ERROR,
    ATELIER_INVALID_RESULT,
    ATELIER_TIMEOUT,
    AtelierRun,
    atelier_options,
    remove_orphans,
    run_atelier,
)

INPUT = Path("/srv/mcplain/jobs/1234/input")
DISPATCHER = "main"
FORBIDDEN_KEYS: tuple[str, ...] = ("privileged", "devices", "cap_add", "volumes", "volumes_from", "device_requests")
SOCKET = "/var/run/docker.sock"


def expected_options(input_dir: Path) -> dict[str, Any]:
    """Return, written out by hand, the only options an atelier may have"""

    return {
        "network_mode": "none",
        "read_only": True,
        "tmpfs": {
            "/work": "rw,noexec,nosuid,nodev,size=256m",
            "/tmp": "rw,noexec,nosuid,nodev,size=16m",
        },
        "user": "10001:10001",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
        "pids_limit": 64,
        "mem_limit": "1g",
        "memswap_limit": "1g",
        "nano_cpus": 1_000_000_000,
        "ulimits": [Ulimit(name="nofile", soft=256, hard=256)],
        "environment": {},
        "use_config_proxy": False,
        "mounts": [Mount(target="/job/input", source=str(input_dir), type="bind", read_only=True)],
        "log_config": LogConfig(type="json-file", config={"max-size": "5m", "max-file": "1"}),
        "labels": {"mcplain.role": "atelier", "mcplain.dispatcher": DISPATCHER},
    }


def inspect_options(options: dict[str, Any], input_dir: Path) -> None:
    """Fail unless the options are exactly the hardened ones, with no way around the sandbox"""

    for key in FORBIDDEN_KEYS:
        assert key not in options, key
    for option in options.get("security_opt", []):
        assert "unconfined" not in option, option
    for mount in options.get("mounts", []):
        assert SOCKET not in str(mount.get("Source", "")), mount
        assert mount.get("ReadOnly") is True, mount
    assert options == expected_options(input_dir)


def test_atelier_options_pass_the_technical_inspection() -> None:
    """atelier_options gives exactly the expected options, nothing more, nothing less"""

    inspect_options(atelier_options(INPUT, DISPATCHER), INPUT)


def _without(key: str) -> Callable[[dict[str, Any]], None]:
    """Return a change that removes one option"""

    def change(options: dict[str, Any]) -> None:
        """Remove the option"""

        del options[key]

    return change


def _setting(key: str, value: object) -> Callable[[dict[str, Any]], None]:
    """Return a change that sets one option"""

    def change(options: dict[str, Any]) -> None:
        """Set the option"""

        options[key] = value

    return change


def _added(key: str, value: object) -> Callable[[dict[str, Any]], None]:
    """Return a change that appends a value to a list option"""

    def change(options: dict[str, Any]) -> None:
        """Append the value"""

        options[key] = [*options[key], value]

    return change


def _writable_input(options: dict[str, Any]) -> None:
    """Make the job folder writable"""

    options["mounts"] = [Mount(target="/job/input", source=str(INPUT), type="bind", read_only=False)]


def _executable_work(options: dict[str, Any]) -> None:
    """Allow running files written in /work"""

    options["tmpfs"] = {**options["tmpfs"], "/work": "rw,nosuid,nodev,size=256m"}


WEAKENINGS: dict[str, Callable[[dict[str, Any]], None]] = {
    **{f"without {key}": _without(key) for key in expected_options(INPUT)},
    "bridge network": _setting("network_mode", "bridge"),
    "writable root": _setting("read_only", False),
    "executable work": _executable_work,
    "root user": _setting("user", "0:0"),
    "capabilities kept": _setting("cap_drop", []),
    "new privileges allowed": _setting("security_opt", []),
    "more processes": _setting("pids_limit", 4096),
    "more memory": _setting("mem_limit", "8g"),
    "swap allowed": _setting("memswap_limit", "-1"),
    "more cpu": _setting("nano_cpus", 4_000_000_000),
    "more files": _setting("ulimits", [Ulimit(name="nofile", soft=65536, hard=65536)]),
    "token given": _setting("environment", {"GITHUB_TOKEN": "secret"}),
    "proxy from config": _setting("use_config_proxy", True),
    "writable input": _writable_input,
    "other log driver": _setting("log_config", LogConfig(type="local")),
    "no label": _setting("labels", {}),
    "no dispatcher label": _setting("labels", {"mcplain.role": "atelier"}),
    "docker socket": _added("mounts", Mount(target=SOCKET, source=SOCKET, type="bind", read_only=True)),
    "device": _setting("devices", ["/dev/kvm:/dev/kvm:rwm"]),
    "privileged": _setting("privileged", True),
    "added capability": _setting("cap_add", ["SYS_ADMIN"]),
    "apparmor unconfined": _added("security_opt", "apparmor=unconfined"),
    "seccomp unconfined": _added("security_opt", "seccomp=unconfined"),
    "socket as volume": _setting("volumes", {SOCKET: {"bind": SOCKET, "mode": "ro"}}),
}


@pytest.mark.parametrize("name", list(WEAKENINGS))
def test_any_weakening_fails_the_inspection(name: str) -> None:
    """Removing or weakening one option, or adding a way out, makes the inspection fail"""

    options = copy.deepcopy(atelier_options(INPUT, DISPATCHER))
    WEAKENINGS[name](options)
    with pytest.raises(AssertionError):
        inspect_options(options, INPUT)


class FakeContainer:
    """Class that imitates a Docker container whose behavior is set by the test"""

    def __init__(
        self,
        stdout: bytes = b"",
        stderr: bytes = b"",
        exit_code: int = 0,
        times_out: bool = False,
        start_error: Exception | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Remember the planned behavior"""

        self.id = "fake"
        self.labels = labels or {}
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.times_out = times_out
        self.start_error = start_error
        self.status = "created"
        self.killed = False
        self.removed = False

    def start(self) -> None:
        """Start, or fail as planned"""

        if self.start_error is not None:
            raise self.start_error
        self.status = "running"

    def wait(self, timeout: int) -> dict[str, int]:
        """Return the exit code, or time out as planned"""

        if self.times_out:
            raise requests.exceptions.ReadTimeout("read timed out")
        self.status = "exited"
        return {"StatusCode": self.exit_code}

    def reload(self) -> None:
        """Keep the current status"""

    def kill(self) -> None:
        """Stop the container"""

        self.killed = True
        self.status = "exited"

    def logs(self, stdout: bool, stderr: bool, stream: bool, follow: bool) -> Iterator[bytes]:
        """Yield one output stream in chunks"""

        data = self.stderr
        if stdout:
            data = self.stdout
        for index in range(0, len(data), 65536):
            yield data[index : index + 65536]

    def remove(self, force: bool) -> None:
        """Remember the removal"""

        self.removed = True


def has_labels(container: FakeContainer, labels: list[str]) -> bool:
    """Tell whether a container carries every key=value label"""

    pairs = [label.split("=", 1) for label in labels]
    return all(container.labels.get(key) == value for key, value in pairs)


class FakeContainers:
    """Class that imitates client.containers"""

    def __init__(self, container: FakeContainer | None, error: Exception | None = None) -> None:
        """Remember the container to give back"""

        self.container = container
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.listed: list[FakeContainer] = []
        self.filters: dict[str, list[str]] | None = None

    def create(self, image: str, **options: Any) -> FakeContainer:
        """Record the call and return the planned container"""

        self.calls.append((image, options))
        if self.error is not None:
            raise self.error
        assert self.container is not None
        return self.container

    def list(self, all: bool, filters: dict[str, list[str]]) -> list[FakeContainer]:
        """Return the planned leftover containers that carry every label of the filter, as Docker does"""

        self.filters = filters
        return [item for item in self.listed if has_labels(item, filters["label"])]


class FakeClient:
    """Class that imitates a DockerClient"""

    def __init__(self, container: FakeContainer | None, error: Exception | None = None) -> None:
        """Hold the fake containers collection"""

        self.containers = FakeContainers(container, error)


def result_line(fixtures: Path) -> bytes:
    """Return a real AnalysisResult as one JSON line, as the atelier prints it"""

    result = analyze_directory(fixtures / "python_fastmcp_clean")
    return result.model_dump_json().encode() + b"\n"


@pytest.fixture
def engine_fixtures() -> Path:
    """Return the fixture folder of the engine"""

    return ENGINE_FIXTURES


def test_valid_result_is_returned_and_the_container_removed(engine_fixtures: Path) -> None:
    """A valid line gives the result; the container is created with the atelier options only, then removed"""

    container = FakeContainer(stdout=result_line(engine_fixtures))
    client = FakeClient(container)
    run = run_atelier(client, INPUT, make_settings())
    assert run.result is not None and run.error_code is None
    assert client.containers.calls == [("mcplain-atelier:dev", atelier_options(INPUT, DISPATCHER))]
    assert container.removed


def test_timeout_kills_and_gives_gray() -> None:
    """A container still running after the time limit is killed, removed, and gives atelier_timeout"""

    container = FakeContainer(times_out=True)
    run = run_atelier(FakeClient(container), INPUT, make_settings(atelier_timeout=2))
    assert (run.result, run.error_code) == (None, ATELIER_TIMEOUT)
    assert container.killed and container.removed


def test_non_zero_exit_gives_atelier_error() -> None:
    """A container that fails without a result gives atelier_error"""

    container = FakeContainer(exit_code=1, stderr=b"boom")
    run = run_atelier(FakeClient(container), INPUT, make_settings())
    assert (run.result, run.error_code, run.stderr, run.exit_code) == (None, ATELIER_ERROR, "boom", 1)
    assert container.removed


@pytest.mark.parametrize(
    "stdout",
    [b"", b"not json\n", b'{"status": "ok"}\n', b"x" * (launcher.MAX_STDOUT_BYTES + 1)],
    ids=["empty", "text", "incomplete", "too_long"],
)
def test_unreadable_output_gives_invalid_result(stdout: bytes) -> None:
    """Empty, invalid, incomplete or too long output gives atelier_invalid_result"""

    container = FakeContainer(stdout=stdout)
    run = run_atelier(FakeClient(container), INPUT, make_settings())
    assert (run.result, run.error_code) == (None, ATELIER_INVALID_RESULT)
    assert container.removed


def run_with(result: dict[str, Any]) -> AtelierRun:
    """Run a fake atelier that prints a result given as a mapping"""

    container = FakeContainer(stdout=json.dumps(result).encode() + b"\n")
    return run_atelier(FakeClient(container), INPUT, make_settings())


def fixture_result(fixtures: Path, name: str) -> dict[str, Any]:
    """Return the real result of an engine fixture as a mapping"""

    return analyze_directory(fixtures / name).model_dump(mode="json")


def test_lamps_level_and_domains_pass_through(engine_fixtures: Path) -> None:
    """The lamps of the server and of each tool, the tool levels and the fixed domains are kept as the engine set them"""

    result = fixture_result(engine_fixtures, "postmark_like")
    run = run_with(result)
    assert run.error_code is None and run.result is not None
    assert run.result.model_dump(mode="json") == result
    server = run.result.servers[0]
    assert [lamp.id.value for lamp in server.lamps] == [lamp.value for lamp in LAMP_ORDER]
    assert {tool.level.value for tool in server.tools} <= {"none", "warn", "danger"}


@pytest.mark.parametrize(
    "damage",
    [
        "server_without_lamps",
        "tool_without_lamps",
        "five_lamps",
        "unknown_lamp",
        "unknown_state",
        "unknown_level",
        "domains_not_a_list",
    ],
)
def test_output_without_complete_lamps_gives_invalid_result(engine_fixtures: Path, damage: str) -> None:
    """A result whose lamps, levels or domains are missing or malformed is refused, so the analysis turns gray"""

    result = fixture_result(engine_fixtures, "python_filesystem")
    server = result["servers"][0]
    tool = server["tools"][0]
    if damage == "server_without_lamps":
        del server["lamps"]
    elif damage == "tool_without_lamps":
        tool["lamps"] = []
    elif damage == "five_lamps":
        server["lamps"] = server["lamps"][:5]
    elif damage == "unknown_lamp":
        server["lamps"][5]["id"] = "camera"
    elif damage == "unknown_state":
        tool["lamps"][0]["state"] = "blinking"
    elif damage == "unknown_level":
        tool["level"] = "maybe"
    else:
        server["internet_domains"] = "example.com"
    run = run_with(result)
    assert (run.result, run.error_code) == (None, ATELIER_INVALID_RESULT)


def test_two_lines_are_refused(engine_fixtures: Path) -> None:
    """Anything after the result line makes the output invalid"""

    line = result_line(engine_fixtures)
    container = FakeContainer(stdout=line + json.dumps({"extra": 1}).encode())
    run = run_atelier(FakeClient(container), INPUT, make_settings())
    assert run.error_code == ATELIER_INVALID_RESULT


def test_stderr_is_cut_to_two_thousand_characters() -> None:
    """Only the start of the error output is kept for the log"""

    container = FakeContainer(exit_code=1, stderr=b"e" * 50_000)
    run = run_atelier(FakeClient(container), INPUT, make_settings())
    assert run.stderr == "e" * 2000


def test_missing_image_gives_atelier_error() -> None:
    """A Docker error at creation gives atelier_error"""

    client = FakeClient(None, ImageNotFound("no such image"))
    run = run_atelier(client, INPUT, make_settings())
    assert (run.result, run.error_code) == (None, ATELIER_ERROR)


def test_start_error_still_removes_the_container() -> None:
    """A Docker error at start gives atelier_error and the container is removed"""

    container = FakeContainer(start_error=APIError("cannot start"))
    run = run_atelier(FakeClient(container), INPUT, make_settings())
    assert run.error_code == ATELIER_ERROR
    assert container.removed


def test_test_entrypoint_is_the_only_extra_option() -> None:
    """The test command replaces the entry point and changes nothing else"""

    client = FakeClient(FakeContainer(exit_code=1))
    run_atelier(client, INPUT, make_settings(), test_entrypoint=["sleep", "1"])
    [(_, options)] = client.containers.calls
    assert options == {**atelier_options(INPUT, DISPATCHER), "entrypoint": ["sleep", "1"]}


def test_orphans_of_this_dispatcher_only_are_removed() -> None:
    """At startup a dispatcher removes its own leftover ateliers, never those of another dispatcher"""

    client = FakeClient(None)
    ours = [FakeContainer(labels={"mcplain.role": "atelier", "mcplain.dispatcher": "main"}) for _ in range(2)]
    other = FakeContainer(labels={"mcplain.role": "atelier", "mcplain.dispatcher": "blue"})
    unlabeled = FakeContainer(labels={"mcplain.role": "atelier"})
    stranger = FakeContainer(labels={"mcplain.dispatcher": "main"})
    client.containers.listed = [*ours, other, unlabeled, stranger]
    assert remove_orphans(client, "main") == 2
    assert client.containers.filters == {"label": ["mcplain.role=atelier", "mcplain.dispatcher=main"]}
    assert all(container.removed for container in ours)
    assert not any(container.removed for container in (other, unlabeled, stranger))


def test_ateliers_carry_the_dispatcher_identifier() -> None:
    """run_atelier labels each atelier with the MCPLAIN_DISPATCHER_ID of its dispatcher"""

    client = FakeClient(FakeContainer(exit_code=1))
    run_atelier(client, INPUT, make_settings(dispatcher_id="blue"))
    [(_, options)] = client.containers.calls
    assert options["labels"] == {"mcplain.role": "atelier", "mcplain.dispatcher": "blue"}
