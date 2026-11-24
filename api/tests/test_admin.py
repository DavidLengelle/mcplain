"""Tests of the admin routes: admin role and second factor on every route, the origin of every change, and the bans"""

import json
import re
import uuid
from collections.abc import Iterator

import httpx
import pytest
import respx
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from helpers import altcha_settings, make_settings
from sqlalchemy.orm import sessionmaker

from mcplain_api.admin_accounts import DeskOutcome, GuichetDesk, Lookup
from mcplain_api.app import create_app
from mcplain_api.db import Base, make_engine, make_sessions
from mcplain_api.session_user import CurrentUser

ORIGIN = "http://localhost:3010"
OTHER_ORIGIN = "https://attacker.invalid"
PEER = "testclient"
PATH_PARAMETER = re.compile(r"\{[a-z_]+\}")
SAMPLE_ID = "00000000-0000-4000-8000-000000000000"


class FakeUsers:
    """Class that stands for the counter: a cookie names a user, and the API may forget the users of an account"""

    def __init__(self) -> None:
        """Start without any signed-in user"""

        self.users: dict[str, CurrentUser] = {}
        self.forgotten: list[str] = []

    def add(self, role: str = "user", two_factor: bool = False, banned: bool = False) -> tuple[str, dict[str, str]]:
        """Sign in a new user and return its id and the Cookie header of its session"""

        user = CurrentUser(id=uuid.uuid4().hex, email_verified=True, role=role, two_factor=two_factor, banned=banned)
        cookie = f"mcplain.session_token={user.id}"
        self.users[cookie] = user
        return user.id, {"Cookie": cookie}

    def current_user(self, cookie_header: str | None) -> CurrentUser | None:
        """Return the user of a cookie"""

        if cookie_header is None:
            return None
        return self.users.get(cookie_header)

    def forget_user(self, user_id: str) -> None:
        """Remember that the API dropped the kept answers of an account"""

        self.forgotten.append(user_id)


class FakeDesk:
    """Class that stands for the internal account routes of the counter"""

    def __init__(self) -> None:
        """Start with one normal account and one admin account"""

        self.calls: list[tuple[str, str, str | None]] = []
        self.admins: set[str] = set()
        self.known: dict[str, dict[str, object]] = {}
        self.outcome: DeskOutcome | None = None
        self.created: dict[str, int] | None = {}

    def find(self, email: str) -> Lookup:
        """Return the account of an exact email"""

        self.calls.append(("find", email, None))
        if email in self.known:
            return Lookup(DeskOutcome.DONE, self.known[email])
        return Lookup(DeskOutcome.NOT_FOUND)

    def ban(self, user_id: str, reason: str | None) -> DeskOutcome:
        """Ban an account unless it is an admin"""

        self.calls.append(("ban", user_id, reason))
        if self.outcome is not None:
            return self.outcome
        if user_id in self.admins:
            return DeskOutcome.IS_ADMIN
        return DeskOutcome.DONE

    def unban(self, user_id: str) -> DeskOutcome:
        """Lift a ban"""

        self.calls.append(("unban", user_id, None))
        return DeskOutcome.DONE

    def created_per_day(self, days: int) -> dict[str, int] | None:
        """Return the accounts created per day that the test chose"""

        return self.created


@pytest.fixture
def users() -> FakeUsers:
    """Return a fake counter without users"""

    return FakeUsers()


@pytest.fixture
def desk() -> FakeDesk:
    """Return a fake accounts desk"""

    return FakeDesk()


def build(users: FakeUsers, desk: FakeDesk, **values: object) -> TestClient:
    """Return a test client of the API whose website origin is ORIGIN"""

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions: sessionmaker = make_sessions(engine)
    settings = altcha_settings(public_url=ORIGIN, **values)
    app = create_app(settings, sessions.kw["bind"], peer_resolver=lambda names: {PEER}, user_reader=users, account_desk=desk)
    return TestClient(app)


@pytest.fixture
def client(users: FakeUsers, desk: FakeDesk) -> Iterator[TestClient]:
    """Return a test client of the API"""

    with build(users, desk) as test_client:
        yield test_client


def admin_routes() -> list[tuple[str, str]]:
    """Return every method and path of the API under /api/admin, with a sample id"""

    app = create_app(altcha_settings(public_url=ORIGIN), make_engine("sqlite://"), user_reader=FakeUsers(), account_desk=FakeDesk())
    found = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/admin"):
            for method in sorted(route.methods):
                path = route.path.replace("{account_id}", "someone")
                found.append((method, PATH_PARAMETER.sub(SAMPLE_ID, path)))
    return found


def call(client: TestClient, method: str, path: str, headers: dict[str, str], origin: str | None = ORIGIN) -> object:
    """Call one admin route with a JSON body, from an origin when given"""

    sent = {**headers, "Content-Type": "application/json"}
    if origin is not None:
        sent["Origin"] = origin
    if method == "GET":
        return client.get(path, params={"email": "eve@example.com", "days": "30"}, headers=sent)
    return client.request(method, path, json={"reason": None}, headers=sent)


