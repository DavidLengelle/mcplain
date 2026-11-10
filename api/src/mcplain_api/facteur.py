"""Postman (facteur): the only service that holds the SMTP credentials; it sends the mails of the outbox in plain text"""

import json
import logging
import signal
import smtplib
import ssl
import sys
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import parseaddr
from functools import cache
from pathlib import Path
from types import FrameType

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from mcplain_api.ai_logging import install_secret_filter
from mcplain_api.db import AiAdminAlert, MailKind, MailOutbox, as_utc, make_engine, make_sessions, utc_now

LOGGER = logging.getLogger("mcplain.facteur")
TEXTS_FOLDER = Path(__file__).resolve().parent / "mail_texts"
LANGUAGES: tuple[str, ...] = ("en", "fr")
ADMIN_ALERT = "admin_alert"
POLL_SECONDS = 5.0
BATCH_SIZE = 20
RETRY_DELAYS: tuple[timedelta, ...] = (timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=10))
ALERT_SPACING = timedelta(hours=24)
ADMIN_MAILS_PER_DAY = 20
ADMIN_FAILURE_WAIT = timedelta(minutes=10)
SMTP_TIMEOUT_SECONDS = 20.0
LINK_PREFIXES: tuple[str, ...] = ("http://", "https://")
LINK_MAX_CHARS = 2048
FORBIDDEN_IN_LINE: tuple[str, ...] = ("\r", "\n", " ", "\t")
DATE_FORMAT = "%Y-%m-%d %H:%M"


class FacteurSettings(BaseSettings):
    """Class that holds the settings of the postman: the database, the SMTP server and the address of the admin"""

    model_config = SettingsConfigDict(populate_by_name=True, extra="ignore")

    database_url: str = Field(validation_alias="DATABASE_URL")
    smtp_host: str = Field(default="mailpit", validation_alias="MCPLAIN_SMTP_HOST")
    smtp_port: int = Field(default=1025, ge=1, le=65535, validation_alias="MCPLAIN_SMTP_PORT")
    smtp_user: str | None = Field(default=None, validation_alias="MCPLAIN_SMTP_USER")
    smtp_password: SecretStr | None = Field(default=None, validation_alias="MCPLAIN_SMTP_PASSWORD")
    smtp_from: str = Field(default="MCPlain <no-reply@mcplain.localhost>", validation_alias="MCPLAIN_SMTP_FROM")
    smtp_starttls: bool = Field(default=False, validation_alias="MCPLAIN_SMTP_STARTTLS")
    admin_email: str | None = Field(default=None, validation_alias="MCPLAIN_ADMIN_EMAIL")
    admin_lang: str = Field(default="fr", pattern=r"^(en|fr)$", validation_alias="MCPLAIN_ADMIN_LANG")

    @field_validator("smtp_user", "smtp_password", "admin_email", mode="before")
    @classmethod
    def empty_value_is_none(cls, value: object) -> object:
        """Treat an empty variable, as compose passes it when unset, as no value"""

        if isinstance(value, str) and not value.strip():
            return None
        return value


@dataclass
class Retry:
    """Class that holds how many times a mail failed and when it may be tried again"""

    attempts: int
    next_at: datetime


@cache
def mail_texts(lang: str) -> dict[str, dict[str, str]]:
    """Return the plain text models of one language"""

    return json.loads((TEXTS_FOLDER / f"{lang}.json").read_text(encoding="utf-8"))


def fill(model: str, values: dict[str, str]) -> str:
    """Put each value in its place, without reading any brace of the values themselves"""

    text = model
    for name, value in values.items():
        text = text.replace("{" + name + "}", value)
    return text


def clean_address(text: str) -> str:
    """Return a single mail address, or raise ValueError for anything that could add a header or a second recipient"""

    if any(character in text for character in FORBIDDEN_IN_LINE) or "," in text or text.count("@") != 1:
        raise ValueError("invalid address")
    name, address = parseaddr(text)
    if name or address != text:
        raise ValueError("invalid address")
    local, _, domain = address.partition("@")
    if not local or not domain:
        raise ValueError("invalid address")
    return address


