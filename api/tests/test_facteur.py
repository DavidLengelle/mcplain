"""Tests of the postman (facteur): plain text mails, rows deleted once handled, retries, and the admin alerts"""

import logging
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from mcplain_api.db import AiAdminAlert, Base, MailOutbox, make_engine, make_sessions
from mcplain_api.facteur import (
    ADMIN_MAILS_PER_DAY,
    Facteur,
    FacteurSettings,
    clean_address,
    mail_texts,
    outbox_message,
)

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
LINK = "http://localhost:3010/api/auth/verify-email?token=SECRET-TOKEN&callbackURL=%2Ffr%2Fcompte%2Fverifie"
TEST_PASSWORD = "test only smtp password"


class FakeSmtp:
    """Class that records the mails instead of sending them, and fails a given number of times"""

    def __init__(self, failures: int = 0) -> None:
        """Start with no mail sent"""

        self.failures = failures
        self.sent: list[EmailMessage] = []

    def __call__(self, settings: FacteurSettings, message: EmailMessage) -> None:
        """Record the mail, or fail like an SMTP server that does not answer"""

        if self.failures > 0:
            self.failures -= 1
            raise smtplib.SMTPServerDisconnected("down")
        self.sent.append(message)


def facteur_settings(**values: object) -> FacteurSettings:
    """Return settings for the postman, independent of the machine"""

    defaults: dict[str, object] = {"database_url": "sqlite://", "admin_email": "admin@example.com"}
    defaults.update(values)
    return FacteurSettings(_env_file=None, **defaults)


@pytest.fixture
def sessions() -> sessionmaker:
    """Return a session factory on a fresh in-memory database"""

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_sessions(engine)


def add_mail(sessions: sessionmaker, kind: str = "verify_email", lang: str = "fr", recipient: str = "ada@example.com") -> None:
    """Leave one mail in the outbox, as the counter does"""

    with sessions.begin() as session:
        session.add(MailOutbox(kind=kind, lang=lang, recipient=recipient, link=LINK, created_at=NOW))


def outbox_size(sessions: sessionmaker) -> int:
    """Return how many mails wait in the outbox"""

    with sessions() as session:
        return session.scalar(select(func.count()).select_from(MailOutbox)) or 0


def test_mails_are_plain_text_and_the_row_is_deleted(sessions: sessionmaker) -> None:
    """A verification mail goes out in plain text, in its language, then its row and its link leave the database"""

    add_mail(sessions)
    smtp = FakeSmtp()
    Facteur(facteur_settings(), sessions, smtp).deliver_outbox(NOW)
    assert outbox_size(sessions) == 0
    [message] = smtp.sent
    assert message.get_content_type() == "text/plain"
    assert not message.is_multipart()
    assert message["To"] == "ada@example.com"
    assert message["Subject"] == mail_texts("fr")["verify_email"]["subject"]
    assert LINK in message.get_content()
    assert "<" not in message.get_content()


def test_every_model_exists_in_both_languages() -> None:
    """The English and French models have the same mails, each with its link or its values"""

    assert mail_texts("en").keys() == mail_texts("fr").keys() == {"verify_email", "reset_password", "admin_alert"}
    for lang in ("en", "fr"):
        for kind in ("verify_email", "reset_password"):
            assert "{link}" in mail_texts(lang)[kind]["body"]
            message = outbox_message(facteur_settings(), kind, lang, "ada@example.com", LINK)
            assert message.get_content().count(LINK) == 1


def test_a_failing_server_is_tried_three_more_times_then_the_mail_is_dropped(
    sessions: sessionmaker, caplog: pytest.LogCaptureFixture
) -> None:
    """Three more tries, spaced; after the last one the row is deleted and the log has neither link nor address"""

    add_mail(sessions)
    smtp = FakeSmtp(failures=10)
    facteur = Facteur(facteur_settings(), sessions, smtp)
    moments = [NOW, NOW + timedelta(seconds=10), NOW + timedelta(seconds=31), NOW + timedelta(minutes=3), NOW + timedelta(minutes=14)]
    remaining = []
    with caplog.at_level(logging.INFO, logger="mcplain.facteur"):
        for moment in moments:
            facteur.deliver_outbox(moment)
            remaining.append(outbox_size(sessions))
    assert remaining == [1, 1, 1, 1, 0]
    assert smtp.failures == 6
    assert "dropped after 4 attempts" in caplog.text
    assert "SECRET-TOKEN" not in caplog.text
    assert "ada@example.com" not in caplog.text


def test_a_mail_sent_on_a_retry_is_deleted(sessions: sessionmaker) -> None:
    """When the server comes back, the mail goes out and its row is deleted"""

    add_mail(sessions)
    smtp = FakeSmtp(failures=1)
    facteur = Facteur(facteur_settings(), sessions, smtp)
    facteur.deliver_outbox(NOW)
    facteur.deliver_outbox(NOW + timedelta(seconds=31))
    assert outbox_size(sessions) == 0
    assert len(smtp.sent) == 1
    assert facteur.retries == {}


