"""Tests of the dials of the admin dashboard on a known set of rows: UTC days, empty days, a new month, and nothing about a person"""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import altcha_settings, make_settings
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_admin import ORIGIN, PEER, FakeDesk, FakeUsers

from mcplain_api import admin_dashboard, ai_budget, redacteur
from mcplain_api.admin_dashboard import (
    accounts_view,
    ai_view,
    analyses_view,
    parse_days,
    refusals_view,
    spend_view,
    window,
)
from mcplain_api.ai_budget import budget_reason, spent_since
from mcplain_api.app import create_app
from mcplain_api.db import (
    AI_STATE_ROW,
    AiAdminAlert,
    AiCall,
    AiState,
    AiText,
    Analysis,
    Base,
    QuotaRefusal,
    QuotaUsage,
    SignupCount,
    SignupRefusal,
    UserHistory,
    make_engine,
    make_sessions,
)

NOW = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
DASHBOARD_ROUTES: tuple[str, ...] = ("spend", "ai", "analyses", "refusals", "accounts")
PERSON_EMAIL = "carol@example.com"
PERSON_ID = "carol-account-id-0123"
IP_HASH = "f" * 64
REQUEST_ID = "req_011SECRETREQUESTID"
ALERT_REQUEST_ID = "req_011ALERTREQUESTID"
PERSONAL_KEYS: frozenset[str] = frozenset(
    {"email", "user_id", "account_id", "request_id", "ip", "ip_hash", "subject", "recipient", "input", "select"}
)


def at(text: str) -> datetime:
    """Return a moment written as 2026-12-01T09:00:00 in UTC"""

    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def call(created: str, kind: str, cost: float, reason: str | None = None, outcome: str = "answered") -> AiCall:
    """Return one logged call of the AI"""

    return AiCall(
        text_id=uuid.uuid4(),
        kind=kind,
        lang="fr",
        outcome=outcome,
        reject_reason=reason,
        cost_usd=cost,
        request_id=REQUEST_ID,
        created_at=at(created),
    )


def result(color: str, kind: str | None = None, name: str | None = None, **values: Any) -> dict[str, Any]:
    """Return the stored result of an analysis, reduced to what the dashboard reads"""

    stored: dict[str, Any] = {"status": values.pop("status", "ok"), "verdict": {"color": color, "gray_case": values.pop("gray_case", None)}}
    if kind is not None:
        stored["source"] = {"kind": kind, "name": name}
    stored.update(values)
    return stored


def analysis(created: str, state: str, stored: dict[str, Any] | None, from_cache: bool = False, error_code: str | None = None) -> Analysis:
    """Return one analysis of the queue"""

    return Analysis(
        input_raw="npx -y secret-input-of-a-person",
        state=state,
        result=stored,
        from_cache=from_cache,
        error_code=error_code,
        created_at=at(created),
        finished_at=at(created),
    )


@pytest.fixture
def engine() -> Engine:
    """Return an empty database in memory"""

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def add(engine: Engine, *rows: object) -> None:
    """Store some rows"""

    with make_sessions(engine).begin() as session:
        session.add_all(list(rows))


def read(engine: Engine) -> Session:
    """Return a session to read the dials"""

    return make_sessions(engine)()


def test_the_period_is_7_or_30_utc_days_ending_today() -> None:
    """7 and 30 are the only periods; the first day is 6 or 29 days before today"""

    assert parse_days("7") == 7
    assert parse_days("30") == 30
    for value in (None, "", "1", "31", "365", "7.0", "abc", "-7", " 7"):
        assert parse_days(value) is None
    assert window(NOW, 7) == [date(2026, 11, 25 + index) for index in range(6)] + [date(2026, 12, 1)]
    assert len(window(NOW, 30)) == 30
    assert window(NOW, 30)[0] == date(2026, 11, 2)


