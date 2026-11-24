"""Tests of the reports of the visitors: ALTCHA, the limits, the box of the site, the admin list, the erasing, with SQLite"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import altcha_headers, altcha_settings
from mcplain import __version__
from mcplain.verdict import RULES_VERSION
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from test_quotas import COUNTER_PEER, FakeUsers

from mcplain_api.app import create_app
from mcplain_api.db import (
    AdminAction,
    AiAdminAlert,
    Analysis,
    Base,
    QuotaRefusal,
    Report,
    ReportCount,
    ReportMark,
    make_engine,
    make_sessions,
)
from mcplain_api import reports as reports_module
from mcplain_api.facteur import Facteur, FacteurSettings
from mcplain_api.ip_fingerprint import purge_old_fingerprints
from mcplain_api.reports import BOX_FULL_ALERT, clean_comment, erase_old_comments, send_report

ORIGIN = "http://localhost:3000"
KINDS: tuple[str, ...] = ("false_alarm", "missed_danger", "author_error")
NOW = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
PERSON_COMMENT = "comment-of-a-person-7f3a"


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


def build(sessions: sessionmaker, users: FakeUsers, **values: object) -> TestClient:
    """Return a test client of the API on the test database, the website origin set"""

    settings = altcha_settings(public_url=ORIGIN, **values)
    app = create_app(settings, sessions.kw["bind"], peer_resolver=lambda names: {COUNTER_PEER}, user_reader=users)
    return TestClient(app)


def finished(sessions: sessionmaker, color: str = "orange", state: str = "done") -> uuid.UUID:
    """Add a finished analysis of one color and return its id"""

    with sessions.begin() as session:
        row = Analysis(
            id=uuid.uuid4(),
            input_raw="uvx demo",
            state=state,
            result={"status": "ok", "verdict": {"color": color}},
            engine_version=__version__,
            rules_version=RULES_VERSION,
            created_at=NOW,
            finished_at=NOW,
        )
        session.add(row)
        return row.id


def headers_for(address: str = "203.0.113.5", extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return the headers the relay of the website gives: the origin and the visitor address"""

    sent = {"Origin": ORIGIN, "X-Forwarded-For": address}
    sent.update(extra or {})
    return sent


def post_report(client: TestClient, analysis: uuid.UUID, body: dict[str, Any], headers: dict[str, str]) -> Any:
    """Send a report with a fresh ALTCHA solution, as the website does"""

    sent = altcha_headers(client)
    sent.update(headers)
    return client.post(f"/api/analyses/{analysis}/reports", json=body, headers=sent)


def reports(sessions: sessionmaker) -> list[Report]:
    """Return every stored report, the oldest first"""

    with sessions() as session:
        return list(session.scalars(select(Report).order_by(Report.created_at)).all())


def refusals(sessions: sessionmaker) -> dict[str, int]:
    """Return the refusals counted per kind, every day together"""

    with sessions() as session:
        found: dict[str, int] = {}
        for row in session.scalars(select(QuotaRefusal)).all():
            found[row.kind] = found.get(row.kind, 0) + row.count
        return found


def test_the_three_kinds_are_kept_with_the_versions_and_the_color(sessions: sessionmaker, users: FakeUsers) -> None:
    """Each kind is kept, new, with the engine and rules versions and the color the report had"""

    analysis = finished(sessions, "red")
    with build(sessions, users) as client:
        for kind in KINDS:
            answer = post_report(client, analysis, {"kind": kind}, headers_for())
            assert answer.status_code == 201, kind
            assert answer.json() == {"ok": True}
            assert answer.headers["cache-control"] == "no-store"
    stored = reports(sessions)
    assert sorted(row.kind for row in stored) == sorted(KINDS)
    for row in stored:
        assert (row.status, row.engine_version, row.rules_version, row.color) == ("new", __version__, RULES_VERSION, "red")
        assert (row.reporter_kind, row.reporter_user_id, row.comment) == ("anonymous", None, None)


def test_a_failed_analysis_is_kept_gray(sessions: sessionmaker, users: FakeUsers) -> None:
    """A report about a failed analysis keeps the gray color the visitor saw"""

    analysis = finished(sessions, "green", state="failed")
    with build(sessions, users) as client:
        assert post_report(client, analysis, {"kind": "missed_danger"}, headers_for()).status_code == 201
    assert reports(sessions)[0].color == "gray"


