"""Tests of the quotas, the burst limit, ALTCHA on the analyses, the history and the erase route, with SQLite"""

import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from helpers import altcha_headers, altcha_settings, post_analysis
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from mcplain_api.analysis_gate import enqueue
from mcplain_api.app import create_app
from mcplain_api.db import (
    Analysis,
    AnalysisState,
    AnalysisToken,
    Base,
    BurstCount,
    IpSalt,
    QuotaRefusal,
    QuotaUsage,
    UserHistory,
    make_engine,
    make_sessions,
)
from mcplain_api.ip_fingerprint import purge_old_fingerprints
from mcplain_api.quota import Visitor, VisitorKind, burst_wait, next_reset, refund_token, take_token
from mcplain_api.session_user import CurrentUser
from mcplain_api.settings import Settings

FETCH = {"input": "uvx mcp-server-fetch"}
COUNTER_PEER = "172.20.0.9"


class FakeUsers:
    """Class that stands for the counter: a cookie names a user, anything else is nobody"""

    def __init__(self) -> None:
        """Start without any signed-in user"""

        self.users: dict[str, CurrentUser] = {}

    def add(self, role: str = "user") -> dict[str, str]:
        """Sign in a new user and return the Cookie header of its session"""

        user = CurrentUser(id=uuid.uuid4().hex, email_verified=True, role=role)
        cookie = f"mcplain.session_token={user.id}"
        self.users[cookie] = user
        return {"Cookie": cookie}

    def id_of(self, headers: dict[str, str]) -> str:
        """Return the id of the user of a Cookie header"""

        return self.users[headers["Cookie"]].id

    def current_user(self, cookie_header: str | None) -> CurrentUser | None:
        """Return the user of a cookie"""

        if cookie_header is None:
            return None
        return self.users.get(cookie_header)


@pytest.fixture
def sessions() -> sessionmaker:
    """Return sessions on a fresh in-memory database"""

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_sessions(engine)


@pytest.fixture
def users() -> FakeUsers:
    """Return a fake counter without users"""

    return FakeUsers()


def build_client(sessions: sessionmaker, users: FakeUsers, **values: object) -> TestClient:
    """Return a test client of the API on the test database, with the fake counter and the counter as peer"""

    settings = altcha_settings(**values)
    app = create_app(settings, sessions.kw["bind"], peer_resolver=lambda names: {COUNTER_PEER}, user_reader=users)
    return TestClient(app)


@pytest.fixture
def client(sessions: sessionmaker, users: FakeUsers) -> Iterator[TestClient]:
    """Return a test client with the default quotas"""

    with build_client(sessions, users) as test_client:
        yield test_client


def from_network(address: str, left: str | None = None) -> dict[str, str]:
    """Return the X-Forwarded-For our relay would write for a visitor, with what a browser may have written on the left"""

    value = address
    if left is not None:
        value = f"{left}, {address}"
    return {"X-Forwarded-For": value}


def count(sessions: sessionmaker, table: type[Base]) -> int:
    """Return the number of rows of a table"""

    with sessions() as session:
        return session.scalar(select(func.count()).select_from(table)) or 0


def row_of(sessions: sessionmaker, identifier: str) -> Analysis:
    """Read one analysis back"""

    with sessions() as session:
        row = session.get(Analysis, uuid.UUID(identifier))
    assert row is not None
    return row


def test_without_account_three_new_analyses_a_day_then_cache_only(client: TestClient, sessions: sessionmaker) -> None:
    """Three analyses take a token each; the fourth is created cache-only, without token, and counted as such"""

    network = from_network("203.0.113.7")
    answers = [post_analysis(client, FETCH, network) for _ in range(4)]
    assert [answer.status_code for answer in answers] == [202, 202, 202, 202]
    assert [answer.json()["cache_only"] for answer in answers] == [False, False, False, True]
    assert row_of(sessions, answers[3].json()["id"]).cache_only
    assert count(sessions, AnalysisToken) == 3
    quota = client.get("/api/quota", headers=network).json()
    assert (quota["kind"], quota["limit"], quota["used"], quota["remaining"]) == ("anonymous", 3, 3, 0)
    with sessions() as session:
        assert session.scalar(select(QuotaRefusal.count).where(QuotaRefusal.kind == "anonymous")) == 1
    other = client.get("/api/quota", headers=from_network("198.51.100.4")).json()
    assert other["remaining"] == 3