def test_the_spend_counts_each_utc_day_and_the_month_starts_again(engine: Engine) -> None:
    """Today and the month come from the function of the fuses; each day and each kind of text are added up"""

    add(
        engine,
        call("2026-12-01T09:00:00", "notice", 0.01),
        call("2026-12-01T00:00:00", "translation", 0.02),
        call("2026-11-30T23:59:59.999999", "notice", 0.03),
        call("2026-11-30T12:00:00", "notice", 0.0, outcome="unavailable"),
        call("2026-11-20T12:00:00", "notice", 0.5),
        call("2026-10-01T12:00:00", "notice", 1.0),
    )
    settings = make_settings(ai_monthly_budget_usd=10)
    with read(engine) as session:
        week = spend_view(session, settings, NOW, 7)
        month = spend_view(session, settings, NOW, 30)
    assert week["today_usd"] == pytest.approx(0.03)
    assert week["month_usd"] == pytest.approx(0.03)
    assert week["daily_fuse_usd"] == pytest.approx(0.5)
    assert week["monthly_budget_usd"] == pytest.approx(10)
    assert week["fuse_reached"] is False
    assert week["budget_reached"] is False
    days = {item["day"]: item for item in week["per_day"]}
    assert list(days) == [day.isoformat() for day in window(NOW, 7)]
    assert days["2026-12-01"] == {
        "day": "2026-12-01",
        "cost_usd": pytest.approx(0.03),
        "notice_usd": pytest.approx(0.01),
        "translation_usd": pytest.approx(0.02),
        "paid_calls": 2,
    }
    assert days["2026-11-30"]["cost_usd"] == pytest.approx(0.03)
    assert days["2026-11-30"]["paid_calls"] == 1
    assert days["2026-11-27"] == {"day": "2026-11-27", "cost_usd": 0.0, "notice_usd": 0.0, "translation_usd": 0.0, "paid_calls": 0}
    assert week["paid_calls"] == 3
    assert week["by_kind"] == {"notice": pytest.approx(0.04), "translation": pytest.approx(0.02)}
    assert month["paid_calls"] == 4
    assert month["by_kind"]["notice"] == pytest.approx(0.54)
    assert month["month_usd"] == pytest.approx(0.03)


def test_the_dashboard_and_the_fuses_read_the_same_spend(engine: Engine) -> None:
    """One function gives what was spent: the dashboard, the writer and the balance all use spent_since of ai_budget"""

    assert admin_dashboard.spent_since is ai_budget.spent_since
    assert redacteur.budget_reason is ai_budget.budget_reason
    assert redacteur.calls_today is ai_budget.calls_today
    for name in ("_spent_since", "_budget_reason", "_calls_today", "worst_cost"):
        assert not hasattr(redacteur.Redacteur, name)
    add(engine, call("2026-12-01T08:00:00", "notice", 0.2), call("2026-12-01T09:00:00", "translation", 0.25))
    with read(engine) as session:
        view = spend_view(session, make_settings(ai_daily_fuse_usd=0.5), NOW, 7)
        assert view["today_usd"] == pytest.approx(spent_since(session, ai_budget.day_start(NOW)))
        assert budget_reason(session, make_settings(ai_daily_fuse_usd=0.5), 0.04, NOW) is None
        assert budget_reason(session, make_settings(ai_daily_fuse_usd=0.5), 0.06, NOW) is not None
        reached = spend_view(session, make_settings(ai_daily_fuse_usd=0.45), NOW, 7)
    assert view["today_usd"] == pytest.approx(0.45)
    assert reached["fuse_reached"] is True


