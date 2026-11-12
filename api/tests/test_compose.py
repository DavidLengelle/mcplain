"""Tests on the running compose stack: docker compose build atelier, then docker compose up -d --build"""

import json
import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import docker
import httpx
import pytest
from docker import DockerClient
from docker.models.containers import Container

pytestmark = pytest.mark.docker

REPOSITORY = Path(__file__).resolve().parents[2]
WEB_PORT_VARIABLE = "MCPLAIN_WEB_PORT"
DEFAULT_WEB_PORT = "3000"
MAILPIT_PORT_VARIABLE = "MCPLAIN_MAILPIT_PORT"
DEFAULT_MAILPIT_PORT = "8025"
MAIL_WAIT_SECONDS = 60
FETCH_INPUT = "uvx mcp-server-fetch==2026.11.11"
FILESYSTEM_INPUT = "npx -y @modelcontextprotocol/server-filesystem@2.3.0"


def compose_port(variable: str, default: str) -> str:
    """Return a host port as compose reads it: environment, then .env, then the default"""

    value = os.environ.get(variable)
    if value:
        return value
    env_file = REPOSITORY / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, _, setting = line.partition("=")
            if name.strip() == variable and setting.strip():
                return setting.strip()
    return default


def web_port() -> str:
    """Return the host port of the website, as compose reads it: environment, then .env, then 3000"""

    return compose_port(WEB_PORT_VARIABLE, DEFAULT_WEB_PORT)

API_URL = os.environ.get("MCPLAIN_API_URL", "http://127.0.0.1:8000")
PROJECT = "mcplain"
FINISHED: frozenset[str] = frozenset({"done", "failed", "quota_exhausted"})
ANALYSIS_TIMEOUT = 300
CLAIM_COUNT = 300
CLAIM_SCRIPT = f"""
import json
import threading
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from mcplain_api.db import Analysis, Base, make_engine, make_sessions
from mcplain_api.dispatcher import Dispatcher
from mcplain_api.settings import Settings

settings = Settings()
url = make_url(settings.database_url)
name = "mcplain_claims_" + uuid.uuid4().hex[:12]
admin = create_engine(url, isolation_level="AUTOCOMMIT")
with admin.connect() as connection:
    connection.execute(text('CREATE DATABASE "' + name + '"'))
test_url = url.set(database=name).render_as_string(hide_password=False)
try:
    setup = make_engine(test_url)
    Base.metadata.create_all(setup)
    with make_sessions(setup).begin() as session:
        session.add_all([Analysis(input_raw="npx demo-" + str(index), state="queued") for index in range({CLAIM_COUNT})])
    setup.dispose()
    claimed = [[], []]
    barrier = threading.Barrier(2)

    def work(index):
        engine = make_engine(test_url)
        dispatcher = Dispatcher(settings, make_sessions(engine), None)
        barrier.wait()
        while True:
            item = dispatcher.claim()
            if item is None:
                break
            claimed[index].append(str(item.id))
        engine.dispose()

    threads = [threading.Thread(target=work, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    print(json.dumps(claimed))
finally:
    with admin.connect() as connection:
        connection.execute(text('DROP DATABASE IF EXISTS "' + name + '" WITH (FORCE)'))
    admin.dispose()
"""

LOCK_SCRIPT = """
import json
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from mcplain_api.db import AiText, Base, make_engine, make_sessions
from mcplain_api.redacteur import claim_waiting
from mcplain_api.settings import Settings

url = make_url(Settings().database_url)
name = "mcplain_ai_lock_" + uuid.uuid4().hex[:12]
admin = create_engine(url, isolation_level="AUTOCOMMIT")
with admin.connect() as connection:
    connection.execute(text('CREATE DATABASE "' + name + '"'))
try:
    engine = make_engine(url.set(database=name).render_as_string(hide_password=False))
    Base.metadata.create_all(engine)
    sessions = make_sessions(engine)
    with sessions.begin() as session:
        session.add(AiText(kind="notice", lang="fr", hash="0" * 64, prompt_version="v", model="m", status="pending"))
    with sessions.begin() as first:
        held = claim_waiting(first)
        with sessions.begin() as second:
            skipped = claim_waiting(second)
    print(json.dumps([held is not None, skipped is None]))
    engine.dispose()
finally:
    with admin.connect() as connection:
        connection.execute(text('DROP DATABASE IF EXISTS "' + name + '" WITH (FORCE)'))
    admin.dispose()
"""

