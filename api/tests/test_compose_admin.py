"""Tests of session 9c-1 on the running stack: the internal session route, the limit of get-session, 2FA, bans and CSRF"""

import base64
import hashlib
import hmac
import json
import struct
import subprocess
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import docker
import httpx
import pytest
from docker import DockerClient
from test_compose import REPOSITORY, clear_mails, compose_container, postgres_lines, web_port

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


PASSWORD = "test only admin password 0123"
LOGGED_SERVICES: tuple[str, ...] = ("guichet", "api", "web", "postgres", "facteur", "migrate")
TOTP_PERIOD = 30


def totp(secret: str, shift: int = 0) -> str:
    """Compute the 6-digit TOTP code of a base32 secret, SHA-1 and 30 seconds, as Google Authenticator does"""

    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded.upper())
    counter = int(time.time() // TOTP_PERIOD) + shift
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def wrong_totp(secret: str) -> str:
    """Return a 6-digit code that none of the three accepted windows gives"""

    right = {totp(secret, shift) for shift in (-1, 0, 1)}
    candidate = 0
    while f"{candidate:06d}" in right:
        candidate += 1
    return f"{candidate:06d}"


def solved(site: httpx.Client) -> str:
    """Solve a fresh ALTCHA challenge of the API, as the widget would"""

    from altcha import Challenge, Payload, solve_challenge

    challenge = Challenge.from_dict(site.get("/api/altcha/challenge").json())
    solution = solve_challenge(challenge)
    assert solution is not None
    return Payload(challenge, solution).to_base64()


class Browser:
    """Class that stands for one browser on the website: its own cookies, the Origin of the site on every change"""

    def __init__(self) -> None:
        """Open a client of the website with an empty cookie jar"""

        self.origin = f"http://localhost:{web_port()}"
        self.http = httpx.Client(base_url=self.origin, timeout=60, trust_env=False)

    def send(self, method: str, path: str, origin: str | None = "site", **options: object) -> httpx.Response:
        """Send a request; wait and try again when the limiter of the counter answers 429 before reading it"""

        headers = dict(options.pop("headers", {}) or {})
        if origin == "site":
            headers["Origin"] = self.origin
        elif origin is not None:
            headers["Origin"] = origin
        for _ in range(12):
            response = self.http.request(method, path, headers=headers, **options)
            wait = response.headers.get("x-retry-after")
            if response.status_code != 429 or wait is None:
                return response
            time.sleep(int(wait) + 1)
        return response

    def sign_in(self, email: str, password: str = PASSWORD) -> httpx.Response:
        """Send the password step of the sign-in, with a solved ALTCHA"""

        return self.send("POST", "/api/auth/sign-in/email", json={"email": email, "password": password}, headers={"x-altcha": solved(self.http)})

    def has_session(self) -> bool:
        """Tell whether the jar holds a session cookie"""

        return any(cookie.name.endswith("session_token") and cookie.value for cookie in self.http.cookies.jar)

    def close(self) -> None:
        """Close the client"""

        self.http.close()


@pytest.fixture
def accounts(client: DockerClient) -> Iterator[list[str]]:
    """Return the list of the test addresses; at the end, their accounts and their mails are deleted"""

    made: list[str] = []
    yield made
    for email in made:
        postgres_lines(client, f"DELETE FROM auth.\"user\" WHERE email = '{email}';")
    clear_mails(client, made)


@pytest.fixture
def browsers() -> Iterator[list[Browser]]:
    """Return a list where the tests keep their browsers, all closed at the end"""

    opened: list[Browser] = []
    yield opened
    for browser in opened:
        browser.close()


def new_browser(browsers: list[Browser]) -> Browser:
    """Open one more browser"""

    browser = Browser()
    browsers.append(browser)
    return browser


def make_account(client: DockerClient, browser: Browser, role: str, accounts: list[str]) -> str:
    """Sign up through the website, mark the address verified and set the role with psql, then sign in; return the email"""

    email = f"admin-9c-{uuid.uuid4().hex[:10]}@example.com"
    accounts.append(email)
    answer = browser.send(
        "POST",
        "/api/auth/sign-up/email",
        json={"email": email, "password": PASSWORD, "name": ""},
        headers={"x-altcha": solved(browser.http), "x-mcplain-lang": "en"},
    )
    assert answer.status_code == 200, answer.text
    postgres_lines(
        client,
        f"DELETE FROM mail_outbox WHERE recipient = '{email}'; "
        f"UPDATE auth.\"user\" SET \"emailVerified\" = true, role = '{role}' WHERE email = '{email}';",
    )
    assert browser.sign_in(email).status_code == 200
    assert browser.has_session()
    return email


def turn_on_two_factor(browser: Browser) -> tuple[str, list[str]]:
    """Turn the second factor on from My account: password, key, first code; return the key and the backup codes"""

    enabled = browser.send("POST", "/api/auth/two-factor/enable", json={"password": PASSWORD})
    assert enabled.status_code == 200, enabled.text
    body = enabled.json()
    secret = parse_qs(urlparse(body["totpURI"]).query)["secret"][0]
    verified = browser.send("POST", "/api/auth/two-factor/verify-totp", json={"code": totp(secret)})
    assert verified.status_code == 200, verified.text
    return secret, body["backupCodes"]


def user_id(client: DockerClient, email: str) -> str:
    """Return the id of an account, read as the owner of the database"""

    return postgres_lines(client, f"SELECT id FROM auth.\"user\" WHERE email = '{email}';")[0]


def sessions_of(client: DockerClient, email: str) -> int:
    """Count the sessions of an account in the database"""

    return int(postgres_lines(client, f"SELECT count(*) FROM auth.session s JOIN auth.\"user\" u ON u.id = s.\"userId\" WHERE u.email = '{email}';")[0])


def find(browser: Browser, email: str) -> httpx.Response:
    """Ask the admin route for one account"""

    return browser.send("GET", "/api/admin/accounts", params={"email": email})


def test_an_admin_without_second_factor_is_a_normal_account(client: DockerClient, accounts: list[str], browsers: list[Browser]) -> None:
    """Before the second factor, the admin role has the quota of an account and every admin route answers 403"""

    browser = new_browser(browsers)
    email = make_account(client, browser, "admin", accounts)
    assert browser.send("GET", "/api/quota").json()["kind"] == "account"
    assert find(browser, email).status_code == 403
    banned = browser.send("POST", f"/api/admin/accounts/{user_id(client, email)}/unban")
    assert (banned.status_code, banned.json()["error"]["code"]) == (403, "api.admin_required")


def test_the_whole_second_factor_journey_on_the_stack(client: DockerClient, accounts: list[str], browsers: list[Browser]) -> None:
    """Turn on, sign out, password alone gives nothing, a wrong code nothing, the right code a session; trustDevice ignored"""

    started = datetime.now(UTC)
    browser = new_browser(browsers)
    email = make_account(client, browser, "admin", accounts)
    secret, backup_codes = turn_on_two_factor(browser)
    assert browser.send("GET", "/api/quota").json()["kind"] == "admin"
    assert find(browser, email).json()["account"]["two_factor"] is True
    assert browser.send("POST", "/api/auth/sign-out", json={}).status_code == 200
    postgres_lines(client, f"DELETE FROM auth.session WHERE \"userId\" = '{user_id(client, email)}';")
    again = new_browser(browsers)
    step = again.sign_in(email)
    assert step.json()["twoFactorRedirect"] is True
    assert not again.has_session()
    assert sessions_of(client, email) == 0
    assert again.send("GET", "/api/quota").json()["kind"] == "anonymous"
    assert again.send("POST", "/api/auth/two-factor/verify-totp", json={"code": wrong_totp(secret)}).status_code == 401
    assert sessions_of(client, email) == 0
    right = again.send("POST", "/api/auth/two-factor/verify-totp", json={"code": totp(secret), "trustDevice": True})
    assert right.status_code == 200, right.text
    assert again.has_session()
    assert not [cookie for cookie in again.http.cookies.jar if "trust_device" in cookie.name and cookie.value]
    assert again.send("GET", "/api/quota").json()["kind"] == "admin"
    third = new_browser(browsers)
    third.http.cookies.set("mcplain.trust_device", "forged", domain="localhost")
    assert third.sign_in(email).json()["twoFactorRedirect"] is True
    assert not third.has_session()
    used = third.send("POST", "/api/auth/two-factor/verify-backup-code", json={"code": backup_codes[0]})
    assert used.status_code == 200, used.text
    assert third.has_session()
    fourth = new_browser(browsers)
    fourth.sign_in(email)
    assert fourth.send("POST", "/api/auth/two-factor/verify-backup-code", json={"code": backup_codes[0]}).status_code == 401
    assert not fourth.has_session()
    logs = service_logs(client, started)
    assert secret not in logs
    assert secret.lower() not in logs
    for code in backup_codes:
        assert code not in logs
    assert PASSWORD not in logs


def test_ten_wrong_codes_lock_the_admin_account(client: DockerClient, accounts: list[str], browsers: list[Browser]) -> None:
    """After 10 wrong codes in a row, even the right code is refused for a while"""

    browser = new_browser(browsers)
    email = make_account(client, browser, "admin", accounts)
    secret, _ = turn_on_two_factor(browser)
    for _ in range(2):
        attempt = new_browser(browsers)
        attempt.sign_in(email)
        for _ in range(5):
            assert attempt.send("POST", "/api/auth/two-factor/verify-totp", json={"code": wrong_totp(secret)}).status_code == 401
    last = new_browser(browsers)
    last.sign_in(email)
    locked = last.send("POST", "/api/auth/two-factor/verify-totp", json={"code": totp(secret)})
    assert (locked.status_code, locked.json()["code"]) == (429, "ACCOUNT_TEMPORARILY_LOCKED")
    assert not last.has_session()


def test_the_admin_bans_and_unbans_an_account_through_the_relay(client: DockerClient, accounts: list[str], browsers: list[Browser]) -> None:
    """The ban kills the sessions at once, the sign-in says only that the account is blocked; unban lets it in again"""

    admin = new_browser(browsers)
    admin_email = make_account(client, admin, "admin", accounts)
    turn_on_two_factor(admin)
    target = new_browser(browsers)
    target_email = make_account(client, target, "user", accounts)
    assert target.send("GET", "/api/quota").json()["kind"] == "account"
    target_id = find(admin, target_email).json()["account"]["id"]
    elsewhere = admin.send("POST", f"/api/admin/accounts/{target_id}/ban", origin="https://attacker.invalid", json={"reason": "spam"})
    assert (elsewhere.status_code, elsewhere.json()["error"]["code"]) == (403, "api.origin_refused")
    without = admin.send("POST", f"/api/admin/accounts/{target_id}/ban", origin=None, json={"reason": "spam"})
    assert (without.status_code, without.json()["error"]["code"]) == (403, "api.origin_refused")
    assert sessions_of(client, target_email) == 1
    banned = admin.send("POST", f"/api/admin/accounts/{target_id}/ban", json={"reason": "spam \u202e test"})
    assert banned.status_code == 200, banned.text
    assert sessions_of(client, target_email) == 0
    assert target.send("GET", "/api/quota").json()["kind"] == "anonymous"
    assert target.send("GET", "/api/account/history").status_code == 401
    refused = new_browser(browsers).sign_in(target_email)
    assert (refused.status_code, refused.json()) == (403, {"code": "ACCOUNT_BLOCKED", "message": "Refused"})
    assert find(admin, target_email).json()["account"]["ban_reason"] == "spam \u202e test"
    myself = admin.send("POST", f"/api/admin/accounts/{user_id(client, admin_email)}/ban", json={})
    assert (myself.status_code, myself.json()["error"]["code"]) == (403, "api.cannot_ban_self")
    other_admin = new_browser(browsers)
    other_email = make_account(client, other_admin, "admin", accounts)
    refused_admin = admin.send("POST", f"/api/admin/accounts/{user_id(client, other_email)}/ban", json={})
    assert (refused_admin.status_code, refused_admin.json()["error"]["code"]) == (403, "api.cannot_ban_admin")
    assert admin.send("POST", f"/api/admin/accounts/{target_id}/unban", json={}).status_code == 200
    back = new_browser(browsers)
    assert back.sign_in(target_email).status_code == 200
    assert back.send("GET", "/api/quota").json()["kind"] == "account"


def test_reset_admin_2fa_turns_the_second_factor_off_and_kills_the_sessions(
    client: DockerClient, accounts: list[str], browsers: list[Browser]
) -> None:
    """The local script, run by David only, turns off the second factor of one account and deletes its sessions"""

    browser = new_browser(browsers)
    email = make_account(client, browser, "admin", accounts)
    turn_on_two_factor(browser)
    assert sessions_of(client, email) == 1
    done = subprocess.run([str(REPOSITORY / "scripts" / "reset-admin-2fa.sh"), email], cwd=REPOSITORY, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert sessions_of(client, email) == 0
    assert postgres_lines(client, f"SELECT \"twoFactorEnabled\" FROM auth.\"user\" WHERE email = '{email}';") == ["f"]
    assert postgres_lines(client, f"SELECT count(*) FROM auth.\"twoFactor\" WHERE \"userId\" = '{user_id(client, email)}';") == ["0"]
    again = new_browser(browsers)
    assert again.sign_in(email).status_code == 200
    assert again.has_session()
    assert again.send("GET", "/api/quota").json()["kind"] == "account"
    missing = subprocess.run([str(REPOSITORY / "scripts" / "reset-admin-2fa.sh"), "nobody-9c@example.com"], cwd=REPOSITORY, capture_output=True, text=True, check=False)
    assert missing.returncode == 1


def service_logs(client: DockerClient, since: datetime) -> str:
    """Return what the services of the stack printed since a moment"""

    texts = []
    for service in LOGGED_SERVICES:
        for container in client.containers.list(all=True, filters={"label": [f"com.docker.compose.service={service}", "com.docker.compose.project=mcplain"]}):
            texts.append(container.logs(since=since, stdout=True, stderr=True).decode("utf-8", errors="replace"))
    return "\n".join(texts)
