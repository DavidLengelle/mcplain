"""Tests of what the API does for the accounts: visitor address, fingerprint, ALTCHA, the guard of the counter, the session"""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from altcha import Challenge, Payload, create_challenge, solve_challenge
from fastapi.testclient import TestClient
from helpers import make_settings
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from mcplain_api.altcha_gate import accept_solution, new_challenge
from mcplain_api.app import create_app
from mcplain_api.auth_guard import GuardAction, check_action
from mcplain_api.client_ip import normalize_ip, visitor_ip
from mcplain_api.db import AltchaUse, Base, IpSalt, SignupCount, SignupRefusal, make_engine, make_sessions
from mcplain_api.ip_fingerprint import ip_fingerprint, purge_old_fingerprints, salt_of_day
from mcplain_api.session_user import CurrentUser, SessionReader, account_cookies
from mcplain_api.settings import Settings

TEST_KEY = "test only altcha key, never a real one"
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
GUICHET = "http://guichet:3100"
SESSION_URL = f"{GUICHET}/api/auth/get-session"
SESSION_COOKIE = "mcplain.session_token=abc.def"


def settings_for_accounts(**values: object) -> Settings:
    """Return test settings with a test ALTCHA key and the cheapest cost"""

    defaults: dict[str, object] = {"altcha_hmac_key": TEST_KEY, "altcha_cost": 1}
    defaults.update(values)
    return make_settings(**defaults)


@pytest.fixture
def sessions() -> sessionmaker:
    """Return a session factory on a fresh in-memory database"""

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_sessions(engine)


def solved(challenge: Challenge) -> str:
    """Solve a challenge as the widget would, and return the base64 payload"""

    solution = solve_challenge(challenge)
    assert solution is not None
    return Payload(challenge, solution).to_base64()


def fresh_payload(settings: Settings) -> str:
    """Return the payload of a fresh challenge of the API, solved"""

    data = new_challenge(settings, datetime.now(UTC))
    assert data is not None
    return solved(Challenge.from_dict(data))


def test_a_fake_forwarded_for_from_the_browser_does_not_change_the_address() -> None:
    """Our relay appends the real address: whatever the browser writes on the left is ignored"""

    assert visitor_ip(["203.0.113.7"], "172.18.0.5", 1) == "203.0.113.7"
    assert visitor_ip(["6.6.6.6, 203.0.113.7"], "172.18.0.5", 1) == "203.0.113.7"
    assert visitor_ip(["6.6.6.6", "7.7.7.7, 203.0.113.7"], "172.18.0.5", 1) == "203.0.113.7"
    assert visitor_ip(["6.6.6.6, 203.0.113.7, 10.0.0.2"], "172.18.0.5", 2) == "203.0.113.7"


def test_without_our_relay_the_address_is_unknown_or_the_peer() -> None:
    """Fewer entries than relays means the request skipped them; zero hops means the direct peer"""

    assert visitor_ip([], "172.18.0.5", 1) is None
    assert visitor_ip(["203.0.113.7"], "172.18.0.5", 2) is None
    assert visitor_ip(["6.6.6.6"], "198.51.100.4", 0) == "198.51.100.4"
    assert visitor_ip(["not an address"], None, 1) is None
    assert visitor_ip([", ".join(["1.1.1.1"] * 40)], None, 1) is None


def test_ipv6_is_cut_to_its_64_prefix() -> None:
    """Two addresses of one IPv6 network are one visitor; a mapped IPv4 is its IPv4"""

    first = visitor_ip(["2001:db8:1:2:aaaa::1"], None, 1)
    second = visitor_ip(["2001:db8:1:2:bbbb::9"], None, 1)
    assert first == second == "2001:db8:1:2::/64"
    assert normalize_ip("::ffff:203.0.113.7") == "203.0.113.7"
    assert normalize_ip("[2001:db8::1]") == "2001:db8::/64"
    assert normalize_ip("fe80::1%eth0") == "fe80::/64"


def test_fingerprint_is_an_hmac_with_the_salt_of_the_day(sessions: sessionmaker) -> None:
    """The fingerprint is HMAC-SHA256 of the address with the random salt of the UTC day, stable during the day"""

    with sessions.begin() as session:
        first = ip_fingerprint(session, "203.0.113.7", NOW)
        again = ip_fingerprint(session, "203.0.113.7", NOW + timedelta(hours=5))
        other = ip_fingerprint(session, "203.0.113.8", NOW)
        tomorrow = ip_fingerprint(session, "203.0.113.7", NOW + timedelta(days=1))
        salt = salt_of_day(session, NOW.date())
    assert first == again
    assert first != other
    assert first != tomorrow
    assert first == hmac.new(salt, b"203.0.113.7", hashlib.sha256).hexdigest()
    assert len(salt) == 32