def clean_link(text: str) -> str:
    """Return a link that starts with http or https and holds no space nor line break, or raise ValueError"""

    if not text.startswith(LINK_PREFIXES) or len(text) > LINK_MAX_CHARS:
        raise ValueError("invalid link")
    if any(character in text for character in FORBIDDEN_IN_LINE):
        raise ValueError("invalid link")
    return text


def sender_header(text: str) -> Address:
    """Return the From header of the settings"""

    name, address = parseaddr(text)
    username, _, domain = address.partition("@")
    return Address(display_name=name, username=username, domain=domain)


def plain_message(settings: FacteurSettings, recipient: str, subject: str, body: str) -> EmailMessage:
    """Build a plain text mail, never HTML"""

    message = EmailMessage()
    message["From"] = sender_header(settings.smtp_from)
    message["To"] = clean_address(recipient)
    message["Subject"] = subject
    message.set_content(body, subtype="plain", charset="utf-8")
    return message


def outbox_message(settings: FacteurSettings, kind: str, lang: str, recipient: str, link: str) -> EmailMessage:
    """Build the mail of one row of the outbox, in its language"""

    if kind not in {item.value for item in MailKind} or lang not in LANGUAGES:
        raise ValueError("unknown mail")
    model = mail_texts(lang)[kind]
    return plain_message(settings, recipient, model["subject"], fill(model["body"], {"link": clean_link(link)}))


def alert_message(settings: FacteurSettings, code: str, count: int, first: datetime, last: datetime) -> EmailMessage:
    """Build the mail for the admin: the code, the dates and the number of alerts, never a key nor a text of a third party"""

    model = mail_texts(settings.admin_lang)[ADMIN_ALERT]
    values = {"code": code, "count": str(count), "first": first.strftime(DATE_FORMAT), "last": last.strftime(DATE_FORMAT)}
    return plain_message(settings, settings.admin_email or "", fill(model["subject"], values), fill(model["body"], values))


def send_with_smtp(settings: FacteurSettings, message: EmailMessage) -> None:
    """Send one mail; the password is only ever given over STARTTLS"""

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
        if settings.smtp_starttls:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_user and settings.smtp_password is not None:
            if not settings.smtp_starttls:
                raise smtplib.SMTPException("refusing to send the SMTP password without STARTTLS")
            smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


