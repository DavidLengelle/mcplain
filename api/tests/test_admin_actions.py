"""Tests of the actions of the admin: ask a text again under every fuse, analyze again, mark an alert, and the journal"""

import json
import uuid
from collections.abc import Iterator
from datetime import timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from helpers import altcha_settings, lamps_of, report, tool_report
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from test_admin import ORIGIN, PEER, FakeDesk, FakeUsers

from mcplain_api.ai_client import API_URL
from mcplain_api.app import create_app
from mcplain_api.db import (
    AI_STATE_ROW,
    AdminAction,
    AiAdminAlert,
    AiCall,
    AiState,
    AiText,
    Analysis,
    Base,
    make_engine,
    make_sessions,
    utc_now,
)
from mcplain_api.redacteur import Redacteur

KEY = "sk-ant-test-CANARY"
GOOD_NOTICE = {
    "summary": "Ce serveur donne l'heure.",
    "use_cases": ["Demander l'heure."],
    "tool_titles": [{"name": "get_time", "title": "Donner l'heure", "sentence": "Il donne l'heure."}],
    "mismatch": False,
    "alert": "",
}


class Admin:
    """Class that holds a test client signed in as the admin with its second factor, and the database"""

    def __init__(self) -> None:
        """Build the API on a fresh database"""

        engine = make_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.sessions: sessionmaker = make_sessions(engine)
        self.users = FakeUsers()
        self.desk = FakeDesk()
        settings = altcha_settings(public_url=ORIGIN, ai_monthly_budget_usd=10, max_queued=3)
        app = create_app(settings, engine, peer_resolver=lambda names: {PEER}, user_reader=self.users, account_desk=self.desk)
        self.client = TestClient(app)
        self.id, cookie = self.users.add("admin", two_factor=True)
        self.headers = {**cookie, "Origin": ORIGIN}

    def post(self, path: str) -> httpx.Response:
        """Send a change as the admin, from the website"""

        return self.client.post(path, json={}, headers=self.headers)

    def journal(self) -> list[tuple[str, str, str]]:
        """Return the lines of the journal as the route gives them, oldest first"""

        lines = self.client.get("/api/admin/journal", headers=self.headers).json()["lines"]
        return [(line["action"], line["target_kind"], line["target_id"]) for line in reversed(lines)]


@pytest.fixture
def admin() -> Iterator[Admin]:
    """Return the admin client"""

    yield Admin()


def add_text(admin: Admin, status: str, reason: str | None = None) -> uuid.UUID:
    """Create the notice of a real report through the public route, then give it a state"""

    with admin.sessions.begin() as session:
        analysis = Analysis(input_raw="uvx demo", state="done", result=report([tool_report("get_time", "Gives the time.", lamps_of("internet"))]))
        session.add(analysis)
        session.flush()
        analysis_id = analysis.id
    assert admin.client.post(f"/api/analyses/{analysis_id}/notice", json={"lang": "fr"}).status_code == 202
    with admin.sessions.begin() as session:
        row = session.scalars(select(AiText)).all()[-1]
        row.status = status
        row.reject_reason = reason
        return row.id


def spend(admin: Admin, cost: float, days_ago: int = 0, text_id: uuid.UUID | None = None) -> None:
    """Log one paid call"""

    with admin.sessions.begin() as session:
        session.add(AiCall(text_id=text_id or uuid.uuid4(), kind="notice", lang="fr", outcome="answered", cost_usd=cost, created_at=utc_now() - timedelta(days=days_ago)))


def status_of(admin: Admin, text_id: uuid.UUID) -> str:
    """Return the state of a text"""

    with admin.sessions() as session:
        row = session.get(AiText, text_id)
        assert row is not None
        return row.status