def test_salts_are_deleted_after_two_days(sessions: sessionmaker) -> None:
    """Today and yesterday keep their salt; older salts and sign-up counts are deleted"""

    with sessions.begin() as session:
        for days in range(4):
            ip_fingerprint(session, "203.0.113.7", NOW - timedelta(days=days))
            session.add(SignupCount(day=(NOW - timedelta(days=days)).date(), ip_hash=str(days) * 64, count=1))
    with sessions.begin() as session:
        purge_old_fingerprints(session, NOW)
    with sessions() as session:
        days_kept = sorted(session.scalars(select(IpSalt.day)).all())
        counts_kept = sorted(session.scalars(select(SignupCount.day)).all())
    assert days_kept == [(NOW - timedelta(days=1)).date(), NOW.date()]
    assert counts_kept == days_kept


def test_no_address_is_stored_in_clear(sessions: sessionmaker) -> None:
    """After a sign-up, no table of the database holds the visitor address"""

    settings = settings_for_accounts()
    answer = check_action(
        sessions, settings, GuardAction.SIGN_UP, fresh_payload(settings), {"x-forwarded-for": "6.6.6.6, 203.0.113.77"}, NOW
    )
    assert answer.ok
    with sessions() as session:
        stored = " ".join(str(row) for table in Base.metadata.sorted_tables for row in session.execute(select(table)).all())
    assert "203.0.113.77" not in stored
    assert "6.6.6.6" not in stored


def test_challenge_is_signed_and_expires_after_five_minutes() -> None:
    """The challenge is PBKDF2/SHA-256, with the configured cost, signed, and valid five minutes"""

    data = new_challenge(settings_for_accounts(altcha_cost=2000), NOW)
    assert data is not None
    assert data["parameters"]["algorithm"] == "PBKDF2/SHA-256"
    assert data["parameters"]["cost"] == 2000
    assert data["parameters"]["expiresAt"] == int((NOW + timedelta(minutes=5)).timestamp())
    assert isinstance(data["signature"], str) and len(data["signature"]) == 64
    assert new_challenge(make_settings(), NOW) is None


def test_a_valid_solution_is_accepted_once(sessions: sessionmaker) -> None:
    """A solved challenge is accepted the first time, refused when replayed"""

    settings = settings_for_accounts()
    payload = fresh_payload(settings)
    with sessions.begin() as session:
        assert accept_solution(session, settings, payload, datetime.now(UTC))
    with sessions.begin() as session:
        assert not accept_solution(session, settings, payload, datetime.now(UTC))
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(AltchaUse)) == 1


def test_an_expired_solution_is_refused(sessions: sessionmaker) -> None:
    """A challenge whose time is over is refused, even well solved"""

    settings = settings_for_accounts()
    challenge = create_challenge("PBKDF2/SHA-256", 1, expires_at=int(datetime.now(UTC).timestamp()) - 1, hmac_secret=TEST_KEY)
    with sessions.begin() as session:
        assert not accept_solution(session, settings, solved(challenge), datetime.now(UTC))


def test_a_wrong_signature_is_refused(sessions: sessionmaker) -> None:
    """A challenge signed with another key, unsigned, or a broken payload is refused"""

    settings = settings_for_accounts()
    expires = int(datetime.now(UTC).timestamp()) + 300
    other = create_challenge("PBKDF2/SHA-256", 1, expires_at=expires, hmac_secret="another key")
    unsigned = create_challenge("PBKDF2/SHA-256", 1, expires_at=expires)
    with sessions.begin() as session:
        assert not accept_solution(session, settings, solved(other), datetime.now(UTC))
        assert not accept_solution(session, settings, solved(unsigned), datetime.now(UTC))
        assert not accept_solution(session, settings, "not base64 at all", datetime.now(UTC))
        assert not accept_solution(session, settings, None, datetime.now(UTC))
        assert not accept_solution(session, settings, "a" * 5000, datetime.now(UTC))
        assert not accept_solution(session, make_settings(), fresh_payload(settings), datetime.now(UTC))


