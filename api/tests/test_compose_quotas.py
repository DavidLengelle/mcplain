"""Tests of the quotas on the running stack, through the website as a browser: ALTCHA solved, accounts made with psql"""

import time
import uuid
from collections.abc import Iterator

import docker
import httpx
import pytest
from docker import DockerClient
from test_compose import clear_mails, compose_container, postgres_lines, web_port

pytestmark = pytest.mark.docker

PASSWORD = "test only quota password 0123"
INVALID = {"input": "pip install requests"}
BENCH_SETTING = "MCPLAIN_ALLOW_BENCH_ROLE=true"


@pytest.fixture
def client() -> DockerClient:
    """Return a Docker client"""

    return docker.from_env()


@pytest.fixture
def site() -> Iterator[httpx.Client]:
    """Return a client of the website, which relays /api to the API and /api/auth to the counter"""

    with httpx.Client(base_url=f"http://localhost:{web_port()}", timeout=60, trust_env=False) as test_client:
        yield test_client


def reset(client: DockerClient) -> None:
    """Empty the quotas and the burst counts as the owner of the database: tests only, never through the API"""

    postgres_lines(client, "DELETE FROM quota_usage; DELETE FROM burst_counts; DELETE FROM analysis_tokens;")


@pytest.fixture
def emails(client: DockerClient) -> Iterator[list[str]]:
    """Return the list of the test addresses; at the end, their accounts and their mails in Mailpit are deleted"""

    made: list[str] = []
    yield made
    for email in made:
        drop_account(client, email)
    clear_mails(client, made)


def solved(site: httpx.Client) -> str:
    """Solve a fresh ALTCHA challenge of the API, as the widget would"""

    from altcha import Challenge, Payload, solve_challenge

    challenge = Challenge.from_dict(site.get("/api/altcha/challenge").json())
    solution = solve_challenge(challenge)
    assert solution is not None
    return Payload(challenge, solution).to_base64()


def ask(site: httpx.Client, body: dict[str, str], fake_address: str | None = None) -> httpx.Response:
    """Ask the website for an analysis with a fresh solution, and a fake X-Forwarded-For when given"""

    headers = {"x-altcha": solved(site)}
    if fake_address is not None:
        headers["X-Forwarded-For"] = fake_address
    return site.post("/api/analyses", json=body, headers=headers)


def make_account(client: DockerClient, site: httpx.Client, role: str, emails: list[str]) -> str:
    """Sign up through the website, then mark the address verified and set the role with psql; return the email"""

    email = f"quota-{uuid.uuid4().hex[:10]}@example.com"
    emails.append(email)
    origin = str(site.base_url).rstrip("/")
    answer = site.post(
        "/api/auth/sign-up/email",
        json={"email": email, "password": PASSWORD, "name": ""},
        headers={"Origin": origin, "x-altcha": solved(site), "x-mcplain-lang": "en"},
    )
    assert answer.status_code == 200, answer.text
    postgres_lines(
        client,
        f"DELETE FROM mail_outbox WHERE recipient = '{email}'; "
        f"UPDATE auth.\"user\" SET \"emailVerified\" = true, role = '{role}' WHERE email = '{email}';",
    )
    signed = site.post(
        "/api/auth/sign-in/email",
        json={"email": email, "password": PASSWORD},
        headers={"Origin": origin, "x-altcha": solved(site)},
    )
    assert signed.status_code == 200, signed.text
    return email


def drop_account(client: DockerClient, email: str) -> None:
    """Remove a test account as the owner of the database"""

    postgres_lines(client, f"DELETE FROM auth.\"user\" WHERE email = '{email}';")


def bench_allowed(client: DockerClient) -> bool:
    """Tell whether the running API accepts the bench role"""

    return BENCH_SETTING in compose_container(client, "api").attrs["Config"]["Env"]


def test_a_fake_forwarded_for_through_the_site_does_not_reset_the_quota(client: DockerClient, site: httpx.Client) -> None:
    """Four requests with four fake X-Forwarded-For count for one network: the fourth is cache-only"""

    reset(client)
    answers = [ask(site, {"input": f"npx -y @mcplain-demo/not-there-{uuid.uuid4().hex[:8]}"}, f"6.6.6.{n}") for n in range(4)]
    assert [answer.status_code for answer in answers] == [202, 202, 202, 202]
    assert [answer.json()["cache_only"] for answer in answers] == [False, False, False, True]
    assert site.get("/api/quota", headers={"X-Forwarded-For": "7.7.7.7"}).json()["remaining"] == 0
    reset(client)


def test_the_burst_limit_stops_the_31st_request_of_a_network(client: DockerClient, site: httpx.Client) -> None:
    """Thirty requests in the hour pass, the 31st is refused with 429 and Retry-After, even refused inputs count"""

    reset(client)
    for _ in range(30):
        assert ask(site, INVALID).status_code == 400
    refused = site.post("/api/analyses", json=INVALID, headers={"x-altcha": solved(site)})
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "burst_limit"
    assert int(refused.headers["Retry-After"]) > 0
    reset(client)


def test_the_bench_role_has_no_quota_nor_burst_limit_but_altcha(
    client: DockerClient, site: httpx.Client, emails: list[str]
) -> None:
    """A bench account passes 35 requests in a row and has no limit, but still needs ALTCHA"""

    if not bench_allowed(client):
        pytest.skip("start the stack with MCPLAIN_ALLOW_BENCH_ROLE=true")
    reset(client)
    make_account(client, site, "bench", emails)
    try:
        assert site.get("/api/quota").json()["kind"] == "bench"
        for _ in range(35):
            assert ask(site, INVALID).status_code == 400
        refused = site.post("/api/analyses", json=INVALID)
        assert (refused.status_code, refused.json()["error"]["code"]) == (403, "altcha_invalid")
    finally:
        reset(client)


def test_deleting_an_account_erases_its_history_and_its_quota(
    client: DockerClient, site: httpx.Client, emails: list[str]
) -> None:
    """The counter asks the API to erase the history and the quota rows before it deletes the account"""

    reset(client)
    email = make_account(client, site, "user", emails)
    identifier = ask(site, {"input": f"npx -y @mcplain-demo/not-there-{uuid.uuid4().hex[:8]}"}).json()["id"]
    user_id = postgres_lines(client, f"SELECT id FROM auth.\"user\" WHERE email = '{email}';")[0]
    assert site.get("/api/quota").json()["kind"] == "account"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not site.get("/api/account/history").json()["entries"]:
        time.sleep(0.5)
    assert site.get("/api/account/history").json()["entries"][0]["id"] == identifier
    origin = str(site.base_url).rstrip("/")
    deleted = site.post("/api/auth/delete-user", json={"password": PASSWORD}, headers={"Origin": origin})
    assert deleted.status_code == 200, deleted.text
    assert postgres_lines(client, f"SELECT count(*) FROM user_history WHERE user_id = '{user_id}';") == ["0"]
    assert postgres_lines(client, f"SELECT count(*) FROM quota_usage WHERE subject = 'user:{user_id}';") == ["0"]
    assert postgres_lines(client, f"SELECT count(*) FROM auth.\"user\" WHERE email = '{email}';") == ["0"]
    reset(client)