@respx.mock
def test_a_rejected_notice_is_asked_again_and_written_by_the_writer(admin: Admin) -> None:
    """Rejected or failed: queued again, one line in the journal, then the writer writes it with its usual checks"""

    route = respx.post(API_URL).mock(
        return_value=httpx.Response(
            200,
            json={"content": [{"type": "text", "text": json.dumps(GOOD_NOTICE)}], "stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 5}},
        )
    )
    rejected = add_text(admin, "rejected", "link")
    answer = admin.post(f"/api/admin/texts/{rejected}/retry")
    assert answer.status_code == 202
    assert answer.json() == {"id": str(rejected), "status": "pending"}
    assert status_of(admin, rejected) == "pending"
    writer = Redacteur(altcha_settings(anthropic_api_key=KEY), admin.sessions, sleep=lambda seconds: None)
    writer.start()
    assert writer.run_once()
    assert status_of(admin, rejected) == "ready"
    assert route.call_count == 1
    assert admin.journal() == [("text_retry", "text", str(rejected))]


@pytest.mark.parametrize("status", ["ready", "pending", "paused", "disabled"])
def test_only_a_rejected_or_failed_text_can_be_asked_again(admin: Admin, status: str) -> None:
    """A ready notice, a waiting one, a paused one or a cut one is refused and stays as it is"""

    text_id = add_text(admin, status)
    answer = admin.post(f"/api/admin/texts/{text_id}/retry")
    assert answer.status_code == 409
    assert answer.json()["error"] == {"code": "api.text_not_retryable", "params": {"detail": status}}
    assert status_of(admin, text_id) == status
    assert admin.journal() == []


def test_a_failed_text_is_asked_again_before_its_waiting_time(admin: Admin) -> None:
    """The waiting time of a failure does not stop the admin; the writer still checks everything"""

    text_id = add_text(admin, "failed", "unavailable")
    with admin.sessions.begin() as session:
        session.get(AiText, text_id).retry_at = utc_now() + timedelta(minutes=10)
    assert admin.post(f"/api/admin/texts/{text_id}/retry").status_code == 202
    assert status_of(admin, text_id) == "pending"


def test_the_cap_of_4_calls_a_day_blocks_the_admin_too(admin: Admin) -> None:
    """Four calls of this text today: refused, said clearly, and the text stays rejected"""

    text_id = add_text(admin, "rejected", "encoding")
    for _ in range(4):
        spend(admin, 0.001, text_id=text_id)
    answer = admin.post(f"/api/admin/texts/{text_id}/retry")
    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "api.daily_text_cap"
    assert status_of(admin, text_id) == "rejected"


def test_the_daily_fuse_blocks_the_admin_too(admin: Admin) -> None:
    """The fuse of the day (10 / 20 = 0.50 dollar) counts the worst cost of the call, like the writer"""

    text_id = add_text(admin, "rejected", "link")
    spend(admin, 0.49)
    answer = admin.post(f"/api/admin/texts/{text_id}/retry")
    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "api.daily_fuse"
    assert "detail" in answer.json()["error"]["params"]
    assert status_of(admin, text_id) == "rejected"


def test_the_monthly_budget_blocks_the_admin_too(admin: Admin) -> None:
    """The budget of the month is checked before the fuse of the day"""

    text_id = add_text(admin, "failed", "unavailable")
    if utc_now().day == 1:
        spend(admin, 10.0)
    else:
        spend(admin, 10.0, days_ago=1)
    answer = admin.post(f"/api/admin/texts/{text_id}/retry")
    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "api.monthly_budget"


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (AiState(id=AI_STATE_ROW, disabled_reason="no_key"), "api.ai_disabled"),
        (AiState(id=AI_STATE_ROW, paused_until=utc_now() + timedelta(hours=1)), "api.ai_paused"),
    ],
)
def test_the_pause_and_the_cut_block_the_admin_too(admin: Admin, state: AiState, code: str) -> None:
    """Cut off or paused for everyone: nothing is queued"""

    text_id = add_text(admin, "rejected", "link")
    with admin.sessions.begin() as session:
        session.add(state)
    answer = admin.post(f"/api/admin/texts/{text_id}/retry")
    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == code
    assert status_of(admin, text_id) == "rejected"


