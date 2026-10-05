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