def test_the_ai_dial_counts_the_refusals_per_reason_and_the_encoding_rate(engine: Engine) -> None:
    """Refusals per code and per day; the rate is the encoding refusals of notices over the paid notice calls"""

    add(
        engine,
        call("2026-12-01T09:00:00", "notice", 0.01, "encoding"),
        call("2026-12-01T09:00:01", "notice", 0.01),
        call("2026-12-01T09:30:00", "notice", 0.01, "forbidden_word"),
        call("2026-11-30T23:59:59", "notice", 0.01, "encoding"),
        call("2026-11-30T10:00:00", "translation", 0.01, "encoding"),
        call("2026-11-30T11:00:00", "notice", 0.0, outcome="unavailable"),
        call("2026-11-01T11:00:00", "notice", 0.01, "encoding"),
        AiAdminAlert(code="usage_limit", created_at=at("2026-11-30T08:00:00"), details={"kind": "notice", "status": 400, "request_id": ALERT_REQUEST_ID}),
        AiAdminAlert(code="auth_refused", created_at=at("2026-12-01T08:00:00"), details={"kind": "x", "status": "401"}),
        AiAdminAlert(code="bad_request", created_at=at("2026-10-01T08:00:00"), details=None),
        AiText(kind="notice", lang="fr", hash="a" * 64, prompt_version="v", model="m", status="rejected", reject_reason="link", updated_at=at("2026-12-01T07:00:00")),
        AiText(kind="translation", lang="fr", hash="b" * 64, prompt_version="v", model="m", status="failed", reject_reason="encoding", updated_at=at("2026-11-29T07:00:00")),
        AiText(kind="notice", lang="en", hash="c" * 64, prompt_version="v", model="m", status="ready", updated_at=at("2026-12-01T07:00:00")),
        AiText(kind="notice", lang="en", hash="d" * 64, prompt_version="v", model="m", status="paused", reject_reason="daily_fuse", updated_at=at("2026-12-01T06:00:00")),
    )
    with read(engine) as session:
        week = ai_view(session, NOW, 7)
    days = {item["day"]: item["reasons"] for item in week["per_day"]}
    assert days["2026-12-01"] == {"encoding": 1, "forbidden_word": 1}
    assert days["2026-11-30"] == {"encoding": 2}
    assert days["2026-11-29"] == {}
    assert week["reasons"] == {"encoding": 3, "forbidden_word": 1}
    assert week["encoding"] == {"rejected": 2, "paid_notice_calls": 4, "rate": pytest.approx(0.5)}
    assert [alert["code"] for alert in week["alerts"]] == ["auth_refused", "usage_limit"]
    assert week["alerts"][0]["kind"] is None
    assert week["alerts"][0]["status"] is None
    assert week["alerts"][1]["kind"] == "notice"
    assert week["alerts"][1]["status"] == 400
    assert [(text["kind"], text["status"], text["reject_reason"]) for text in week["texts"]] == [
        ("notice", "rejected", "link"),
        ("notice", "paused", "daily_fuse"),
        ("translation", "failed", "encoding"),
    ]


def test_the_encoding_rate_is_empty_without_paid_notice(engine: Engine) -> None:
    """No paid notice call: no rate, never a division by zero"""

    with read(engine) as session:
        view = ai_view(session, NOW, 30)
    assert view["encoding"] == {"rejected": 0, "paid_notice_calls": 0, "rate": None}
    assert all(item["reasons"] == {} for item in view["per_day"])
    assert view["writer"] == {"disabled_reason": None, "paused_until": None}


def test_the_analyses_dial_counts_colors_gray_cases_languages_failures_and_the_top(engine: Engine) -> None:
    """Analyses per UTC day, served by the cache or new; failures by code with the token given back or kept"""

    first = analysis("2026-11-30T23:59:59", "done", result("green", "npm", "pkg-a"))
    last = analysis("2026-12-01T00:00:00", "done", result("green", "npm", "pkg-a"), from_cache=True)
    add(
        engine,
        first,
        last,
        analysis("2026-12-01T01:00:00", "done", result("gray", "pypi", "pkg-b", gray_case="no_tools_found")),
        analysis("2026-12-01T02:00:00", "done", result("gray", "github", "owner/go-server", status="unsupported_language", language="go", gray_case="unsupported_language")),
        analysis("2026-12-01T03:00:00", "done", result("red", "npm", "@scope/pkg-c")),
        analysis("2026-12-01T04:00:00", "failed", result("gray", gray_case="error", error={"code": "fetch.npm_not_found"}), error_code="fetch_error"),
        analysis("2026-12-01T05:00:00", "failed", None, error_code="atelier_timeout"),
        analysis("2026-12-01T06:00:00", "quota_exhausted", None),
        analysis("2026-12-01T07:00:00", "queued", None),
        analysis("2026-11-20T07:00:00", "done", result("orange", "npm", "pkg-old")),
    )
    with read(engine) as session:
        week = analyses_view(session, NOW, 7)
        month = analyses_view(session, NOW, 30)
    days = {item["day"]: item for item in week["per_day"]}
    assert days["2026-12-01"] == {"day": "2026-12-01", "total": 6, "cached": 1, "new": 5}
    assert days["2026-11-30"] == {"day": "2026-11-30", "total": 1, "cached": 0, "new": 1}
    assert days["2026-11-29"] == {"day": "2026-11-29", "total": 0, "cached": 0, "new": 0}
    assert week["colors"] == {"red": 1, "orange": 0, "gray": 4, "green": 2}
    assert week["gray_cases"] == [
        {"code": "error", "count": 2},
        {"code": "no_tools_found", "count": 1},
        {"code": "unsupported_language", "count": 1},
    ]
    assert week["languages"] == [{"code": "go", "count": 1}]
    assert week["failures"] == [
        {"code": "atelier_timeout", "count": 1, "refund": "give_back"},
        {"code": "fetch.npm_not_found", "count": 1, "refund": "keep"},
    ]
    assert week["top"][0] == {"kind": "npm", "name": "pkg-a", "count": 2, "last_analysis_id": str(last.id)}
    assert {item["name"] for item in week["top"]} == {"pkg-a", "pkg-b", "owner/go-server", "@scope/pkg-c"}
    assert month["colors"]["orange"] == 1
    assert "pkg-old" in {item["name"] for item in month["top"]}


