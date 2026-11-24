"""Tests of the estimated credit: the ledger, the low balance mail sent once by the postman, armed again when the credit goes up"""

import smtplib
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient
from helpers import altcha_settings
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from test_admin import ORIGIN, PEER, FakeDesk, FakeUsers

from mcplain_api import ai_budget, credit, facteur
from mcplain_api.ai_budget import estimated_balance, is_low
from mcplain_api.app import create_app
from mcplain_api.credit import DeleteOutcome, add_entry, credit_view, delete_last
from mcplain_api.db import BALANCE_ALERT_ROW, AdminAction, AiCall, BalanceAlert, Base, as_utc, make_engine, make_sessions
from mcplain_api.facteur import Facteur, FacteurSettings

THRESHOLD = 2.0
START = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


class FakeSmtp:
    """Class that records the mails instead of sending them, and fails while told to"""

    def __init__(self) -> None:
        """Start with no mail sent and a server that answers"""

        self.down = False
        self.sent: list[EmailMessage] = []

    def __call__(self, settings: FacteurSettings, message: EmailMessage) -> None:
        """Record the mail, or fail like an SMTP server that does not answer"""

        if self.down:
            raise smtplib.SMTPServerDisconnected("down")
        self.sent.append(message)


@pytest.fixture
def sessions() -> sessionmaker:
    """Return a session factory on a fresh in-memory database"""

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_sessions(engine)


def spend(sessions: sessionmaker, moment: datetime, cost: float) -> None:
    """Log one paid call of the AI"""

    with sessions.begin() as session:
        session.add(AiCall(text_id=uuid.uuid4(), kind="notice", lang="fr", outcome="answered", cost_usd=cost, created_at=moment))


def entry(sessions: sessionmaker, kind: str, amount: float, moment: datetime) -> uuid.UUID:
    """Add one entry of the ledger as the API does"""

    with sessions.begin() as session:
        return add_entry(session, kind, amount, None, moment, THRESHOLD).id


def balance(sessions: sessionmaker) -> float | None:
    """Return the estimated credit"""

    with sessions() as session:
        return estimated_balance(session).amount_usd


def postman(sessions: sessionmaker, smtp: FakeSmtp, **values: object) -> Facteur:
    """Return a postman that sends to the fake server"""

    defaults: dict[str, object] = {"database_url": "sqlite://", "admin_email": "admin@example.com", "public_url": ORIGIN}
    defaults.update(values)
    return Facteur(FacteurSettings(_env_file=None, **defaults), sessions, sender=smtp)


def test_without_statement_there_is_no_balance(sessions: sessionmaker) -> None:
    """No statement: no amount, never low, whatever the top-ups and the spend"""

    spend(sessions, START, 1.0)
    entry(sessions, "top_up", 5.0, START)
    with sessions() as session:
        found = estimated_balance(session)
    assert found.amount_usd is None
    assert found.statement_at is None
    assert is_low(found, THRESHOLD) is False


def test_the_balance_is_the_last_statement_plus_top_ups_minus_spend_since(sessions: sessionmaker) -> None:
    """Only what comes after the last statement counts; the spend comes from spent_since, like the fuses"""

    spend(sessions, START - timedelta(hours=1), 3.0)
    entry(sessions, "statement", 20.0, START - timedelta(minutes=30))
    entry(sessions, "statement", 10.0, START)
    assert balance(sessions) == pytest.approx(10.0)
    spend(sessions, START + timedelta(minutes=1), 0.5)
    entry(sessions, "top_up", 5.0, START + timedelta(minutes=2))
    spend(sessions, START + timedelta(minutes=3), 0.25)
    with sessions() as session:
        found = estimated_balance(session)
        assert found.spent_usd == pytest.approx(ai_budget.spent_since(session, START))
    assert found.amount_usd == pytest.approx(14.25)
    assert found.statement_usd == pytest.approx(10.0)
    assert found.top_ups_usd == pytest.approx(5.0)
    assert found.statement_at == START
    assert facteur.estimated_balance is ai_budget.estimated_balance
    assert credit.estimated_balance is ai_budget.estimated_balance


