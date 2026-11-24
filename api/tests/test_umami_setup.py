"""Tests of scripts/umami-first-setup.sh with a fake docker and a fake curl: it refuses a dashboard outside 127.0.0.1"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from helpers import REPOSITORY

SCRIPT = REPOSITORY / "scripts" / "umami-first-setup.sh"
WEBSITE = "6cd6a0a6-8a23-40af-97ec-796ec2dda574"
TYPED = "a-typed-password-never-shown-42"
LOCAL = [{"HostIp": "127.0.0.1", "HostPort": "3200"}]
FAKE_DOCKER = """#!/bin/sh
case "$*" in
  "compose ps -q umami") echo umami-container ;;
  "compose port web 3000") echo "$FAKE_WEB" ;;
  inspect*) echo "$FAKE_PORTS" ;;
esac
"""
FAKE_CURL = """#!PYTHON
import json, os, sys
arguments = sys.argv[1:]
with open(os.environ["FAKE_CALLS"], "a", encoding="utf-8") as calls:
    calls.write(json.dumps(arguments) + "\\n")
url = next(item for item in arguments if item.startswith("http"))
if "-w" in arguments:
    if url.endswith("/api/me/password"):
        print("200", end="")
    else:
        print(os.environ.get("FAKE_RELAY_STATUS", "404"), end="")
    sys.exit(0)
if url.endswith("/api/heartbeat"):
    sys.exit(0)
if "--data-binary" in arguments:
    sys.stdin.read()
if url.endswith("/api/auth/login"):
    print(json.dumps({"token": "fake-token"}))
elif url.endswith("/api/websites") and "-X" in arguments:
    print(json.dumps({"id": "WEBSITE"}))
elif url.endswith("/api/websites"):
    print(json.dumps({"data": []}))
"""


def setup(tmp_path: Path) -> Path:
    """Copy the script into a fake repository, with a fake docker and a fake curl first on the PATH"""

    root = tmp_path / "repository"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / SCRIPT.name)
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "docker").write_text(FAKE_DOCKER, encoding="utf-8")
    (fake / "curl").write_text(FAKE_CURL.replace("PYTHON", sys.executable).replace("WEBSITE", WEBSITE), encoding="utf-8")
    for tool in ("docker", "curl"):
        (fake / tool).chmod(0o755)
    return root


def run(tmp_path: Path, ports: object, web: str = "127.0.0.1:3000", relay: str = "404") -> tuple[int, str, list[list[str]]]:
    """Run the script with a typed password; return its exit code, its whole output and every curl command line"""

    root = setup(tmp_path)
    calls = tmp_path / "calls"
    environment = {
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "FAKE_PORTS": json.dumps(ports),
        "FAKE_WEB": web,
        "FAKE_RELAY_STATUS": relay,
        "FAKE_CALLS": str(calls),
    }
    done = subprocess.run(
        ["sh", str(root / "scripts" / SCRIPT.name), "mcplain.example.com"],
        input=f"{TYPED}\n{TYPED}\n",
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = []
    if calls.exists():
        lines = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
    return done.returncode, done.stdout + done.stderr, lines


@pytest.mark.parametrize(
    "ports",
    [
        {"3000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "3200"}]},
        {"3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3200"}, {"HostIp": "::", "HostPort": "3200"}]},
        {"3000/tcp": None},
        {},
    ],
)
def test_a_dashboard_published_elsewhere_than_localhost_stops_everything(tmp_path: Path, ports: object) -> None:
    """Any binding outside 127.0.0.1, or none, stops the script before any call to Umami"""

    code, output, calls = run(tmp_path, ports)
    assert code == 1
    assert "elsewhere than on 127.0.0.1" in output
    assert calls == []


def test_a_website_on_another_address_or_a_relay_that_lets_umami_through_stops_everything(tmp_path: Path) -> None:
    """The website must be on 127.0.0.1, and every hidden path under /umami must be 404"""

    code, output, calls = run(tmp_path, {"3000/tcp": LOCAL}, web="0.0.0.0:3000")
    assert (code, calls) == (1, [])
    assert "website is published elsewhere" in output
    code, output, calls = run(tmp_path / "second", {"3000/tcp": LOCAL}, relay="200")
    assert code == 1
    assert "lets /umami/api/auth/login through" in output
    assert all("/api/me/password" not in " ".join(line) for line in calls)


def test_the_password_is_changed_without_ever_being_on_a_command_line_nor_in_env(tmp_path: Path) -> None:
    """The typed password reaches curl by a file or the input only; the public id of the website is written in .env"""

    code, output, calls = run(tmp_path, {"3000/tcp": LOCAL})
    assert code == 0, output
    assert TYPED not in output
    assert all(TYPED not in argument for line in calls for argument in line)
    assert all("fake-token" not in argument for line in calls for argument in line)
    assert any("http://127.0.0.1:3200/api/me/password" in line for line in calls)
    env_file = (tmp_path / "repository" / ".env").read_text(encoding="utf-8")
    assert env_file == f"MCPLAIN_UMAMI_WEBSITE_ID={WEBSITE}\n"
    assert not list((tmp_path / "repository").glob(".env.*"))