def test_the_top_keeps_20_lines(engine: Engine) -> None:
    """At most 20 MCP, the most analyzed first"""

    rows = [analysis("2026-12-01T01:00:00", "done", result("green", "npm", f"pkg-{index:02d}")) for index in range(25)]
    rows += [analysis("2026-12-01T02:00:00", "done", result("green", "npm", "pkg-24")) for _ in range(3)]
    add(engine, *rows)
    with read(engine) as session:
        view = analyses_view(session, NOW, 7)
    assert len(view["top"]) == 20
    assert view["top"][0]["name"] == "pkg-24"
    assert view["top"][0]["count"] == 4


def test_the_refusals_dial_counts_sign_ups_and_used_up_quotas_per_day(engine: Engine) -> None:
    """signup_limit and each kind of quota_exhausted, per day, zero on the empty days"""

    add(
        engine,
        SignupRefusal(day=date(2026, 12, 1), count=3),
        SignupRefusal(day=date(2026, 11, 1), count=9),
        QuotaRefusal(day=date(2026, 12, 1), kind="anonymous", count=2),
        QuotaRefusal(day=date(2026, 11, 28), kind="account", count=1),
    )
    with read(engine) as session:
        week = refusals_view(session, NOW, 7)
    assert week["kinds"] == ["signup_limit", "quota_exhausted_anonymous", "quota_exhausted_account"]
    days = {item["day"]: item["counts"] for item in week["per_day"]}
    assert days["2026-12-01"] == {"signup_limit": 3, "quota_exhausted_anonymous": 2, "quota_exhausted_account": 0}
    assert days["2026-11-28"] == {"signup_limit": 0, "quota_exhausted_anonymous": 0, "quota_exhausted_account": 1}
    assert days["2026-11-26"] == {"signup_limit": 0, "quota_exhausted_anonymous": 0, "quota_exhausted_account": 0}
    assert week["totals"] == {"signup_limit": 3, "quota_exhausted_anonymous": 2, "quota_exhausted_account": 1}


def test_the_accounts_dial_fills_the_days_the_counter_did_not_give() -> None:
    """Every day of the period is there; the counter not answering gives no dial"""

    desk = FakeDesk()
    desk.created = {"2026-12-01": 4, "2026-11-25": 1, "2026-10-01": 7}
    view = accounts_view(desk, NOW, 7)
    assert view is not None
    assert [item["count"] for item in view["per_day"]] == [1, 0, 0, 0, 0, 0, 4]
    assert view["total"] == 5
    desk.created = None
    assert accounts_view(desk, NOW, 7) is None


@pytest.fixture
def admin_client(engine: Engine) -> Iterator[tuple[TestClient, dict[str, str], FakeDesk]]:
    """Return a test client of the API, the cookie of an admin with its second factor, and the fake counter"""

    users = FakeUsers()
    desk = FakeDesk()
    settings = altcha_settings(public_url=ORIGIN)
    app = create_app(settings, engine, peer_resolver=lambda names: {PEER}, user_reader=users, account_desk=desk)
    _, headers = users.add("admin", two_factor=True)
    with TestClient(app) as client:
        yield client, headers, desk