def test_a_row_that_could_add_a_header_is_dropped_unsent(sessions: sessionmaker) -> None:
    """An address with a line break or a second recipient, or a strange link, is never sent"""

    add_mail(sessions, recipient="ada@example.com\r\nBcc: eve@attacker.invalid")
    add_mail(sessions, recipient="ada@example.com, eve@attacker.invalid")
    smtp = FakeSmtp()
    Facteur(facteur_settings(), sessions, smtp).deliver_outbox(NOW)
    assert smtp.sent == []
    assert outbox_size(sessions) == 0
    with pytest.raises(ValueError):
        outbox_message(facteur_settings(), "verify_email", "fr", "ada@example.com", "javascript:alert(1)")
    with pytest.raises(ValueError):
        outbox_message(facteur_settings(), "newsletter", "fr", "ada@example.com", LINK)
    with pytest.raises(ValueError):
        clean_address("Eve <eve@attacker.invalid>")


def add_alert(sessions: sessionmaker, code: str, moment: datetime, emailed_at: datetime | None = None) -> None:
    """Record one admin alert, as the writer does"""

    with sessions.begin() as session:
        session.add(AiAdminAlert(code=code, created_at=moment, details={"request_id": "req_secret"}, emailed_at=emailed_at))


def test_admin_alerts_give_one_mail_per_code_with_the_count(sessions: sessionmaker) -> None:
    """Three alerts of one code give one mail with their number; the details never go in the mail"""

    for minutes in range(3):
        add_alert(sessions, "usage_limit", NOW - timedelta(minutes=10 - minutes))
    smtp = FakeSmtp()
    facteur = Facteur(facteur_settings(), sessions, smtp)
    facteur.deliver_alerts(NOW)
    [message] = smtp.sent
    assert message["To"] == "admin@example.com"
    assert "usage_limit" in message["Subject"]
    assert "3 fois" in message.get_content()
    assert "req_secret" not in message.get_content()
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(AiAdminAlert).where(AiAdminAlert.emailed_at.is_(None))) == 0


def test_at_most_one_mail_per_code_every_24_hours(sessions: sessionmaker) -> None:
    """A new alert of a code mailed less than 24 hours ago waits; after 24 hours it goes out"""

    add_alert(sessions, "auth", NOW - timedelta(hours=2), emailed_at=NOW - timedelta(hours=2))
    add_alert(sessions, "auth", NOW - timedelta(minutes=1))
    smtp = FakeSmtp()
    facteur = Facteur(facteur_settings(), sessions, smtp)
    facteur.deliver_alerts(NOW)
    assert smtp.sent == []
    facteur.deliver_alerts(NOW + timedelta(hours=23))
    assert len(smtp.sent) == 1


def test_at_most_20_admin_mails_per_day(sessions: sessionmaker) -> None:
    """Thirty different codes give twenty mails today, and the rest the next day"""

    for index in range(30):
        add_alert(sessions, f"code_{index:02d}", NOW - timedelta(minutes=30 - index))
    smtp = FakeSmtp()
    facteur = Facteur(facteur_settings(), sessions, smtp)
    facteur.deliver_alerts(NOW)
    facteur.deliver_alerts(NOW + timedelta(minutes=5))
    assert len(smtp.sent) == ADMIN_MAILS_PER_DAY
    facteur.deliver_alerts(NOW + timedelta(days=1))
    assert len(smtp.sent) == 30


def test_no_admin_mail_without_an_admin_address(sessions: sessionmaker) -> None:
    """Without MCPLAIN_ADMIN_EMAIL, the alerts stay in their table"""

    add_alert(sessions, "auth", NOW)
    smtp = FakeSmtp()
    Facteur(facteur_settings(admin_email=""), sessions, smtp).deliver_alerts(NOW)
    assert smtp.sent == []


def test_an_admin_mail_that_fails_is_tried_again_later(sessions: sessionmaker) -> None:
    """When the server fails, the alert stays unmailed and the postman waits ten minutes"""

    add_alert(sessions, "auth", NOW)
    smtp = FakeSmtp(failures=1)
    facteur = Facteur(facteur_settings(), sessions, smtp)
    facteur.deliver_alerts(NOW)
    facteur.deliver_alerts(NOW + timedelta(minutes=5))
    assert smtp.sent == []
    facteur.deliver_alerts(NOW + timedelta(minutes=11))
    assert len(smtp.sent) == 1


def test_the_password_is_never_sent_without_starttls() -> None:
    """With a password and without STARTTLS, the postman refuses to log in"""

    from mcplain_api.facteur import send_with_smtp

    class Server:
        """Class that imitates an SMTP connection"""

        def __init__(self, *args: object, **kwargs: object) -> None:
            """Open nothing"""

        def __enter__(self) -> "Server":
            """Return itself"""

            return self

        def __exit__(self, *args: object) -> None:
            """Close nothing"""

        def login(self, user: str, password: str) -> None:
            """Fail the test if a login is tried"""

            raise AssertionError("login without STARTTLS")

        def send_message(self, message: EmailMessage) -> None:
            """Accept the mail"""

    settings = facteur_settings(smtp_user="mcplain", smtp_password=TEST_PASSWORD, smtp_starttls=False)
    message = outbox_message(settings, "verify_email", "en", "ada@example.com", LINK)
    original = smtplib.SMTP
    smtplib.SMTP = Server
    try:
        with pytest.raises(smtplib.SMTPException):
            send_with_smtp(settings, message)
    finally:
        smtplib.SMTP = original
