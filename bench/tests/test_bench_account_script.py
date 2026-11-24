"""Tests of scripts/make-bench-account.sh: the address and the password of the CI never make an account outside GitHub Actions"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "make-bench-account.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "bench.yml"
CI_EMAIL = "bench@bench.mcplain.invalid"
CI_PASSWORD = "test-only-bench-account-password-0123456789"
FAKE_DOCKER = "#!/bin/sh\necho called >> \"$(dirname \"$0\")/calls\"\nexit 1\n"


def run(tmp_path: Path, email: str, password: str, github_actions: str | None) -> tuple[int, str, bool]:
    """Run the script with a fake docker on the PATH; return the exit code, the error output and whether docker was called"""

    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    docker = fake / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(0o755)
    environment = {
        "PATH": f"{fake}:{os.environ['PATH']}",
        "MCPLAIN_BENCH_EMAIL": email,
        "MCPLAIN_BENCH_PASSWORD": password,
    }
    if github_actions is not None:
        environment["GITHUB_ACTIONS"] = github_actions
    done = subprocess.run([str(SCRIPT)], env=environment, capture_output=True, text=True, check=False, cwd=tmp_path)
    return done.returncode, done.stderr, (fake / "calls").exists()


def test_the_ci_values_are_the_ones_written_in_the_workflow() -> None:
    """The values this guard refuses are exactly the public ones of bench.yml"""

    text = WORKFLOW.read_text(encoding="utf-8")
    assert f"MCPLAIN_BENCH_EMAIL={CI_EMAIL}" in text
    assert f"MCPLAIN_BENCH_PASSWORD={CI_PASSWORD}" in text


@pytest.mark.parametrize(
    ("email", "password"),
    [
        (CI_EMAIL, CI_PASSWORD),
        (CI_EMAIL, "a private password of this machine"),
        ("bench-1234abcd@bench.mcplain.invalid", CI_PASSWORD),
        ("bench-1234abcd@bench.mcplain.invalid", "some-test-only-value"),
    ],
)
def test_outside_github_actions_the_ci_values_are_refused_before_any_docker_call(tmp_path: Path, email: str, password: str) -> None:
    """Outside GitHub Actions, the CI address or a test-only password stops the script at once, without touching the stack"""

    for github_actions in (None, "", "false", "1"):
        code, error, called = run(tmp_path, email, password, github_actions)
        assert code == 2, error
        assert "init-secrets.sh" in error
        assert password not in error
        assert not called


def test_in_github_actions_or_with_the_values_of_this_machine_the_script_goes_on(tmp_path: Path) -> None:
    """In GitHub Actions the CI values pass the guard; on a machine, its own values pass it; both then reach docker"""

    assert run(tmp_path, CI_EMAIL, CI_PASSWORD, "true")[2]
    (tmp_path / "bin" / "calls").unlink()
    assert run(tmp_path, "bench-1234abcd@bench.mcplain.invalid", "a private password of this machine", None)[2]