def test_an_account_is_kept_by_its_id(sessions: sessionmaker, users: FakeUsers) -> None:
    """A signed-in account is noted by its id, so that the admin can ban an abuse"""

    analysis = finished(sessions)
    account = users.add()
    with build(sessions, users) as client:
        assert post_report(client, analysis, {"kind": "false_alarm"}, headers_for(extra=account)).status_code == 201
    row = reports(sessions)[0]
    assert (row.reporter_kind, row.reporter_user_id) == ("account", users.id_of(account))


def test_the_origin_must_be_the_website(sessions: sessionmaker, users: FakeUsers) -> None:
    """Without Origin, or from another one, the report is refused before anything"""

    analysis = finished(sessions)
    with build(sessions, users) as client:
        for origin in (None, "http://attacker.invalid"):
            sent = altcha_headers(client)
            sent["X-Forwarded-For"] = "203.0.113.5"
            if origin is not None:
                sent["Origin"] = origin
            answer = client.post(f"/api/analyses/{analysis}/reports", json={"kind": "false_alarm"}, headers=sent)
            assert answer.status_code == 403
            assert answer.json()["error"]["code"] == "api.origin_refused"
    assert reports(sessions) == []


def test_the_format_and_the_size_are_checked(sessions: sessionmaker, users: FakeUsers) -> None:
    """JSON only, 8 KB at most, a known kind, no other field, 500 characters of comment at most"""

    analysis = finished(sessions)
    path = f"/api/analyses/{analysis}/reports"
    with build(sessions, users) as client:
        assert client.post(path, content="kind=false_alarm", headers={**headers_for(), "Content-Type": "text/plain"}).status_code == 415
        big = client.post(path, json={"kind": "false_alarm", "comment": "x" * 9000}, headers=headers_for())
        assert big.status_code == 413
        assert client.post(path, json={"kind": "other"}, headers=headers_for()).status_code == 400
        assert client.post(path, json={"kind": "false_alarm", "email": "a@example.com"}, headers=headers_for()).status_code == 400
        too_long = client.post(path, json={"kind": "false_alarm", "comment": "x" * 501}, headers=headers_for())
        assert too_long.status_code == 400
        assert too_long.json()["error"] == {"code": "api.comment_too_long", "params": {"limit": "500"}}
        assert post_report(client, analysis, {"kind": "false_alarm", "comment": "é" * 500}, headers_for()).status_code == 201


def test_the_comment_is_plain_text_without_control_characters() -> None:
    """Control characters and lone surrogates go, the line breaks stay, an empty comment is none"""

    assert clean_comment("  a\u0000b\u0007c\r\nd\te\u001b[31m  ") == "abc\nde[31m"
    assert clean_comment("x\ud800y") == "xy"
    assert clean_comment(" \u0000 \n ") is None
    assert clean_comment(None) is None
    assert clean_comment("<b>\u202Ekept as text</b>") == "<b>\u202Ekept as text</b>"


def test_the_comment_is_stored_cleaned_and_never_written_in_a_log(
    sessions: sessionmaker, users: FakeUsers, caplog: pytest.LogCaptureFixture
) -> None:
    """The stored comment is the cleaned one; no log line holds it"""

    analysis = finished(sessions)
    caplog.set_level(logging.DEBUG)
    with build(sessions, users) as client:
        answer = post_report(client, analysis, {"kind": "author_error", "comment": f" {PERSON_COMMENT}\u0000 "}, headers_for())
        assert answer.status_code == 201
    assert reports(sessions)[0].comment == PERSON_COMMENT
    assert PERSON_COMMENT not in caplog.text


def test_only_a_finished_analysis_can_be_reported(sessions: sessionmaker, users: FakeUsers) -> None:
    """An unknown analysis gives 404, a queued or used-up one 409"""

    queued = finished(sessions, state="queued")
    exhausted = finished(sessions, state="quota_exhausted")
    with build(sessions, users) as client:
        assert post_report(client, uuid.uuid4(), {"kind": "false_alarm"}, headers_for()).status_code == 404
        sent = {**altcha_headers(client), **headers_for()}
        assert client.post("/api/analyses/not-an-id/reports", json={"kind": "false_alarm"}, headers=sent).status_code == 404
        for analysis in (queued, exhausted):
            answer = post_report(client, analysis, {"kind": "false_alarm"}, headers_for())
            assert answer.status_code == 409
            assert answer.json()["error"]["code"] == "api.analysis_not_finished"
    assert reports(sessions) == []