def test_expired_uses_are_purged(sessions: sessionmaker) -> None:
    """Used solutions whose challenge expired are deleted at the next check"""

    settings = settings_for_accounts()
    with sessions.begin() as session:
        session.add(AltchaUse(signature_hash="0" * 64, expires_at=NOW - timedelta(minutes=1)))
        session.add(AltchaUse(signature_hash="1" * 64, expires_at=NOW + timedelta(minutes=1)))
    with sessions.begin() as session:
        accept_solution(session, settings, None, NOW)
    with sessions() as session:
        assert session.scalars(select(AltchaUse.signature_hash)).all() == ["1" * 64]


def test_sign_ups_are_limited_per_network_and_per_day(sessions: sessionmaker) -> None:
    """Thirty sign-ups from one network pass, the next one is refused and counted, without the address"""

    settings = settings_for_accounts()
    headers = {"X-Forwarded-For": "203.0.113.7"}
    answers = [check_action(sessions, settings, GuardAction.SIGN_UP, fresh_payload(settings), headers, NOW) for _ in range(31)]
    assert all(answer.ok for answer in answers[:30])
    assert (answers[30].ok, answers[30].code) == (False, "signup_limit")
    other_network = check_action(sessions, settings, GuardAction.SIGN_UP, fresh_payload(settings), {"x-forwarded-for": "198.51.100.1"}, NOW)
    assert other_network.ok
    tomorrow = check_action(sessions, settings, GuardAction.SIGN_UP, fresh_payload(settings), headers, NOW + timedelta(days=1))
    assert tomorrow.ok
    check_action(sessions, settings, GuardAction.SIGN_UP, fresh_payload(settings), headers, NOW)
    with sessions() as session:
        refusals = {row.day: row.count for row in session.scalars(select(SignupRefusal))}
    assert refusals == {NOW.date(): 2}


def test_the_limit_is_a_setting(sessions: sessionmaker, monkeypatch: pytest.MonkeyPatch) -> None:
    """MCPLAIN_SIGNUPS_PER_IP_PER_DAY sets the limit, 30 by default"""

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.delenv("MCPLAIN_SIGNUPS_PER_IP_PER_DAY", raising=False)
    assert Settings().signups_per_ip_per_day == 30
    monkeypatch.setenv("MCPLAIN_SIGNUPS_PER_IP_PER_DAY", "2")
    assert Settings().signups_per_ip_per_day == 2
    settings = settings_for_accounts(signups_per_ip_per_day=2)
    headers = {"x-forwarded-for": "203.0.113.7"}
    answers = [check_action(sessions, settings, GuardAction.SIGN_UP, fresh_payload(settings), headers, NOW).ok for _ in range(3)]
    assert answers == [True, True, False]


def test_sign_in_and_reset_are_never_limited(sessions: sessionmaker) -> None:
    """Only the creation of an account is limited: signing in and asking for a reset always pass with a valid ALTCHA"""

    settings = settings_for_accounts(signups_per_ip_per_day=1)
    headers = {"x-forwarded-for": "203.0.113.7"}
    for action in (GuardAction.SIGN_IN, GuardAction.REQUEST_PASSWORD_RESET) * 5:
        assert check_action(sessions, settings, action, fresh_payload(settings), headers, NOW).ok
    assert not check_action(sessions, settings, GuardAction.SIGN_IN, None, headers, NOW).ok
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(SignupCount)) == 0


def test_an_invalid_altcha_is_refused_before_counting(sessions: sessionmaker) -> None:
    """Without a valid ALTCHA, the guard answers altcha_invalid and counts nothing"""

    settings = settings_for_accounts(signups_per_ip_per_day=1)
    answer = check_action(sessions, settings, GuardAction.SIGN_UP, "broken", {"x-forwarded-for": "203.0.113.7"}, NOW)
    assert (answer.ok, answer.code) == (False, "altcha_invalid")
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(SignupCount)) == 0
        assert session.scalar(select(func.count()).select_from(SignupRefusal)) == 0


def guard_client(settings: Settings, peers: set[str]) -> TestClient:
    """Return a test client of the API whose counter resolves to the given addresses"""

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return TestClient(create_app(settings, engine, peer_resolver=lambda names: peers))


def test_guard_route_answers_the_counter_only() -> None:
    """The guard answers the counter; any other peer gets a plain 404"""

    settings = settings_for_accounts()
    body = {"action": "sign_in", "altcha": fresh_payload(settings), "ip_headers": {"x-forwarded-for": "203.0.113.7"}}
    allowed = guard_client(settings, {"testclient"})
    assert allowed.post("/internal/auth-guard", json=body).json() == {"ok": True}
    refused = allowed.post("/internal/auth-guard", json=body)
    assert (refused.status_code, refused.json()) == (403, {"ok": False, "code": "altcha_invalid"})
    stranger = guard_client(settings, {"172.18.0.9"})
    response = stranger.post("/internal/auth-guard", json={"action": "sign_in", "altcha": fresh_payload(settings)})
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "api.not_found", "params": {}}}