REACH_SCRIPT = """
const net = require("node:net");
const targets = JSON.parse(process.argv[1]);
const REACHED = new Set(["ECONNREFUSED", "ECONNRESET"]);

function probe(host, port) {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port, timeout: 3000 });
    socket.on("connect", () => { socket.destroy(); resolve("reachable"); });
    socket.on("timeout", () => { socket.destroy(); resolve("unreachable"); });
    socket.on("error", (error) => {
      if (REACHED.has(error.code)) { resolve("reachable"); } else { resolve("unreachable"); }
    });
  });
}

async function main() {
  const report = {};
  const health = await fetch("http://api:8000/api/health").catch(() => null);
  report.api = 0;
  if (health !== null) { report.api = health.status; }
  for (const [name, host, port] of targets) { report[name] = await probe(host, port); }
  console.log(JSON.stringify(report));
}

main();
"""


@pytest.fixture
def client() -> Iterator[DockerClient]:
    """Return a Docker client"""

    docker_client = docker.from_env()
    yield docker_client
    docker_client.close()


@pytest.fixture
def http() -> Iterator[httpx.Client]:
    """Return an HTTP client of the API published by compose on 127.0.0.1:8000"""

    with httpx.Client(base_url=API_URL, timeout=30) as http_client:
        try:
            health = http_client.get("/api/health")
        except httpx.HTTPError:
            pytest.fail("start the stack first: docker compose up -d --build")
        assert health.json() == {"status": "ok"}
        yield http_client


def compose_container(client: DockerClient, service: str) -> Container:
    """Return the running container of one compose service"""

    containers = client.containers.list(
        filters={"label": [f"com.docker.compose.project={PROJECT}", f"com.docker.compose.service={service}"]}
    )
    if not containers:
        pytest.fail("start the stack first: docker compose up -d --build")
    return containers[0]


def solved_altcha(http: httpx.Client) -> str:
    """Ask the API for an ALTCHA challenge and solve it as the widget of a browser would"""

    from altcha import Challenge, Payload, solve_challenge

    challenge = Challenge.from_dict(http.get("/api/altcha/challenge").json())
    solution = solve_challenge(challenge)
    assert solution is not None
    return Payload(challenge, solution).to_base64()


def reset_counters() -> None:
    """Empty the quotas and the burst counts as the owner of the database, never through the API: tests only"""

    postgres_lines(docker.from_env(), "DELETE FROM quota_usage; DELETE FROM burst_counts; DELETE FROM analysis_tokens;")


def analyze(http: httpx.Client, text: str) -> dict[str, Any]:
    """Ask the API for an analysis with a solved ALTCHA, the counters reset first, and poll it until it is finished"""

    reset_counters()
    response = http.post("/api/analyses", json={"input": text}, headers={"x-altcha": solved_altcha(http)})
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    deadline = time.monotonic() + ANALYSIS_TIMEOUT
    while time.monotonic() < deadline:
        body = http.get(f"/api/analyses/{identifier}").json()
        if body["state"] in FINISHED:
            return body
        time.sleep(0.5)
    pytest.fail(f"analysis {identifier} did not finish")


def test_two_dispatchers_never_claim_the_same_analysis(client: DockerClient) -> None:
    """Two dispatchers claiming at the same time on the compose PostgreSQL never take the same analysis"""

    api = compose_container(client, "api")
    exit_code, (stdout, stderr) = api.exec_run(["python", "-c", CLAIM_SCRIPT], demux=True)
    assert exit_code == 0, stderr
    first, second = json.loads(stdout)
    assert set(first).isdisjoint(second)
    assert len(first) + len(second) == CLAIM_COUNT
    assert len(set(first) | set(second)) == CLAIM_COUNT
    assert first and second