def test_the_admin_routes_are_the_expected_ones() -> None:
    """The list of the admin routes is known: a new one must come with its tests"""

    assert admin_routes() == [
        ("GET", "/api/admin/accounts"),
        ("POST", "/api/admin/accounts/someone/ban"),
        ("POST", "/api/admin/accounts/someone/unban"),
        ("GET", "/api/admin/dashboard/spend"),
        ("GET", "/api/admin/dashboard/ai"),
        ("GET", "/api/admin/dashboard/analyses"),
        ("GET", "/api/admin/dashboard/refusals"),
        ("GET", "/api/admin/dashboard/accounts"),
        ("GET", "/api/admin/credit"),
        ("POST", "/api/admin/credit"),
        ("DELETE", "/api/admin/credit/00000000-0000-4000-8000-000000000000"),
        ("POST", "/api/admin/texts/00000000-0000-4000-8000-000000000000/retry"),
        ("POST", "/api/admin/analyses/00000000-0000-4000-8000-000000000000/rerun"),
        ("POST", "/api/admin/alerts/00000000-0000-4000-8000-000000000000/read"),
        ("GET", "/api/admin/journal"),
    ]


def test_every_admin_route_refuses_anybody_but_the_admin_with_its_second_factor(users: FakeUsers, desk: FakeDesk) -> None:
    """Anonymous, normal account, bench account, admin without second factor, banned admin: all refused on every route"""

    with build(users, desk, allow_bench_role=True) as client:
        identities = {
            "anonymous": {},
            "user": users.add("user")[1],
            "user with a second factor": users.add("user", two_factor=True)[1],
            "bench": users.add("bench", two_factor=True)[1],
            "admin without second factor": users.add("admin")[1],
            "banned admin": users.add("admin", two_factor=True, banned=True)[1],
        }
        for method, path in admin_routes():
            for name, headers in identities.items():
                answer = call(client, method, path, headers)
                assert answer.status_code == 403, (method, path, name)
                assert answer.json()["error"]["code"] == "api.admin_required", (method, path, name)
                assert answer.headers["cache-control"] == "no-store"
        _, admin = users.add("admin", two_factor=True)
        for method, path in admin_routes():
            assert call(client, method, path, admin).status_code != 403, (method, path)
    assert desk.calls == [("find", "eve@example.com", None), ("ban", "someone", None), ("unban", "someone", None)]


def test_an_unknown_admin_path_is_refused_before_anything(client: TestClient, users: FakeUsers) -> None:
    """A path under /api/admin that does not exist is still refused to a normal account"""

    _, headers = users.add("user")
    assert client.get("/api/admin/anything", headers=headers).status_code == 403
    assert client.get("/api/admin", headers=headers).status_code == 403


def test_a_change_from_another_origin_or_without_origin_is_refused(client: TestClient, users: FakeUsers, desk: FakeDesk) -> None:
    """POST of an admin route: Origin must be the website; another one or none at all is refused, even for the admin"""

    _, admin = users.add("admin", two_factor=True)
    for method, path in admin_routes():
        if method == "GET":
            continue
        for origin in (OTHER_ORIGIN, None, "http://localhost:3010.attacker.invalid", "null"):
            answer = call(client, method, path, admin, origin)
            assert answer.status_code == 403, (path, origin)
            assert answer.json()["error"]["code"] == "api.origin_refused"
    assert desk.calls == []
    assert call(client, "POST", "/api/admin/accounts/someone/ban", admin).status_code == 200


def test_the_admin_finds_one_account_by_its_exact_email(client: TestClient, users: FakeUsers, desk: FakeDesk) -> None:
    """GET /api/admin/accounts?email= answers one account or 404; an empty or strange address is refused"""

    _, admin = users.add("admin", two_factor=True)
    desk.known["eve@example.com"] = {"id": "e1", "email": "eve@example.com", "banned_at": None, "ban_reason": None}
    found = client.get("/api/admin/accounts", params={"email": " eve@example.com "}, headers=admin)
    assert found.status_code == 200
    assert found.json() == {"account": desk.known["eve@example.com"]}
    assert client.get("/api/admin/accounts", params={"email": "bob@example.com"}, headers=admin).status_code == 404
    assert client.get("/api/admin/accounts", params={"email": "eve"}, headers=admin).status_code == 400
    assert client.get("/api/admin/accounts", headers=admin).status_code == 400
    assert client.get("/api/admin/accounts", params={"email": "a@" + "b" * 320}, headers=admin).status_code == 400


def test_the_admin_bans_and_unbans_and_every_kept_session_is_forgotten(
    client: TestClient, users: FakeUsers, desk: FakeDesk
) -> None:
    """A ban sends the reason, trimmed, to the counter, and the API forgets all the kept sessions of that account"""

    _, admin = users.add("admin", two_factor=True)
    headers = {**admin, "Origin": ORIGIN}
    banned = client.post("/api/admin/accounts/e1/ban", json={"reason": "  spam  "}, headers=headers)
    assert banned.status_code == 200
    assert banned.json() == {"ok": True}
    assert client.post("/api/admin/accounts/e2/ban", json={"reason": "   "}, headers=headers).status_code == 200
    assert client.post("/api/admin/accounts/e3/ban", json={}, headers=headers).status_code == 200
    assert client.post("/api/admin/accounts/e1/unban", headers=headers).status_code == 200
    assert desk.calls == [("ban", "e1", "spam"), ("ban", "e2", None), ("ban", "e3", None), ("unban", "e1", None)]
    assert users.forgotten == ["e1", "e2", "e3", "e1"]


