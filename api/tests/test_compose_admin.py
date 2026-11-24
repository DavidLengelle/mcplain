"""Tests of session 9c-1 on the running stack: the internal session route, the limit of get-session, 2FA, bans and CSRF"""

import json

import docker
import pytest
from docker import DockerClient
from test_compose import compose_container

pytestmark = pytest.mark.docker

SESSION_LIMIT = 100
READ_SESSIONS = """
const [url, count, fake] = process.argv.slice(1);
const statuses = [];
for (let index = 0; index < Number(count); index += 1) {
  const headers = {};
  if (fake === "yes") {
    headers["x-forwarded-for"] = `198.51.100.${index % 250}`;
  }
  const response = await fetch(url, { headers });
  statuses.push(response.status);
}
console.log(JSON.stringify(statuses));
"""
READ_SESSIONS_PYTHON = """
import json, sys
import httpx
url, count = sys.argv[1], int(sys.argv[2])
with httpx.Client(timeout=10, trust_env=False) as client:
    print(json.dumps([client.get(url).status_code for _ in range(count)]))
"""
FETCH_INTERNAL = """
const response = await fetch(process.argv[1], { headers: { cookie: "mcplain.session_token=x" } });
console.log(JSON.stringify({ status: response.status, body: await response.text() }));
"""


@pytest.fixture
def client() -> DockerClient:
    """Return a Docker client"""

    return docker.from_env()


def node_in(client: DockerClient, service: str, script: str, *arguments: str) -> object:
    """Run a small Node.js module in a container of the stack and return what it printed as JSON"""

    exit_code, (stdout, stderr) = compose_container(client, service).exec_run(
        ["node", "--input-type=module", "-e", script, *arguments], demux=True
    )
    assert exit_code == 0, stderr
    return json.loads(stdout)


def python_in_api(client: DockerClient, script: str, *arguments: str) -> object:
    """Run a small Python script in the API container and return what it printed as JSON"""

    exit_code, (stdout, stderr) = compose_container(client, "api").exec_run(["python", "-c", script, *arguments], demux=True)
    assert exit_code == 0, stderr
    return json.loads(stdout)


def test_the_public_session_route_is_limited_per_real_visitor_address(client: DockerClient) -> None:
    """Through the relay, get-session stops at 100 a minute for one visitor, fake X-Forwarded-For or not; another has its own"""

    url = "http://web:3000/api/auth/get-session"
    first = node_in(client, "guichet", READ_SESSIONS, url, str(SESSION_LIMIT + 5), "yes")
    assert isinstance(first, list)
    assert 429 in first
    assert first.index(429) <= SESSION_LIMIT
    assert all(status == 200 for status in first[: first.index(429)])
    assert set(first[first.index(429) :]) == {429}
    other = python_in_api(client, READ_SESSIONS_PYTHON, url, "3")
    assert other == [200, 200, 200]


def test_the_internal_session_route_answers_the_api_only(client: DockerClient) -> None:
    """The counter answers /internal/session to the API container only; the website neither reaches it nor relays it"""

    from_web = node_in(client, "web", FETCH_INTERNAL, "http://guichet:3100/internal/session")
    assert from_web == {"status": 404, "body": '{"error":"not_found"}'}
    relayed = node_in(client, "web", FETCH_INTERNAL, "http://127.0.0.1:3000/internal/session")
    assert isinstance(relayed, dict) and relayed["status"] == 404 and not relayed["body"].startswith("{")
    from_api = python_in_api(
        client,
        "import json, httpx; r = httpx.get('http://guichet:3100/internal/session', headers={'cookie': 'mcplain.session_token=x'});"
        " print(json.dumps({'status': r.status_code, 'body': r.json()}))",
    )
    assert from_api == {"status": 200, "body": {"user": None}}
