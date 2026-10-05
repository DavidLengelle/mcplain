"""Tests on the running compose stack: docker compose build atelier, then docker compose up -d --build"""

import json
import os
import time
from collections.abc import Iterator
from typing import Any

import docker
import httpx
import pytest
from docker import DockerClient
from docker.models.containers import Container

pytestmark = pytest.mark.docker

API_URL = os.environ.get("MCPLAIN_API_URL", "http://127.0.0.1:8000")
PROJECT = "mcplain"
FINISHED: frozenset[str] = frozenset({"done", "failed"})
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


def analyze(http: httpx.Client, text: str) -> dict[str, Any]:
    """Ask the API for an analysis and poll it until it is finished"""

    response = http.post("/api/analyses", json={"input": text})
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
    assert attrs["HostConfig"]["PortBindings"] == {"3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3000"}]}


@pytest.mark.network
def test_fetch_server_is_orange_with_fetch_url_first(http: httpx.Client) -> None:
    """uvx mcp-server-fetch is orange, and O01 cites the request of fetch_url first"""

    body = analyze(http, "uvx mcp-server-fetch")
    assert body["state"] == "done", body
    verdict = body["result"]["verdict"]
    assert verdict["color"] == "orange"
    open_network = [alert for alert in verdict["alerts"] if alert["rule"] == "O01"]
    assert open_network[0]["function"] == "fetch_url"


@pytest.mark.network
def test_filesystem_server_is_orange_with_o08(http: httpx.Client) -> None:
    """npx -y @modelcontextprotocol/server-filesystem is orange with O08"""

    body = analyze(http, "npx -y @modelcontextprotocol/server-filesystem")
    assert body["state"] == "done", body
    verdict = body["result"]["verdict"]
    assert verdict["color"] == "orange"
    assert "O08" in {alert["rule"] for alert in verdict["alerts"]}


@pytest.mark.network
def test_second_request_is_served_from_the_cache(http: httpx.Client, client: DockerClient) -> None:
    """The second request for the same package starts no atelier and is served from the cache"""

    first = analyze(http, "npx -y @modelcontextprotocol/server-filesystem")
    start = time.time()
    second = analyze(http, "npx -y @modelcontextprotocol/server-filesystem")
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