def test_the_admin_cannot_ban_itself_nor_another_admin(client: TestClient, users: FakeUsers, desk: FakeDesk) -> None:
    """Banning oneself is refused by the API; banning another admin is refused by the counter"""

    own_id, admin = users.add("admin", two_factor=True)
    headers = {**admin, "Origin": ORIGIN}
    myself = client.post(f"/api/admin/accounts/{own_id}/ban", json={}, headers=headers)
    assert (myself.status_code, myself.json()["error"]["code"]) == (403, "api.cannot_ban_self")
    desk.admins.add("a2")
    other = client.post("/api/admin/accounts/a2/ban", json={}, headers=headers)
    assert (other.status_code, other.json()["error"]["code"]) == (403, "api.cannot_ban_admin")
    assert [item[1] for item in desk.calls] == ["a2"]
    assert users.forgotten == []


def test_a_ban_request_is_checked(client: TestClient, users: FakeUsers, desk: FakeDesk) -> None:
    """A reason over 200 characters, an unknown field, a body that is not JSON, a strange id or a counter down: refused"""

    _, admin = users.add("admin", two_factor=True)
    headers = {**admin, "Origin": ORIGIN}
    assert client.post("/api/admin/accounts/e1/ban", json={"reason": "x" * 201}, headers=headers).status_code == 400
    assert client.post("/api/admin/accounts/e1/ban", json={"reason": "x" * 200}, headers=headers).status_code == 200
    assert client.post("/api/admin/accounts/e1/ban", json={"other": 1}, headers=headers).status_code == 400
    assert client.post("/api/admin/accounts/e1/ban", content="reason=x", headers=headers).status_code == 415
    assert client.post("/api/admin/accounts/e%20x/ban", json={}, headers=headers).status_code == 404
    desk.outcome = DeskOutcome.NOT_FOUND
    assert client.post("/api/admin/accounts/e9/ban", json={}, headers=headers).status_code == 404
    desk.outcome = DeskOutcome.UNAVAILABLE
    down = client.post("/api/admin/accounts/e9/ban", json={}, headers=headers)
    assert (down.status_code, down.json()["error"]["code"]) == (503, "api.guichet_unavailable")


def test_a_banned_account_is_nobody_on_public_routes_and_refused_on_its_own(client: TestClient, users: FakeUsers) -> None:
    """The quota of a banned account is the one of its network, and its history answers 403"""

    _, headers = users.add("user", banned=True)
    assert client.get("/api/quota", headers=headers).json()["kind"] == "anonymous"
    history = client.get("/api/account/history", headers=headers)
    assert (history.status_code, history.json()["error"]["code"]) == (403, "api.account_blocked")
    assert client.delete("/api/account/history", headers=headers).status_code == 403


GUICHET = "http://guichet:3100"


@respx.mock
def test_the_desk_asks_the_internal_routes_of_the_counter() -> None:
    """The desk reaches /internal/accounts, keeps only the known fields, and reads 404, 409 and errors"""

    found = respx.get(f"{GUICHET}/internal/accounts").mock(
        return_value=httpx.Response(200, json={"account": {"id": "e1", "email": "eve@example.com", "secret": "x"}})
    )
    desk = GuichetDesk(make_settings())
    lookup = desk.find("eve@example.com")
    assert lookup.outcome is DeskOutcome.DONE
    assert lookup.account is not None and "secret" not in lookup.account and lookup.account["id"] == "e1"
    assert found.calls.last.request.url.params["email"] == "eve@example.com"
    respx.get(f"{GUICHET}/internal/accounts").mock(return_value=httpx.Response(404))
    assert desk.find("bob@example.com").outcome is DeskOutcome.NOT_FOUND
    respx.get(f"{GUICHET}/internal/accounts").mock(return_value=httpx.Response(200, json={"account": None}))
    assert desk.find("bob@example.com").outcome is DeskOutcome.UNAVAILABLE
    ban = respx.post(f"{GUICHET}/internal/accounts/ban").mock(return_value=httpx.Response(200, json={"ok": True}))
    assert desk.ban("e1", "spam") is DeskOutcome.DONE
    assert json.loads(ban.calls.last.request.content) == {"user_id": "e1", "reason": "spam"}
    respx.post(f"{GUICHET}/internal/accounts/ban").mock(return_value=httpx.Response(409))
    assert desk.ban("a1", None) is DeskOutcome.IS_ADMIN
    respx.post(f"{GUICHET}/internal/accounts/unban").mock(side_effect=httpx.ConnectError("down"))
    assert desk.unban("e1") is DeskOutcome.UNAVAILABLE