def test_every_dial_route_asks_for_7_or_30_days(admin_client: tuple[TestClient, dict[str, str], FakeDesk]) -> None:
    """days=7 and days=30 answer, anything else is 400, and no answer is kept by a cache"""

    client, headers, _ = admin_client
    for name in DASHBOARD_ROUTES:
        path = "/api/admin/dashboard/" + name
        for days in ("7", "30"):
            answer = client.get(path, params={"days": days}, headers=headers)
            assert answer.status_code == 200, (name, days)
            assert answer.headers["cache-control"] == "no-store"
            assert answer.json()["days"] == int(days)
        for days in ("1", "31", "abc", "7.0", ""):
            answer = client.get(path, params={"days": days}, headers=headers)
            assert answer.status_code == 400, (name, days)
            assert answer.json()["error"]["code"] == "api.invalid_days"
        assert client.get(path, headers=headers).status_code == 400


def test_the_accounts_dial_says_when_the_counter_does_not_answer(admin_client: tuple[TestClient, dict[str, str], FakeDesk]) -> None:
    """The counter down gives 503, never an empty dial that would look like no sign-up"""

    client, headers, desk = admin_client
    desk.created = None
    answer = client.get("/api/admin/dashboard/accounts", params={"days": "7"}, headers=headers)
    assert answer.status_code == 503
    assert answer.json()["error"]["code"] == "api.guichet_unavailable"


def keys_of(value: object) -> set[str]:
    """Return every key of every object inside a JSON value"""

    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            found |= keys_of(item)
    if isinstance(value, list):
        for item in value:
            found |= keys_of(item)
    return found


def test_no_dial_ever_tells_anything_about_a_person(engine: Engine, admin_client: tuple[TestClient, dict[str, str], FakeDesk]) -> None:
    """No e-mail, no account id, no address fingerprint, no request id, no pasted link, in any answer of the dials"""

    client, headers, desk = admin_client
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    done = Analysis(
        id=uuid.uuid4(),
        input_raw="npx -y secret-input-of-a-person",
        state="done",
        result=result("green", "npm", "pkg-a"),
        created_at=now,
        finished_at=now,
    )
    add(
        engine,
        done,
        AiCall(text_id=uuid.uuid4(), kind="notice", lang="fr", outcome="answered", reject_reason="encoding", cost_usd=0.01, request_id=REQUEST_ID, created_at=now),
        AiAdminAlert(code="usage_limit", created_at=now, details={"kind": "notice", "status": 400, "request_id": ALERT_REQUEST_ID}),
        AiState(id=AI_STATE_ROW, paused_until=None, disabled_reason=None),
        QuotaUsage(day=today.date(), subject="ip:" + IP_HASH, kind="anonymous", count=3),
        QuotaUsage(day=today.date(), subject="user:" + PERSON_ID, kind="account", count=1),
        QuotaRefusal(day=today.date(), kind="anonymous", count=1),
        SignupCount(day=today.date(), ip_hash=IP_HASH, count=30),
        SignupRefusal(day=today.date(), count=1),
        UserHistory(user_id=PERSON_ID, analysis_id=done.id, created_at=now),
    )
    add(
        engine,
        AiText(kind="notice", lang="fr", hash="a" * 64, prompt_version="v", model="m", status="rejected", reject_reason="link", request_id=REQUEST_ID, analysis_id=done.id, updated_at=now),
    )
    desk.created = {today.date().isoformat(): 2}
    for name in DASHBOARD_ROUTES:
        for days in ("7", "30"):
            answer = client.get("/api/admin/dashboard/" + name, params={"days": days}, headers=headers)
            assert answer.status_code == 200, name
            text = answer.text
            for secret in (PERSON_EMAIL, PERSON_ID, IP_HASH, REQUEST_ID, ALERT_REQUEST_ID, "secret-input-of-a-person", "req_"):
                assert secret not in text, (name, secret)
            assert not keys_of(answer.json()) & PERSONAL_KEYS, name