def test_a_second_writer_skips_the_text_being_written(client: DockerClient) -> None:
    """On the compose PostgreSQL, a text held by one writer is invisible to another: ten visitors make one call"""

    api = compose_container(client, "api")
    exit_code, (stdout, stderr) = api.exec_run(["python", "-c", LOCK_SCRIPT], demux=True)
    assert exit_code == 0, stderr
    assert json.loads(stdout) == [True, True]


def test_the_writer_container_is_closed(client: DockerClient) -> None:
    """The writer runs on the back network only, read-only, not root, without any mount; no other service has the key"""

    writer = compose_container(client, "redacteur")
    attrs = writer.attrs
    assert [name.split("_")[-1] for name in attrs["NetworkSettings"]["Networks"]] == ["back"]
    assert attrs["HostConfig"]["ReadonlyRootfs"] is True
    assert attrs["HostConfig"]["CapDrop"] == ["ALL"]
    assert attrs["Config"]["User"] == "10002:10002"
    assert attrs["Mounts"] == [] or all(mount["Type"] == "tmpfs" for mount in attrs["Mounts"])
    assert not attrs["HostConfig"]["PortBindings"]
    assert "no-new-privileges:true" in attrs["HostConfig"]["SecurityOpt"]
    for service in ("api", "dispatcher", "web", "postgres"):
        environment = compose_container(client, service).attrs["Config"]["Env"]
        assert not [item for item in environment if "ANTHROPIC" in item.upper()], service


def network_address(container: Container, suffix: str) -> str:
    """Return the IP address of a container on the compose network whose name ends with suffix"""

    for name, settings in container.attrs["NetworkSettings"]["Networks"].items():
        if name.endswith(suffix):
            return settings["IPAddress"]
    pytest.fail(f"{container.name} is not on the {suffix} network")


def test_web_reaches_the_api_and_nothing_behind_it(client: DockerClient) -> None:
    """From the web container the API answers; PostgreSQL and the dispatcher cannot be reached, by name or address"""

    web = compose_container(client, "web")
    postgres = compose_container(client, "postgres")
    dispatcher = compose_container(client, "dispatcher")
    targets = [
        ["postgres_by_name", "postgres", 5432],
        ["postgres_by_address", network_address(postgres, "_back"), 5432],
        ["dispatcher_by_name", "dispatcher", 1],
        ["dispatcher_by_address", network_address(dispatcher, "_back"), 1],
        ["api_port", "api", 8000],
    ]
    exit_code, (stdout, stderr) = web.exec_run(["node", "-e", REACH_SCRIPT, json.dumps(targets)], demux=True)
    assert exit_code == 0, stderr
    assert json.loads(stdout) == {
        "api": 200,
        "api_port": "reachable",
        "postgres_by_name": "unreachable",
        "postgres_by_address": "unreachable",
        "dispatcher_by_name": "unreachable",
        "dispatcher_by_address": "unreachable",
    }


def test_web_container_is_closed(client: DockerClient) -> None:
    """The web container is only on the front network, read-only, not root, and without the Docker socket"""

    web = compose_container(client, "web")
    attrs = web.attrs
    assert [name.split("_")[-1] for name in attrs["NetworkSettings"]["Networks"]] == ["front"]
    assert attrs["HostConfig"]["ReadonlyRootfs"] is True
    assert attrs["HostConfig"]["CapDrop"] == ["ALL"]
    assert attrs["Config"]["User"] == "10003:10003"
    assert all("docker.sock" not in mount["Source"] for mount in attrs["Mounts"])
    assert attrs["HostConfig"]["PortBindings"] == {"3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": web_port()}]}