def test_altcha_is_needed_and_used_once(sessions: sessionmaker, users: FakeUsers) -> None:
    """Without a solution, or with one already used, the report is refused"""

    analysis = finished(sessions)
    path = f"/api/analyses/{analysis}/reports"
    with build(sessions, users) as client:
        missing = client.post(path, json={"kind": "false_alarm"}, headers=headers_for())
        assert (missing.status_code, missing.json()["error"]["code"]) == (403, "altcha_invalid")
        solution = altcha_headers(client)
        assert client.post(path, json={"kind": "false_alarm"}, headers={**headers_for(), **solution}).status_code == 201
        again = client.post(path, json={"kind": "missed_danger"}, headers={**headers_for(), **solution})
        assert (again.status_code, again.json()["error"]["code"]) == (403, "altcha_invalid")
    assert len(reports(sessions)) == 1


def test_a_banned_account_cannot_report(sessions: sessionmaker, users: FakeUsers) -> None:
    """A banned account is refused, not counted as a visitor without account"""

    analysis = finished(sessions)
    banned = users.add(banned=True)
    with build(sessions, users) as client:
        answer = post_report(client, analysis, {"kind": "false_alarm"}, headers_for(extra=banned))
        assert (answer.status_code, answer.json()["error"]["code"]) == (403, "api.account_blocked")
    assert reports(sessions) == []


def test_one_report_per_kind_and_analysis_for_one_sender(sessions: sessionmaker, users: FakeUsers) -> None:
    """The same kind twice is refused and counted; another kind or another analysis passes; nothing is taken twice"""

    first = finished(sessions)
    second = finished(sessions)
    account = users.add()
    with build(sessions, users) as client:
        for sender in (headers_for(), headers_for("198.51.100.7", account)):
            assert post_report(client, first, {"kind": "false_alarm"}, sender).status_code == 201
            duplicate = post_report(client, first, {"kind": "false_alarm"}, sender)
            assert (duplicate.status_code, duplicate.json()["error"]["code"]) == (409, "report_duplicate")
            assert post_report(client, first, {"kind": "missed_danger"}, sender).status_code == 201
            assert post_report(client, second, {"kind": "false_alarm"}, sender).status_code == 201
    assert len(reports(sessions)) == 6
    assert refusals(sessions) == {"report_limit": 2}
    with sessions() as session:
        counts = {row.subject: row.count for row in session.scalars(select(ReportCount)).all()}
    assert counts["site"] == 6
    assert sorted(count for subject, count in counts.items() if subject != "site") == [3, 3]


def test_ten_a_day_without_account_for_one_network(sessions: sessionmaker, users: FakeUsers) -> None:
    """The 11th report of one network is refused and counted; another network still reports"""

    analyses = [finished(sessions) for _ in range(11)]
    with build(sessions, users) as client:
        for analysis in analyses[:10]:
            assert post_report(client, analysis, {"kind": "false_alarm"}, headers_for()).status_code == 201
        refused = post_report(client, analyses[10], {"kind": "false_alarm"}, headers_for())
        assert refused.status_code == 429
        assert refused.json()["error"]["code"] == "report_limit"
        assert refused.json()["error"]["params"]["resets_at"].endswith("T00:00:00+00:00")
        assert post_report(client, analyses[10], {"kind": "false_alarm"}, headers_for("198.51.100.7")).status_code == 201
    assert len(reports(sessions)) == 11
    assert refusals(sessions) == {"report_limit": 1}


def test_ten_a_day_for_an_account_whatever_the_network(sessions: sessionmaker, users: FakeUsers) -> None:
    """An account is counted by its id: changing network does not give it more"""

    analyses = [finished(sessions) for _ in range(11)]
    account = users.add()
    with build(sessions, users) as client:
        for index, analysis in enumerate(analyses[:10]):
            assert post_report(client, analysis, {"kind": "false_alarm"}, headers_for(f"203.0.113.{index + 1}", account)).status_code == 201
        refused = post_report(client, analyses[10], {"kind": "false_alarm"}, headers_for("198.51.100.99", account))
        assert (refused.status_code, refused.json()["error"]["code"]) == (429, "report_limit")