def test_guard_route_refuses_bad_bodies_and_answers_429_on_the_limit() -> None:
    """An unknown action or field is a 400; the limit is a 429 with its code"""

    settings = settings_for_accounts(signups_per_ip_per_day=1)
    client = guard_client(settings, {"testclient"})
    assert client.post("/internal/auth-guard", json={"action": "delete_user"}).status_code == 400
    assert client.post("/internal/auth-guard", json={"action": "sign_in", "extra": 1}).status_code == 400
    headers = {"x-forwarded-for": "203.0.113.7"}
    first = client.post("/internal/auth-guard", json={"action": "sign_up", "altcha": fresh_payload(settings), "ip_headers": headers})
    second = client.post("/internal/auth-guard", json={"action": "sign_up", "altcha": fresh_payload(settings), "ip_headers": headers})
    assert first.status_code == 200
    assert (second.status_code, second.json()) == (429, {"ok": False, "code": "signup_limit"})


def test_the_website_relay_cannot_reach_the_guard() -> None:
    """The site relays /api/* only: /api/internal/auth-guard does not exist on the API"""

    settings = settings_for_accounts()
    client = guard_client(settings, {"testclient"})
    for method in ("GET", "POST"):
        response = client.request(method, "/api/internal/auth-guard", json={"action": "sign_in"})
        assert response.status_code in (404, 405)


def test_challenge_route_is_never_cached() -> None:
    """GET /api/altcha/challenge gives a new challenge each time, never cached; without a key, a 503"""

    client = guard_client(settings_for_accounts(), set())
    first = client.get("/api/altcha/challenge")
    second = client.get("/api/altcha/challenge")
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    assert first.json()["parameters"]["nonce"] != second.json()["parameters"]["nonce"]
    unavailable = guard_client(make_settings(), set()).get("/api/altcha/challenge")
    assert unavailable.status_code == 503


def test_account_cookies_keep_only_ours() -> None:
    """Only the cookies of the accounts are forwarded to the counter"""

    assert account_cookies("theme=dark; mcplain.session_token=abc.def; other=1") == SESSION_COOKIE
    assert account_cookies("__Secure-mcplain.session_token=x") == "__Secure-mcplain.session_token=x"
    assert account_cookies("theme=dark") is None
    assert account_cookies(None) is None


@respx.mock
def test_current_user_reads_the_session_and_keeps_it_30_seconds() -> None:
    """The cookie is forwarded to the counter; the answer is kept 30 seconds, keyed by the fingerprint of the cookie"""

    route = respx.get(SESSION_URL).mock(
        return_value=httpx.Response(200, json={"session": {}, "user": {"id": "u1", "emailVerified": True, "role": "admin"}})
    )
    moment = [100.0]
    reader = SessionReader(make_settings(), clock=lambda: moment[0])
    assert reader.current_user(f"theme=dark; {SESSION_COOKIE}") == CurrentUser(id="u1", email_verified=True, role="admin")
    assert route.calls.last.request.headers["cookie"] == SESSION_COOKIE
    moment[0] = 129.0
    reader.current_user(SESSION_COOKIE)
    assert route.call_count == 1
    moment[0] = 131.0
    reader.current_user(SESSION_COOKIE)
    assert route.call_count == 2
    assert all(len(key) == 64 and "abc" not in key for key in reader.cache)


@respx.mock
def test_current_user_is_none_without_a_session_or_on_error() -> None:
    """No cookie, no session, an unknown role or an error of the counter: nobody, or a plain user"""

    reader = SessionReader(make_settings())
    assert reader.current_user("theme=dark") is None
    respx.get(SESSION_URL).mock(return_value=httpx.Response(200, json=None))
    assert reader.current_user(SESSION_COOKIE) is None
    respx.get(SESSION_URL).mock(return_value=httpx.Response(200, json={"user": {"id": "u2", "role": "root"}}))
    assert reader.current_user("mcplain.session_token=other") == CurrentUser(id="u2", email_verified=False, role="user")
    respx.get(SESSION_URL).mock(side_effect=httpx.ConnectError("down"))
    assert reader.current_user("mcplain.session_token=third") is None
    respx.get(SESSION_URL).mock(return_value=httpx.Response(500))
    assert reader.current_user("mcplain.session_token=fourth") is None
    assert "mcplain.session_token=fourth" not in str(reader.cache)