def test_an_account_has_ten_whatever_its_network(client: TestClient, users: FakeUsers) -> None:
    """An account counts on its own: ten a day, even from a network that used its three"""

    network = from_network("203.0.113.7")
    for _ in range(3):
        post_analysis(client, FETCH, network)
    account = {**users.add(), **network}
    answers = [post_analysis(client, FETCH, account).json()["cache_only"] for _ in range(11)]
    assert answers == [False] * 10 + [True]
    quota = client.get("/api/quota", headers=account).json()
    assert (quota["kind"], quota["limit"], quota["used"], quota["remaining"]) == ("account", 10, 10, 0)


def test_the_admin_has_no_quota_nor_burst_limit(client: TestClient, users: FakeUsers, sessions: sessionmaker) -> None:
    """The admin never takes a token, is never cache-only, and is not stopped by the burst limit"""

    admin = {**users.add("admin"), **from_network("203.0.113.7")}
    answers = [post_analysis(client, FETCH, admin) for _ in range(35)]
    assert {answer.status_code for answer in answers} == {202}
    assert not any(answer.json()["cache_only"] for answer in answers)
    assert count(sessions, AnalysisToken) == 0
    quota = client.get("/api/quota", headers=admin).json()
    assert (quota["kind"], quota["limit"], quota["remaining"]) == ("admin", None, None)


def test_the_bench_role_is_a_normal_account_unless_the_setting_allows_it(sessions: sessionmaker, users: FakeUsers) -> None:
    """Without MCPLAIN_ALLOW_BENCH_ROLE a bench account has ten; with it, no quota and no burst limit, but ALTCHA still"""

    bench = {**users.add("bench"), **from_network("203.0.113.7")}
    with build_client(sessions, users) as client:
        answers = [post_analysis(client, FETCH, bench).json()["cache_only"] for _ in range(11)]
        assert answers == [False] * 10 + [True]
        assert client.get("/api/quota", headers=bench).json()["kind"] == "account"
    with build_client(sessions, users, allow_bench_role=True) as client:
        answers = [post_analysis(client, FETCH, bench) for _ in range(35)]
        assert {answer.status_code for answer in answers} == {202}
        assert not any(answer.json()["cache_only"] for answer in answers)
        quota = client.get("/api/quota", headers=bench).json()
        assert (quota["kind"], quota["limit"]) == ("bench", None)
        refused = client.post("/api/analyses", json=FETCH, headers=bench)
        assert (refused.status_code, refused.json()["error"]["code"]) == (403, "altcha_invalid")