@pytest.mark.network
def test_fetch_server_is_orange_with_its_request_of_stream_get(http: httpx.Client) -> None:
    """mcp-server-fetch 2026.11.11 is orange with O01, O04 and O08; O01 cites the request of stream_get, reached by either path"""

    body = analyze(http, FETCH_INPUT)
    assert body["state"] == "done", body
    verdict = body["result"]["verdict"]
    assert verdict["color"] == "orange"
    assert {alert["rule"] for alert in verdict["alerts"]} == {"O01", "O04", "O08"}
    open_network = [alert for alert in verdict["alerts"] if alert["rule"] == "O01"]
    assert open_network[0]["function"] == "stream_get"
    assert open_network[0]["steps"][0]["function"] in {"fetch_url", "check_may_autonomously_fetch_url"}


@pytest.mark.network
def test_filesystem_server_is_orange_with_o08(http: httpx.Client) -> None:
    """@modelcontextprotocol/server-filesystem 2.3.0 is orange with O08"""

    body = analyze(http, FILESYSTEM_INPUT)
    assert body["state"] == "done", body
    verdict = body["result"]["verdict"]
    assert verdict["color"] == "orange"
    assert "O08" in {alert["rule"] for alert in verdict["alerts"]}


@pytest.mark.network
def test_second_request_is_served_from_the_cache(http: httpx.Client, client: DockerClient) -> None:
    """The second request for the same package starts no atelier and is served from the cache"""

    first = analyze(http, FILESYSTEM_INPUT)
    start = time.time()
    second = analyze(http, FILESYSTEM_INPUT)
    end = time.time()
    assert second["state"] == "done"
    assert second["result"]["verdict"] == first["result"]["verdict"]
    assert second["result"]["source"] == first["result"]["source"]
    created = list(
        client.events(
            since=int(start),
            until=int(end) + 1,
            filters={"type": "container", "event": "create", "label": "mcplain.role=atelier"},
            decode=True,
        )
    )
    assert created == []
    logs = compose_container(client, "dispatcher").logs(since=int(start) - 1).decode("utf-8", errors="replace")
    assert f"analysis {second['id']}: served from the cache" in logs


def test_the_counter_and_the_postman_are_closed(client: DockerClient) -> None:
    """Counter, postman and Mailpit: read-only, no capability, not root, no socket, their networks, and no foreign secret"""

    expected = {"guichet": ["back", "front"], "facteur": ["back"], "mailpit": ["back"]}
    for service, networks in expected.items():
        attrs = compose_container(client, service).attrs
        assert sorted(name.split("_")[-1] for name in attrs["NetworkSettings"]["Networks"]) == networks, service
        assert attrs["HostConfig"]["ReadonlyRootfs"] is True, service
        assert attrs["HostConfig"]["CapDrop"] == ["ALL"], service
        assert "no-new-privileges:true" in attrs["HostConfig"]["SecurityOpt"], service
        assert attrs["Config"]["User"] not in ("", "0", "root"), service
        assert all("docker.sock" not in mount.get("Source", "") for mount in attrs["Mounts"]), service
    secrets = {"BETTER_AUTH_SECRET": "guichet", "MCPLAIN_ALTCHA_HMAC_KEY": "api", "MCPLAIN_SMTP_PASSWORD": "facteur"}
    for service in ("api", "dispatcher", "redacteur", "web", "guichet", "facteur", "postgres"):
        names = {item.split("=", 1)[0] for item in compose_container(client, service).attrs["Config"]["Env"]}
        for secret, owner in secrets.items():
            assert (secret in names) == (service == owner), (service, secret)
    mailpit = compose_container(client, "mailpit").attrs["HostConfig"]["PortBindings"]
    assert all(binding["HostIp"] == "127.0.0.1" for bindings in mailpit.values() for binding in bindings)