def test_the_bench_account_has_the_limit_of_an_account(sessions: sessionmaker, users: FakeUsers) -> None:
    """The bench role has no exemption for the reports"""

    analyses = [finished(sessions) for _ in range(11)]
    bench = users.add("bench", two_factor=True)
    with build(sessions, users, allow_bench_role=True) as client:
        for analysis in analyses[:10]:
            assert post_report(client, analysis, {"kind": "false_alarm"}, headers_for(extra=bench)).status_code == 201
        assert post_report(client, analyses[10], {"kind": "false_alarm"}, headers_for(extra=bench)).status_code == 429


def test_the_admin_has_no_limit(sessions: sessionmaker, users: FakeUsers) -> None:
    """The admin with its second factor reports past ten and twice the same kind, even when the box is full"""

    analysis = finished(sessions)
    admin = users.add("admin", two_factor=True)
    with build(sessions, users, reports_global_per_day=1) as client:
        assert post_report(client, analysis, {"kind": "false_alarm"}, headers_for()).status_code == 201
        for _ in range(12):
            assert post_report(client, analysis, {"kind": "false_alarm"}, headers_for(extra=admin)).status_code == 201
    assert len(reports(sessions)) == 13
    assert refusals(sessions) == {}


def test_an_admin_without_second_factor_has_the_limit_of_an_account(sessions: sessionmaker, users: FakeUsers) -> None:
    """Without the second factor, the admin is a normal account"""

    analysis = finished(sessions)
    admin = users.add("admin")
    with build(sessions, users) as client:
        assert post_report(client, analysis, {"kind": "false_alarm"}, headers_for(extra=admin)).status_code == 201
        assert post_report(client, analysis, {"kind": "false_alarm"}, headers_for(extra=admin)).status_code == 409


def test_the_box_of_the_site_is_full_after_its_limit(sessions: sessionmaker, users: FakeUsers) -> None:
    """Past the global limit: refused, counted as report_global, one alert for the admin a day, the sender keeps its slot"""

    analyses = [finished(sessions) for _ in range(5)]
    with build(sessions, users, reports_global_per_day=3) as client:
        for index, analysis in enumerate(analyses[:3]):
            assert post_report(client, analysis, {"kind": "false_alarm"}, headers_for(f"203.0.113.{index + 1}")).status_code == 201
        for analysis in analyses[3:]:
            full = post_report(client, analysis, {"kind": "false_alarm"}, headers_for("198.51.100.7"))
            assert (full.status_code, full.json()["error"]["code"]) == (429, "report_global")
    assert len(reports(sessions)) == 3
    assert refusals(sessions) == {"report_global": 2}
    with sessions() as session:
        alerts = session.scalars(select(AiAdminAlert)).all()
        marks = session.scalars(select(ReportMark).where(ReportMark.subject.like("ip:%"))).all()
        sender = [row for row in session.scalars(select(ReportCount)).all() if row.subject not in ("site",) and row.count == 0]
    assert [alert.code for alert in alerts] == [BOX_FULL_ALERT]
    assert alerts[0].details == {"limit": 3}
    assert len(marks) == 3
    assert sender == []