class Facteur:
    """Class that empties the outbox every five seconds and mails the admin alerts"""

    def __init__(
        self,
        settings: FacteurSettings,
        sessions: sessionmaker,
        sender: Callable[[FacteurSettings, EmailMessage], None] = send_with_smtp,
    ) -> None:
        """Keep the settings, the database and the way to send, with no mail failed yet"""

        self.settings = settings
        self.sessions = sessions
        self.sender = sender
        self.retries: dict[uuid.UUID, Retry] = {}
        self.alerts_paused_until: datetime | None = None
        self.stopping = threading.Event()

    def tick(self, now: datetime) -> None:
        """Do one round: the outbox first, then the admin alerts"""

        self.deliver_outbox(now)
        self.deliver_alerts(now)

    def deliver_outbox(self, now: datetime) -> None:
        """Send the waiting mails, delete each row once handled, and give up after three more tries"""

        with self.sessions() as session:
            rows = session.scalars(select(MailOutbox).order_by(MailOutbox.created_at).limit(BATCH_SIZE)).all()
        for row in rows:
            retry = self.retries.get(row.id)
            if retry is not None and retry.next_at > now:
                continue
            try:
                message = outbox_message(self.settings, row.kind, row.lang, row.recipient, row.link)
            except ValueError:
                self.drop(row.id)
                LOGGER.warning("mail %s (%s) dropped: the row is not a valid mail", row.id, row.kind)
                continue
            try:
                self.sender(self.settings, message)
            except (smtplib.SMTPException, OSError) as error:
                self.failed(row.id, row.kind, retry, now, type(error).__name__)
                continue
            self.drop(row.id)
            LOGGER.info("mail %s (%s) sent", row.id, row.kind)

    def failed(self, identifier: uuid.UUID, kind: str, retry: Retry | None, now: datetime, error: str) -> None:
        """Plan the next try of a mail, or delete it after the last one; the log never holds the link nor the address"""

        attempts = 1
        if retry is not None:
            attempts = retry.attempts + 1
        if attempts > len(RETRY_DELAYS):
            self.drop(identifier)
            LOGGER.warning("mail %s (%s) dropped after %d attempts: %s", identifier, kind, attempts, error)
            return
        self.retries[identifier] = Retry(attempts=attempts, next_at=now + RETRY_DELAYS[attempts - 1])
        LOGGER.warning("mail %s (%s) failed, attempt %d: %s", identifier, kind, attempts, error)

    def drop(self, identifier: uuid.UUID) -> None:
        """Delete a row of the outbox, and forget its failures"""

        self.retries.pop(identifier, None)
        with self.sessions.begin() as session:
            session.execute(delete(MailOutbox).where(MailOutbox.id == identifier))

    def deliver_alerts(self, now: datetime) -> None:
        """Mail the admin at most once per alert code every 24 hours, and at most 20 times per UTC day"""

        if self.settings.admin_email is None:
            return
        if self.alerts_paused_until is not None and self.alerts_paused_until > now:
            return
        with self.sessions.begin() as session:
            pending = session.scalars(
                select(AiAdminAlert).where(AiAdminAlert.emailed_at.is_(None)).order_by(AiAdminAlert.created_at)
            ).all()
            if not pending:
                return
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            sent_today = session.scalar(
                select(func.count()).select_from(
                    select(AiAdminAlert.code, AiAdminAlert.emailed_at)
                    .where(AiAdminAlert.emailed_at >= day_start)
                    .distinct()
                    .subquery()
                )
            ) or 0
            groups: dict[str, list[AiAdminAlert]] = {}
            for alert in pending:
                groups.setdefault(alert.code, []).append(alert)
            for code, alerts in groups.items():
                if sent_today >= ADMIN_MAILS_PER_DAY:
                    return
                last_mail = as_utc(session.scalar(select(func.max(AiAdminAlert.emailed_at)).where(AiAdminAlert.code == code)))
                if last_mail is not None and last_mail > now - ALERT_SPACING:
                    continue
                first = as_utc(alerts[0].created_at) or now
                last = as_utc(alerts[-1].created_at) or now
                try:
                    self.sender(self.settings, alert_message(self.settings, code, len(alerts), first, last))
                except (smtplib.SMTPException, OSError, ValueError) as error:
                    self.alerts_paused_until = now + ADMIN_FAILURE_WAIT
                    LOGGER.warning("admin mail for %s failed: %s", code, type(error).__name__)
                    return
                identifiers = [alert.id for alert in alerts]
                session.execute(update(AiAdminAlert).where(AiAdminAlert.id.in_(identifiers)).values(emailed_at=now))
                sent_today += 1
                LOGGER.info("admin mail sent for %s (%d alerts)", code, len(alerts))

    def run_forever(self) -> None:
        """Do a round every five seconds until stopped; a database error waits for the next round"""

        while not self.stopping.is_set():
            try:
                self.tick(utc_now())
            except SQLAlchemyError as error:
                LOGGER.warning("database error: %s", type(error).__name__)
            self.stopping.wait(POLL_SECONDS)

    def stop(self) -> None:
        """Stop after the current round"""

        self.stopping.set()


def main() -> int:
    """Run the postman until SIGTERM or SIGINT"""

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = FacteurSettings()
    secret = None
    if settings.smtp_password is not None:
        secret = settings.smtp_password.get_secret_value()
    install_secret_filter(secret)
    engine = make_engine(settings.database_url)
    facteur = Facteur(settings, make_sessions(engine))

    def stop(signal_number: int, frame: FrameType | None) -> None:
        """Stop taking new mails"""

        facteur.stop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOGGER.info("postman started, admin mails on: %s", settings.admin_email is not None)
    facteur.run_forever()
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