def sign_up_through_the_site(email: str, fake_address: str) -> int:
    """Ask the site for a sign-up with a solved ALTCHA and a fake X-Forwarded-For, as a browser could"""

    from altcha import Challenge, Payload, solve_challenge

    base = f"http://localhost:{web_port()}"
    with httpx.Client(base_url=base, timeout=30) as site:
        challenge = Challenge.from_dict(site.get("/api/altcha/challenge").json())
        solution = solve_challenge(challenge)
        assert solution is not None
        response = site.post(
            "/api/auth/sign-up/email",
            json={"email": email, "password": "test only password 0123", "name": ""},
            headers={
                "Origin": base,
                "x-altcha": Payload(challenge, solution).to_base64(),
                "X-Forwarded-For": fake_address,
                "x-mcplain-lang": "en",
            },
        )
    return response.status_code


def postgres_lines(client: DockerClient, statement: str) -> list[str]:
    """Run one statement as the owner of the database, inside the PostgreSQL container"""

    exit_code, (stdout, stderr) = compose_container(client, "postgres").exec_run(
        ["psql", "-U", "mcplain", "-d", "mcplain", "-At", "-c", statement], demux=True
    )
    assert exit_code == 0, stderr
    return (stdout or b"").decode("utf-8").splitlines()


def mail_ids(mailpit: httpx.Client, email: str) -> list[str]:
    """Return the ids of the Mailpit messages sent to one address"""

    found = mailpit.get("/api/v1/search", params={"query": f'to:"{email}"', "limit": "200"})
    found.raise_for_status()
    return [message["ID"] for message in found.json()["messages"]]


def clear_mails(client: DockerClient, emails: list[str]) -> None:
    """Wait until the postman has sent the mails of these addresses, then delete them in Mailpit through its API"""

    if not emails:
        return
    quoted = ", ".join("'" + email.replace("'", "''") + "'" for email in emails)
    deadline = time.monotonic() + MAIL_WAIT_SECONDS
    while postgres_lines(client, f"SELECT count(*) FROM mail_outbox WHERE recipient IN ({quoted});") != ["0"]:
        assert time.monotonic() < deadline, "the postman did not send the mails of the test"
        time.sleep(0.5)
    address = f"http://127.0.0.1:{compose_port(MAILPIT_PORT_VARIABLE, DEFAULT_MAILPIT_PORT)}"
    with httpx.Client(base_url=address, timeout=30, trust_env=False) as mailpit:
        for email in emails:
            identifiers = mail_ids(mailpit, email)
            if identifiers:
                mailpit.request("DELETE", "/api/v1/messages", json={"IDs": identifiers}).raise_for_status()
            assert mail_ids(mailpit, email) == []


def test_a_fake_forwarded_for_from_the_browser_does_not_change_the_counted_network(client: DockerClient) -> None:
    """Two sign-ups with two fake addresses count for the one real network: one fingerprint, two sign-ups"""

    today = "signup_counts WHERE day = (now() AT TIME ZONE 'utc')::date"
    before = dict(line.split("|") for line in postgres_lines(client, f"SELECT ip_hash, count FROM {today}"))
    stamp = uuid.uuid4().hex[:10]
    emails = [f"ip-check-{stamp}-{index}@example.com" for index in range(2)]
    try:
        assert sign_up_through_the_site(emails[0], "198.51.100.1") == 200
        assert sign_up_through_the_site(emails[1], "198.51.100.2, 198.51.100.3") == 200
        after = dict(line.split("|") for line in postgres_lines(client, f"SELECT ip_hash, count FROM {today}"))
    finally:
        postgres_lines(client, "DELETE FROM auth.\"user\" WHERE email LIKE 'ip-check-%@example.com'")
        postgres_lines(client, "DELETE FROM mail_outbox WHERE recipient LIKE 'ip-check-%@example.com'")
        clear_mails(client, emails)
    changed = {key: int(value) - int(before.get(key, "0")) for key, value in after.items() if value != before.get(key)}
    assert list(changed.values()) == [2]
    stored = " ".join(postgres_lines(client, "SELECT ip_hash FROM signup_counts"))
    assert "198.51.100" not in stored