def accept_every_solution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let every ALTCHA solution pass, for the tests that move the clock without a real challenge"""

    monkeypatch.setattr(reports_module, "accept_solution", lambda session, settings, text, moment: True)


def test_the_box_alert_comes_back_the_next_day(sessions: sessionmaker, monkeypatch: pytest.MonkeyPatch) -> None:
    """The alert of the full box is added once per UTC day"""

    accept_every_solution(monkeypatch)
    settings = altcha_settings(reports_global_per_day=1)
    analyses = [finished(sessions) for _ in range(4)]

    def send(analysis: uuid.UUID, moment: datetime, address: str) -> str:
        """Send one report at a moment"""

        return send_report(sessions, settings, None, address, "x", analysis, "false_alarm", None, moment).value

    assert send(analyses[0], NOW, "203.0.113.1") == "sent"
    assert send(analyses[1], NOW, "203.0.113.2") == "report_global"
    assert send(analyses[2], NOW + timedelta(hours=1), "203.0.113.3") == "report_global"
    later = NOW + timedelta(days=1)
    assert send(analyses[3], later, "203.0.113.4") == "sent"
    assert send(analyses[1], later, "203.0.113.5") == "report_global"
    with sessions() as session:
        days = sorted(alert.created_at.date() for alert in session.scalars(select(AiAdminAlert)).all())
    assert days == [NOW.date(), later.date()]


def test_the_limits_come_back_the_next_utc_day(sessions: sessionmaker, monkeypatch: pytest.MonkeyPatch) -> None:
    """A new UTC day gives the reports again, and the marks of an address go after two days, those of an account stay"""

    accept_every_solution(monkeypatch)
    settings = altcha_settings(reports_per_day=1)
    analysis = finished(sessions)
    other = finished(sessions)
    assert send_report(sessions, settings, None, "203.0.113.5", "x", analysis, "false_alarm", None, NOW).value == "sent"
    assert send_report(sessions, settings, None, "203.0.113.5", "x", other, "false_alarm", None, NOW).value == "report_limit"
    again = NOW + timedelta(days=1)
    assert send_report(sessions, settings, None, "203.0.113.5", "x", other, "false_alarm", None, again).value == "sent"
    with sessions.begin() as session:
        session.add(ReportMark(subject="user:kept", analysis_id=analysis, kind="false_alarm", day=NOW.date()))
    with sessions.begin() as session:
        purge_old_fingerprints(session, NOW + timedelta(days=3))
    with sessions() as session:
        subjects = [row.subject for row in session.scalars(select(ReportMark)).all()]
        counts = session.scalars(select(ReportCount)).all()
    assert subjects == ["user:kept"]
    assert counts == []


def test_the_comment_is_erased_ninety_days_after_it_was_closed(sessions: sessionmaker) -> None:
    """Closed 91 days ago: erased, the row stays; closed 89 days ago or still new: kept"""

    analysis = finished(sessions)
    with sessions.begin() as session:
        for name, status, closed in (
            ("old", "handled", NOW - timedelta(days=91)),
            ("rejected", "rejected", NOW - timedelta(days=90, minutes=1)),
            ("recent", "handled", NOW - timedelta(days=89)),
            ("open", "new", None),
        ):
            session.add(
                Report(
                    analysis_id=analysis,
                    kind="false_alarm",
                    status=status,
                    comment=name,
                    reporter_kind="anonymous",
                    created_at=NOW - timedelta(days=200),
                    closed_at=closed,
                )
            )
    with sessions.begin() as session:
        assert erase_old_comments(session, NOW) == 2
    with sessions.begin() as session:
        assert erase_old_comments(session, NOW) == 0
    kept = {row.status + ":" + str(row.comment): row for row in reports(sessions)}
    assert sorted(kept) == ["handled:None", "handled:recent", "new:open", "rejected:None"]
    for row in reports(sessions):
        assert row.kind == "false_alarm"
        assert row.created_at is not None


def test_the_postman_erases_the_comments_once_an_hour(sessions: sessionmaker) -> None:
    """The postman erases the old comments in its round, at most once an hour"""

    analysis = finished(sessions)
    with sessions.begin() as session:
        session.add(Report(analysis_id=analysis, kind="false_alarm", status="handled", comment="old", reporter_kind="anonymous", created_at=NOW, closed_at=NOW))
    facteur = Facteur(FacteurSettings(database_url="sqlite://"), sessions, sender=lambda settings, message: None)
    facteur.tick(NOW + timedelta(days=90, minutes=-1))
    assert reports(sessions)[0].comment == "old"
    facteur.tick(NOW + timedelta(days=90, minutes=30))
    assert reports(sessions)[0].comment == "old"
    facteur.tick(NOW + timedelta(days=90, minutes=61))
    assert reports(sessions)[0].comment is None


def test_deleting_an_account_keeps_its_reports_without_its_id_nor_its_comments(sessions: sessionmaker, users: FakeUsers) -> None:
    """Before an account is deleted, its reports stay as from a deleted account, and its counts and marks go"""

    analysis = finished(sessions)
    account = users.add()
    user_id = users.id_of(account)
    with build(sessions, users) as client:
        assert post_report(client, analysis, {"kind": "author_error", "comment": PERSON_COMMENT}, headers_for(extra=account)).status_code == 201
        assert post_report(client, analysis, {"kind": "false_alarm", "comment": "other"}, headers_for()).status_code == 201
    settings = altcha_settings(public_url=ORIGIN)
    app = create_app(settings, sessions.kw["bind"], peer_resolver=lambda names: {COUNTER_PEER}, user_reader=users)
    with TestClient(app, client=(COUNTER_PEER, 50000)) as counter:
        assert counter.post("/internal/account-erase", json={"user_id": user_id}).status_code == 200
    rows = {row.kind: row for row in reports(sessions)}
    assert (rows["author_error"].reporter_kind, rows["author_error"].reporter_user_id, rows["author_error"].comment) == ("deleted", None, None)
    assert rows["false_alarm"].comment == "other"
    with sessions() as session:
        subjects = [row.subject for row in session.scalars(select(ReportMark)).all()] + [
            row.subject for row in session.scalars(select(ReportCount)).all()
        ]
    assert not [subject for subject in subjects if user_id in subject]


def admin_client(sessions: sessionmaker, users: FakeUsers) -> tuple[TestClient, dict[str, str]]:
    """Return a client and the headers of the admin with its second factor"""

    return build(sessions, users), {**users.add("admin", two_factor=True), "Origin": ORIGIN}


def test_the_admin_list_shows_the_last_fifty_with_filters(sessions: sessionmaker, users: FakeUsers) -> None:
    """The newest first, 50 at most, filtered by status and kind, with the count of the new ones; a strange filter is 400"""

    analysis = finished(sessions)
    with sessions.begin() as session:
        for index in range(55):
            kind = KINDS[index % 3]
            status = "new"
            if index % 5 == 0:
                status = "rejected"
            session.add(Report(analysis_id=analysis, kind=kind, status=status, reporter_kind="anonymous", created_at=NOW + timedelta(minutes=index)))
    client, admin = admin_client(sessions, users)
    with client:
        everything = client.get("/api/admin/reports", headers=admin).json()
        assert len(everything["reports"]) == 50
        assert everything["new_count"] == 44
        moments = [item["created_at"] for item in everything["reports"]]
        assert moments == sorted(moments, reverse=True)
        authors = client.get("/api/admin/reports", params={"kind": "author_error"}, headers=admin).json()["reports"]
        assert {item["kind"] for item in authors} == {"author_error"}
        assert all(item["unverified"] for item in authors)
        rejected = client.get("/api/admin/reports", params={"status": "rejected", "kind": "false_alarm"}, headers=admin).json()["reports"]
        assert rejected and {(item["status"], item["kind"]) for item in rejected} == {("rejected", "false_alarm")}
        for params in ({"status": "done"}, {"kind": "everything"}):
            assert client.get("/api/admin/reports", params=params, headers=admin).status_code == 400


def test_the_admin_marks_a_report_handled_or_rejected_in_the_journal(sessions: sessionmaker, users: FakeUsers) -> None:
    """Handled then rejected: two lines in the journal, the 90 days start the first time; the same status writes nothing"""

    analysis = finished(sessions)
    with sessions.begin() as session:
        row = Report(analysis_id=analysis, kind="false_alarm", status="new", reporter_kind="anonymous", created_at=NOW)
        session.add(row)
        session.flush()
        identifier = row.id
    client, admin = admin_client(sessions, users)
    path = f"/api/admin/reports/{identifier}/status"
    with client:
        handled = client.post(path, json={"status": "handled"}, headers=admin)
        assert handled.status_code == 200
        assert handled.json() == {"id": str(identifier), "status": "handled"}
        closed = reports(sessions)[0].closed_at
        assert closed is not None
        assert client.post(path, json={"status": "handled"}, headers=admin).status_code == 200
        assert client.post(path, json={"status": "rejected"}, headers=admin).status_code == 200
        assert reports(sessions)[0].closed_at == closed
        assert client.post(path, json={"status": "new"}, headers=admin).status_code == 400
        assert client.post(path, json={"status": "handled", "other": 1}, headers=admin).status_code == 400
        assert client.post(f"/api/admin/reports/{uuid.uuid4()}/status", json={"status": "handled"}, headers=admin).status_code == 404
        assert client.post("/api/admin/reports/nope/status", json={"status": "handled"}, headers=admin).status_code == 404
    with sessions() as session:
        lines = [(line.action, line.target_kind, line.target_id) for line in session.scalars(select(AdminAction).order_by(AdminAction.created_at)).all()]
    assert lines == [("report_handled", "report", str(identifier)), ("report_rejected", "report", str(identifier))]


def test_the_list_erases_the_overdue_comments_before_showing_them(sessions: sessionmaker, users: FakeUsers) -> None:
    """A comment kept past its 90 days is never shown, even if the postman did not pass yet"""

    analysis = finished(sessions)
    long_ago = datetime.now(UTC) - timedelta(days=100)
    with sessions.begin() as session:
        session.add(Report(analysis_id=analysis, kind="false_alarm", status="handled", comment=PERSON_COMMENT, reporter_kind="anonymous", created_at=long_ago, closed_at=long_ago))
    client, admin = admin_client(sessions, users)
    with client:
        answer = client.get("/api/admin/reports", headers=admin)
    assert PERSON_COMMENT not in answer.text
    assert answer.json()["reports"][0]["comment_erased_at"] is not None


def test_no_answer_ever_holds_an_address_fingerprint(sessions: sessionmaker, users: FakeUsers) -> None:
    """The report list shows the account id or nobody, never the fingerprint; the dial of the reports shows totals only"""

    analysis = finished(sessions)
    account = users.add()
    with build(sessions, users) as client:
        assert post_report(client, analysis, {"kind": "false_alarm", "comment": "plain"}, headers_for()).status_code == 201
        assert post_report(client, analysis, {"kind": "author_error"}, headers_for("198.51.100.7", account)).status_code == 201
    with sessions() as session:
        fingerprints = [row.subject[3:] for row in session.scalars(select(ReportMark)).all() if row.subject.startswith("ip:")]
    assert fingerprints
    client, admin = admin_client(sessions, users)
    with client:
        listed = client.get("/api/admin/reports", headers=admin)
        dial = client.get("/api/admin/dashboard/reports", params={"days": "7"}, headers=admin)
    for answer in (listed, dial):
        for fingerprint in fingerprints:
            assert fingerprint not in answer.text
        assert "203.0.113.5" not in answer.text
        assert "198.51.100.7" not in answer.text
    items = {item["kind"]: item for item in listed.json()["reports"]}
    assert items["author_error"]["account_id"] == users.id_of(account)
    assert items["false_alarm"]["account_id"] is None
    assert items["false_alarm"]["reporter_kind"] == "anonymous"
    assert users.id_of(account) not in dial.text


def test_the_dial_counts_the_reports_per_day_and_kind(sessions: sessionmaker, users: FakeUsers) -> None:
    """Every day of the period with each kind, zero on the empty days, and the totals"""

    analysis = finished(sessions)
    today = datetime.now(UTC).replace(hour=1, minute=0, second=0, microsecond=0)
    with sessions.begin() as session:
        for kind, moment in (
            ("false_alarm", today),
            ("false_alarm", today),
            ("author_error", today - timedelta(days=2)),
            ("missed_danger", today - timedelta(days=40)),
        ):
            session.add(Report(analysis_id=analysis, kind=kind, status="new", reporter_kind="anonymous", created_at=moment))
    client, admin = admin_client(sessions, users)
    with client:
        week = client.get("/api/admin/dashboard/reports", params={"days": "7"}, headers=admin).json()
        assert client.get("/api/admin/dashboard/reports", params={"days": "9"}, headers=admin).status_code == 400
    assert week["kinds"] == list(KINDS)
    assert len(week["per_day"]) == 7
    assert week["per_day"][-1]["counts"] == {"false_alarm": 2, "missed_danger": 0, "author_error": 0}
    assert week["per_day"][-3]["counts"] == {"false_alarm": 0, "missed_danger": 0, "author_error": 1}
    assert week["totals"] == {"false_alarm": 2, "missed_danger": 0, "author_error": 1}