def test_only_the_last_entry_can_be_deleted(sessions: sessionmaker) -> None:
    """A typing mistake is fixed by deleting the newest entry; an older one stays"""

    first = entry(sessions, "statement", 10.0, START)
    second = entry(sessions, "top_up", 5.0, START + timedelta(minutes=1))
    with sessions.begin() as session:
        assert delete_last(session, first, THRESHOLD) is DeleteOutcome.NOT_LAST
        assert delete_last(session, uuid.uuid4(), THRESHOLD) is DeleteOutcome.NOT_FOUND
        assert delete_last(session, second, THRESHOLD) is DeleteOutcome.DONE
    assert balance(sessions) == pytest.approx(10.0)


def test_the_mail_goes_once_under_the_threshold_and_never_without_statement(sessions: sessionmaker) -> None:
    """Under 2 dollars: one mail with the balance, the date and the admin page; nothing more until the credit goes up"""

    smtp = FakeSmtp()
    sender = postman(sessions, smtp)
    spend(sessions, START, 50.0)
    entry(sessions, "top_up", 1.0, START)
    sender.tick(START + timedelta(minutes=1))
    assert smtp.sent == []
    entry(sessions, "statement", 1.5, START + timedelta(minutes=2))
    sender.tick(START + timedelta(minutes=3))
    assert len(smtp.sent) == 1
    mail = smtp.sent[0]
    body = mail.get_content()
    assert mail["To"] == "admin@example.com"
    assert mail.get_content_type() == "text/plain"
    assert "1.50" in body
    assert "2026-12-01 08:02" in body
    assert ORIGIN + "/fr/admin" in body
    assert "console Anthropic" in body
    for minutes in range(4, 10):
        sender.tick(START + timedelta(minutes=minutes))
    assert len(smtp.sent) == 1
    with sessions() as session:
        assert as_utc(session.get(BalanceAlert, BALANCE_ALERT_ROW).sent_at) == START + timedelta(minutes=3)


def test_the_mail_is_armed_again_by_a_top_up_and_by_deleting_the_last_entry(sessions: sessionmaker) -> None:
    """A top-up over the threshold arms it; so does deleting a wrong low entry; a spend never does"""

    smtp = FakeSmtp()
    sender = postman(sessions, smtp)
    entry(sessions, "statement", 1.0, START)
    sender.tick(START + timedelta(minutes=1))
    assert len(smtp.sent) == 1
    entry(sessions, "top_up", 0.5, START + timedelta(minutes=2))
    sender.tick(START + timedelta(minutes=3))
    assert len(smtp.sent) == 1
    entry(sessions, "top_up", 10.0, START + timedelta(minutes=4))
    with sessions() as session:
        assert session.get(BalanceAlert, BALANCE_ALERT_ROW).sent_at is None
    sender.tick(START + timedelta(minutes=5))
    assert len(smtp.sent) == 1
    spend(sessions, START + timedelta(minutes=6), 10.0)
    sender.tick(START + timedelta(minutes=7))
    assert len(smtp.sent) == 2
    entry(sessions, "statement", 10.0, START + timedelta(minutes=8))
    wrong = entry(sessions, "statement", 0.1, START + timedelta(minutes=9))
    sender.tick(START + timedelta(minutes=10))
    assert len(smtp.sent) == 3
    with sessions() as session:
        assert session.get(BalanceAlert, BALANCE_ALERT_ROW).sent_at is not None
    with sessions.begin() as session:
        assert delete_last(session, wrong, THRESHOLD) is DeleteOutcome.DONE
    with sessions() as session:
        assert session.get(BalanceAlert, BALANCE_ALERT_ROW).sent_at is None


def test_a_failed_smtp_send_is_tried_again_and_only_a_sent_mail_counts(sessions: sessionmaker) -> None:
    """The state turns sent only after the SMTP server said yes; the next check tries again"""

    smtp = FakeSmtp()
    smtp.down = True
    sender = postman(sessions, smtp)
    entry(sessions, "statement", 0.5, START)
    sender.tick(START + timedelta(minutes=1))
    with sessions() as session:
        assert session.get(BalanceAlert, BALANCE_ALERT_ROW).sent_at is None
    smtp.down = False
    sender.tick(START + timedelta(minutes=1, seconds=30))
    assert smtp.sent == []
    sender.tick(START + timedelta(minutes=2))
    assert len(smtp.sent) == 1