def test_an_unknown_text_or_a_lost_report_is_refused(admin: Admin) -> None:
    """No such text: 404; its report gone: 409"""

    assert admin.post(f"/api/admin/texts/{uuid.uuid4()}/retry").status_code == 404
    assert admin.post("/api/admin/texts/nothing/retry").status_code == 404
    text_id = add_text(admin, "rejected", "link")
    with admin.sessions.begin() as session:
        session.get(AiText, text_id).analysis_id = uuid.uuid4()
    answer = admin.post(f"/api/admin/texts/{text_id}/retry")
    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "api.text_no_report"


def test_an_analysis_is_queued_again_without_cache_nor_quota(admin: Admin) -> None:
    """The same request again, skipping the cache, one line in the journal pointing at the new analysis"""

    with admin.sessions.begin() as session:
        done = Analysis(id=uuid.uuid4(), input_raw="npx -y demo-mcp", select="src/a", state="done", result=report([]))
        running = Analysis(id=uuid.uuid4(), input_raw="npx -y other", state="analyzing")
        session.add_all([done, running])
    answer = admin.post(f"/api/admin/analyses/{done.id}/rerun")
    assert answer.status_code == 202
    created = uuid.UUID(answer.json()["id"])
    with admin.sessions() as session:
        row = session.get(Analysis, created)
        assert row is not None
        assert (row.input_raw, row.select, row.state, row.ignore_cache, row.cache_only) == ("npx -y demo-mcp", "src/a", "queued", True, False)
    assert admin.journal() == [("analysis_rerun", "analysis", str(created))]
    assert admin.post(f"/api/admin/analyses/{running.id}/rerun").status_code == 409
    assert admin.post(f"/api/admin/analyses/{uuid.uuid4()}/rerun").status_code == 404
    assert admin.post(f"/api/admin/analyses/{done.id}/rerun").status_code == 202
    assert admin.post(f"/api/admin/analyses/{done.id}/rerun").status_code == 202
    full = admin.post(f"/api/admin/analyses/{done.id}/rerun")
    assert full.status_code == 503
    assert full.json()["error"]["code"] == "api.queue_full"


def test_an_alert_is_marked_as_read_once(admin: Admin) -> None:
    """The date of reading is set once, with one line in the journal"""

    with admin.sessions.begin() as session:
        alert = AiAdminAlert(id=uuid.uuid4(), code="usage_limit", created_at=utc_now(), details={"request_id": "req_SECRET"})
        session.add(alert)
    assert admin.post(f"/api/admin/alerts/{alert.id}/read").status_code == 200
    assert admin.post(f"/api/admin/alerts/{alert.id}/read").status_code == 200
    assert admin.post(f"/api/admin/alerts/{uuid.uuid4()}/read").status_code == 404
    view = admin.client.get("/api/admin/dashboard/ai", params={"days": "7"}, headers=admin.headers).json()
    assert view["alerts"][0]["read_at"] is not None
    assert "req_SECRET" not in json.dumps(view)
    assert admin.journal() == [("alert_read", "alert", str(alert.id))]


def test_bans_and_unbans_are_written_in_the_journal(admin: Admin) -> None:
    """A done ban and unban each leave a line with the account id; a refused one leaves none"""

    assert admin.client.post("/api/admin/accounts/someone/ban", json={"reason": None}, headers=admin.headers).status_code == 200
    assert admin.client.post("/api/admin/accounts/someone/unban", json={}, headers=admin.headers).status_code == 200
    admin.desk.admins.add("other-admin")
    assert admin.client.post("/api/admin/accounts/other-admin/ban", json={"reason": None}, headers=admin.headers).status_code == 403
    assert admin.journal() == [("ban", "account", "someone"), ("unban", "account", "someone")]


def test_the_journal_keeps_the_50_last_lines_newest_first(admin: Admin) -> None:
    """At most 50 lines, the newest first"""

    now = utc_now()
    with admin.sessions.begin() as session:
        for index in range(60):
            session.add(AdminAction(action="ban", target_kind="account", target_id=f"account-{index:02d}", created_at=now + timedelta(seconds=index)))
    lines = admin.client.get("/api/admin/journal", headers=admin.headers).json()["lines"]
    assert len(lines) == 50
    assert lines[0]["target_id"] == "account-59"
    assert lines[-1]["target_id"] == "account-10"