def test_burst_limit_is_thirty_an_hour_per_network(client: TestClient, sessions: sessionmaker) -> None:
    """The 31st request of the hour from one network is refused with 429, its code, and Retry-After"""

    network = from_network("203.0.113.7")
    for _ in range(30):
        assert post_analysis(client, FETCH, network).status_code == 202
    refused = client.post("/api/analyses", json=FETCH, headers=network)
    assert refused.status_code == 429
    error = refused.json()["error"]
    assert error["code"] == "burst_limit"
    retry_after = int(refused.headers["Retry-After"])
    assert 1 <= retry_after <= 3600
    assert error["params"] == {"retry_after": str(retry_after), "minutes": str(-(-retry_after // 60))}
    assert post_analysis(client, FETCH, from_network("198.51.100.4")).status_code == 202


def test_a_class_of_25_accounts_on_one_network_is_not_stopped(client: TestClient, users: FakeUsers) -> None:
    """The burst limit of an account is kept per account: 25 accounts asking twice from one network all pass"""

    network = from_network("203.0.113.7")
    accounts = [{**users.add(), **network} for _ in range(25)]
    statuses = {post_analysis(client, FETCH, account).status_code for account in accounts for _ in range(2)}
    assert statuses == {202}


def test_a_fake_forwarded_for_does_not_reset_the_counters(client: TestClient) -> None:
    """What the browser writes on the left of X-Forwarded-For is ignored: the quota and the burst stay the same"""

    answers = [post_analysis(client, FETCH, from_network("203.0.113.7", f"6.6.6.{n}")) for n in range(4)]
    assert [answer.json()["cache_only"] for answer in answers] == [False, False, False, True]
    for n in range(26):
        post_analysis(client, FETCH, from_network("203.0.113.7", f"7.7.7.{n}"))
    assert client.post("/api/analyses", json=FETCH, headers=from_network("203.0.113.7", "8.8.8.8")).status_code == 429


def test_altcha_is_asked_for_each_analysis_and_a_replay_is_refused(client: TestClient, sessions: sessionmaker) -> None:
    """No solution, a wrong one or a solution used once more gives 403 altcha_invalid, and nothing is created"""

    missing = client.post("/api/analyses", json=FETCH)
    wrong = client.post("/api/analyses", json=FETCH, headers={"x-altcha": "bm90IGEgc29sdXRpb24="})
    solution = altcha_headers(client)
    first = client.post("/api/analyses", json=FETCH, headers=solution)
    replay = client.post("/api/analyses", json=FETCH, headers=solution)
    assert [missing.status_code, wrong.status_code, first.status_code, replay.status_code] == [403, 403, 202, 403]
    assert {answer.json()["error"]["code"] for answer in (missing, wrong, replay)} == {"altcha_invalid"}
    assert count(sessions, Analysis) == 1


def test_checks_come_in_order_format_burst_altcha_input(client: TestClient, sessions: sessionmaker) -> None:
    """A wrong format is refused before the burst counts; the burst before ALTCHA; ALTCHA before the input"""

    network = from_network("203.0.113.7")
    assert client.post("/api/analyses", content="{", headers={"Content-Type": "text/plain", **network}).status_code == 415
    assert client.post("/api/analyses", content="{", headers={"Content-Type": "application/json", **network}).status_code == 400
    assert count(sessions, BurstCount) == 0
    unsolved = client.post("/api/analyses", json={"input": "pip install requests"}, headers=network)
    assert (unsolved.status_code, unsolved.json()["error"]["code"]) == (403, "altcha_invalid")
    invalid = post_analysis(client, {"input": "pip install requests"}, network)
    assert (invalid.status_code, invalid.json()["error"]["code"]) == (400, "input.unexpected_arguments")
    for _ in range(28):
        post_analysis(client, FETCH, network)
    blocked = client.post("/api/analyses", json={"input": "pip install requests"}, headers=network)
    assert blocked.status_code == 429


def test_refused_requests_take_no_token(sessions: sessionmaker, users: FakeUsers) -> None:
    """An invalid input (400) or a full queue (503) leaves the quota untouched"""

    network = from_network("203.0.113.7")
    with build_client(sessions, users, max_queued=1) as client:
        assert post_analysis(client, {"input": "pip install requests"}, network).status_code == 400
        assert post_analysis(client, FETCH, network).status_code == 202
        assert post_analysis(client, FETCH, network).status_code == 503
        assert client.get("/api/quota", headers=network).json()["used"] == 1


def test_quota_view_counts_nothing_and_gives_the_next_midnight_utc(client: TestClient, sessions: sessionmaker) -> None:
    """GET /api/quota asks no ALTCHA, counts no burst, takes no token, and says when the analyses come back"""

    network = from_network("203.0.113.7")
    for _ in range(40):
        assert client.get("/api/quota", headers=network).status_code == 200
    quota = client.get("/api/quota", headers=network).json()
    assert (quota["used"], quota["remaining"]) == (0, 3)
    resets_at = datetime.fromisoformat(quota["resets_at"])
    now = datetime.now(UTC)
    assert resets_at.utcoffset() == timedelta(0)
    assert (resets_at.hour, resets_at.minute, resets_at.second) == (0, 0, 0)
    assert timedelta(0) < resets_at - now <= timedelta(days=1)
    assert count(sessions, BurstCount) == 0
    assert next_reset(datetime(2026, 11, 12, 23, 59, 59, tzinfo=UTC)) == datetime(2026, 11, 13, tzinfo=UTC)


def test_notice_and_translation_never_read_nor_touch_the_quotas(client: TestClient, sessions: sessionmaker) -> None:
    """Asking for a notice or a translation counts nothing, asks no ALTCHA, and works even with the quota used up"""

    network = from_network("203.0.113.7")
    for _ in range(3):
        post_analysis(client, FETCH, network)
    identifier = post_analysis(client, FETCH, network).json()["id"]
    before = (count(sessions, QuotaUsage), count(sessions, BurstCount), count(sessions, AnalysisToken))
    with sessions() as session:
        burst_before = session.scalar(select(func.sum(BurstCount.count)))
    for kind in ("notice", "translation"):
        for _ in range(5):
            answer = client.post(f"/api/analyses/{identifier}/{kind}", json={"lang": "fr"}, headers=network)
            assert answer.status_code == 409
            assert client.get(f"/api/analyses/{identifier}/{kind}?lang=fr", headers=network).status_code == 409
    after = (count(sessions, QuotaUsage), count(sessions, BurstCount), count(sessions, AnalysisToken))
    with sessions() as session:
        burst_after = session.scalar(select(func.sum(BurstCount.count)))
    assert before == after
    assert burst_before == burst_after
    assert client.get("/api/quota", headers=network).json()["used"] == 3


def test_take_token_is_atomic_under_simultaneous_requests(tmp_path: Path) -> None:
    """Five requests at the same moment with three tokens left give exactly three counted analyses"""

    engine = make_engine(f"sqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(engine)
    sessions = make_sessions(engine)
    settings = altcha_settings(max_queued=100)
    visitor = Visitor(VisitorKind.ANONYMOUS, "ip:" + "a" * 64, None)
    barrier = threading.Barrier(5)
    created: list[bool] = []
    errors: list[BaseException] = []

    def ask() -> None:
        """Wait for the others, then ask for an analysis"""

        try:
            barrier.wait()
            created.append(enqueue(sessions, settings, visitor, FETCH["input"], None, datetime.now(UTC)).cache_only)
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=ask) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert sorted(created) == [False, False, False, True, True]
    with sessions() as session:
        assert session.scalar(select(QuotaUsage.count)) == 3
        assert session.scalar(select(func.count()).select_from(AnalysisToken)) == 3
    engine.dispose()


def test_a_token_is_given_back_only_once(sessions: sessionmaker) -> None:
    """refund_token marks the token: a second call changes nothing"""

    visitor = Visitor(VisitorKind.ANONYMOUS, "ip:" + "b" * 64, None)
    moment = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
    created = enqueue(sessions, altcha_settings(), visitor, FETCH["input"], None, moment)
    with sessions.begin() as session:
        assert refund_token(session, created.id, moment)
    with sessions.begin() as session:
        assert not refund_token(session, created.id, moment)
    with sessions() as session:
        assert session.scalar(select(QuotaUsage.count)) == 0


def test_take_token_stops_exactly_at_the_limit(sessions: sessionmaker) -> None:
    """Under the limit a token is taken, at the limit none, and another day starts again"""

    visitor = Visitor(VisitorKind.ACCOUNT, "user:demo", "demo")
    day = datetime(2026, 11, 12, tzinfo=UTC).date()
    with sessions.begin() as session:
        taken = [take_token(session, day, visitor, 2) for _ in range(3)]
        assert taken == [True, True, False]
        assert take_token(session, day + timedelta(days=1), visitor, 2)


def test_burst_wait_slides_over_one_hour(sessions: sessionmaker) -> None:
    """The hour slides: once the oldest minute is out, a new request passes again"""

    start = datetime(2026, 11, 12, 10, 0, 30, tzinfo=UTC)
    with sessions.begin() as session:
        assert burst_wait(session, "ip:x", start, 2) is None
        assert burst_wait(session, "ip:x", start + timedelta(minutes=10), 2) is None
        wait = burst_wait(session, "ip:x", start + timedelta(minutes=20), 2)
        assert wait == 40 * 60 - 30
        assert burst_wait(session, "ip:x", start + timedelta(minutes=61), 2) is None


def test_quota_rows_and_tokens_go_with_the_salt_after_two_days(sessions: sessionmaker) -> None:
    """The fingerprinted rows of the quotas and the tokens are deleted on the same rhythm as the salt"""

    old = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
    visitor = Visitor(VisitorKind.ANONYMOUS, "ip:" + "c" * 64, None)
    enqueue(sessions, altcha_settings(), visitor, FETCH["input"], None, old)
    with sessions.begin() as session:
        session.add(IpSalt(day=old.date(), salt="d" * 64))
    with sessions.begin() as session:
        purge_old_fingerprints(session, old + timedelta(days=1))
    assert count(sessions, QuotaUsage) == 1
    with sessions.begin() as session:
        purge_old_fingerprints(session, old + timedelta(days=2))
    assert (count(sessions, QuotaUsage), count(sessions, AnalysisToken), count(sessions, IpSalt)) == (0, 0, 0)


def test_history_keeps_every_request_of_an_account_cache_included(client: TestClient, users: FakeUsers, sessions: sessionmaker) -> None:
    """Each request of an account is in its history, the newest first; the same input within a minute is kept once"""

    account = users.add()
    first = post_analysis(client, FETCH, account).json()["id"]
    post_analysis(client, FETCH, account)
    second = post_analysis(client, {"input": "npx -y @modelcontextprotocol/server-filesystem"}, account).json()["id"]
    with sessions.begin() as session:
        row = session.get(Analysis, uuid.UUID(first))
        assert row is not None
        row.state = AnalysisState.DONE.value
        row.from_cache = True
        row.result = {"status": "ok", "verdict": {"color": "orange"}}
    entries = client.get("/api/account/history", headers=account).json()["entries"]
    assert [entry["id"] for entry in entries] == [second, first]
    assert entries[1]["input"] == FETCH["input"]
    assert (entries[1]["color"], entries[1]["status"], entries[1]["from_cache"]) == ("orange", "ok", True)
    assert (entries[0]["color"], entries[0]["state"]) == (None, "queued")
    assert set(entries[0]) == {"date", "id", "input", "select", "state", "color", "status", "from_cache"}
    anonymous = post_analysis(client, FETCH)
    assert anonymous.status_code == 202
    assert count(sessions, UserHistory) == 2


def test_history_never_shows_a_used_up_quota(client: TestClient, users: FakeUsers, sessions: sessionmaker) -> None:
    """A cache-only request that ended on quota_exhausted is not in the history"""

    account = users.add()
    identifier = post_analysis(client, FETCH, account).json()["id"]
    with sessions.begin() as session:
        row = session.get(Analysis, uuid.UUID(identifier))
        assert row is not None
        row.state = AnalysisState.QUOTA_EXHAUSTED.value
    assert client.get("/api/account/history", headers=account).json()["entries"] == []
    view = client.get(f"/api/analyses/{identifier}").json()
    assert (view["state"], view["result"]) == ("quota_exhausted", None)


def test_history_can_be_deleted_and_needs_an_account(client: TestClient, users: FakeUsers, sessions: sessionmaker) -> None:
    """Without account the history routes answer 401; DELETE removes the history of this account only"""

    assert client.get("/api/account/history").status_code == 401
    assert client.delete("/api/account/history").json()["error"]["code"] == "api.sign_in_required"
    first, second = users.add(), users.add()
    post_analysis(client, FETCH, first)
    post_analysis(client, FETCH, second)
    assert client.delete("/api/account/history", headers=first).json() == {"deleted": 1}
    assert client.get("/api/account/history", headers=first).json()["entries"] == []
    assert len(client.get("/api/account/history", headers=second).json()["entries"]) == 1


def erase(sessions: sessionmaker, users: FakeUsers, user_id: str, peer: str) -> int:
    """Call the erase route as if from one peer address"""

    settings: Settings = altcha_settings()
    app = create_app(settings, sessions.kw["bind"], peer_resolver=lambda names: {COUNTER_PEER}, user_reader=users)
    with TestClient(app, client=(peer, 50000)) as test_client:
        return test_client.post("/internal/account-erase", json={"user_id": user_id}).status_code


def test_the_counter_erases_history_and_quota_of_a_deleted_account(client: TestClient, users: FakeUsers, sessions: sessionmaker) -> None:
    """Only the counter may call the erase route; it removes the history, the quota rows, the tokens and the burst counts"""

    gone, kept = users.add(), users.add()
    for account in (gone, kept):
        post_analysis(client, FETCH, account)
    assert erase(sessions, users, users.id_of(gone), "203.0.113.7") == 404
    assert count(sessions, UserHistory) == 2
    assert erase(sessions, users, users.id_of(gone), COUNTER_PEER) == 200
    with sessions() as session:
        assert session.scalars(select(UserHistory.user_id)).all() == [users.id_of(kept)]
        subjects = {f"user:{users.id_of(kept)}"}
        assert set(session.scalars(select(QuotaUsage.subject)).all()) == subjects
        assert set(session.scalars(select(AnalysisToken.subject)).all()) == subjects
        assert set(session.scalars(select(BurstCount.subject)).all()) == subjects