def test_no_mail_without_admin_address(sessions: sessionmaker) -> None:
    """Without MCPLAIN_ADMIN_EMAIL, the postman never mails the balance and the state stays armed"""

    smtp = FakeSmtp()
    sender = postman(sessions, smtp, admin_email="")
    entry(sessions, "statement", 0.5, START)
    sender.tick(START + timedelta(minutes=1))
    assert smtp.sent == []
    with sessions() as session:
        assert session.get(BalanceAlert, BALANCE_ALERT_ROW).sent_at is None


def test_the_view_says_when_there_is_no_statement(sessions: sessionmaker) -> None:
    """Without statement, the view has no balance and is never low"""

    with sessions() as session:
        view = credit_view(session, THRESHOLD)
    assert view["balance_usd"] is None
    assert view["statement_at"] is None
    assert view["low"] is False
    assert view["entries"] == []
    assert view["threshold_usd"] == THRESHOLD


@pytest.fixture
def admin() -> tuple[TestClient, dict[str, str], sessionmaker]:
    """Return a test client of the API, the cookie of an admin with its second factor, and the database"""

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    users = FakeUsers()
    app = create_app(altcha_settings(public_url=ORIGIN), engine, peer_resolver=lambda names: {PEER}, user_reader=users, account_desk=FakeDesk())
    _, headers = users.add("admin", two_factor=True)
    return TestClient(app), {**headers, "Origin": ORIGIN}, make_sessions(engine)


def test_the_routes_add_and_delete_entries_and_write_the_journal(admin: tuple[TestClient, dict[str, str], sessionmaker]) -> None:
    """POST adds an entry with its note in plain text, DELETE takes back the last one, each change has its line"""

    client, headers, sessions = admin
    empty = client.get("/api/admin/credit", headers=headers).json()
    assert empty["balance_usd"] is None
    note = "Console ‮ <b>read</b>"
    added = client.post("/api/admin/credit", json={"kind": "statement", "amount_usd": 9.5, "note": "  " + note + " "}, headers=headers)
    assert added.status_code == 201
    view = added.json()
    assert view["balance_usd"] == pytest.approx(9.5)
    assert view["entries"][0]["note"] == note
    topped = client.post("/api/admin/credit", json={"kind": "top_up", "amount_usd": 5, "note": None}, headers=headers).json()
    assert topped["balance_usd"] == pytest.approx(14.5)
    first_id = view["entries"][0]["id"]
    assert client.delete("/api/admin/credit/" + first_id, headers=headers).status_code == 409
    gone = client.delete("/api/admin/credit/" + topped["last_entry_id"], headers=headers)
    assert gone.status_code == 200
    assert gone.json()["balance_usd"] == pytest.approx(9.5)
    assert client.delete("/api/admin/credit/" + str(uuid.uuid4()), headers=headers).status_code == 404
    assert client.delete("/api/admin/credit/not-an-id", headers=headers).status_code == 404
    with sessions() as session:
        actions = [row.action for row in session.scalars(select(AdminAction).order_by(AdminAction.created_at))]
    assert actions == ["credit_add", "credit_add", "credit_delete"]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"kind": "top_up", "amount_usd": 0}, "api.invalid_amount"),
        ({"kind": "statement", "amount_usd": -1}, "api.invalid_amount"),
        ({"kind": "statement", "amount_usd": 1_000_000}, "api.invalid_amount"),
        ({"kind": "statement", "amount_usd": 1, "note": "x" * 101}, "api.note_too_long"),
        ({"kind": "gift", "amount_usd": 1}, "api.invalid_request"),
        ({"kind": "statement", "amount_usd": "1"}, "api.invalid_request"),
        ({"kind": "statement", "amount_usd": 1, "date": "2026-01-01"}, "api.invalid_request"),
    ],
)
def test_a_wrong_entry_is_refused(admin: tuple[TestClient, dict[str, str], sessionmaker], body: dict[str, object], code: str) -> None:
    """Amounts in range, a note of 100 characters at most, no other field: the date is always the moment of the entry"""

    client, headers, sessions = admin
    answer = client.post("/api/admin/credit", json=body, headers=headers)
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == code
    with sessions() as session:
        assert session.scalars(select(AdminAction)).all() == []


def test_a_note_of_100_characters_is_kept(admin: tuple[TestClient, dict[str, str], sessionmaker]) -> None:
    """100 characters exactly pass"""

    client, headers, _ = admin
    answer = client.post("/api/admin/credit", json={"kind": "statement", "amount_usd": 1, "note": "é" * 100}, headers=headers)
    assert answer.status_code == 201
