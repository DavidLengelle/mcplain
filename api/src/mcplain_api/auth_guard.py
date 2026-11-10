"""Guard asked by the counter (guichet) before a sign-up, a sign-in or a password reset: ALTCHA, then the sign-up limit"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mcplain_api.altcha_gate import accept_solution
from mcplain_api.client_ip import FORWARDED_FOR, visitor_ip
from mcplain_api.db import SignupCount, SignupRefusal
from mcplain_api.ip_fingerprint import ip_fingerprint, purge_old_fingerprints, utc_day
from mcplain_api.settings import Settings


class GuardAction(StrEnum):
    """Class that lists the actions of the counter that go through the guard"""

    SIGN_UP = "sign_up"
    SIGN_IN = "sign_in"
    REQUEST_PASSWORD_RESET = "request_password_reset"


class Refusal(StrEnum):
    """Class that lists why the guard refuses an action"""

    ALTCHA_INVALID = "altcha_invalid"
    SIGNUP_LIMIT = "signup_limit"


@dataclass(frozen=True)
class GuardAnswer:
    """Class that holds the answer of the guard: ok, or the code of the refusal"""

    ok: bool
    code: str | None = None


def check_action(
    sessions: sessionmaker,
    settings: Settings,
    action: GuardAction,
    altcha: str | None,
    ip_headers: dict[str, str],
    moment: datetime,
) -> GuardAnswer:
    """Check the ALTCHA solution; for a sign-up, also count it against the daily limit of the address fingerprint"""

    forwarded = [value for name, value in ip_headers.items() if name.lower() == FORWARDED_FOR]
    ip = visitor_ip(forwarded, None, settings.trusted_proxy_hops)
    with sessions.begin() as session:
        purge_old_fingerprints(session, moment)
        if not accept_solution(session, settings, altcha, moment):
            return GuardAnswer(ok=False, code=Refusal.ALTCHA_INVALID.value)
        if action != GuardAction.SIGN_UP:
            return GuardAnswer(ok=True)
        day = utc_day(moment)
        row = signup_row(session, day, ip_fingerprint(session, ip, moment))
        if row.count >= settings.signups_per_ip_per_day:
            count_refusal(session, day)
            return GuardAnswer(ok=False, code=Refusal.SIGNUP_LIMIT.value)
        row.count += 1
    return GuardAnswer(ok=True)


def signup_row(session: Session, day: date, fingerprint: str) -> SignupCount:
    """Return the locked sign-up count of a fingerprint for a day, created at zero when it does not exist"""

    query = select(SignupCount).where(SignupCount.day == day, SignupCount.ip_hash == fingerprint).with_for_update()
    row = session.scalar(query)
    if row is not None:
        return row
    try:
        with session.begin_nested():
            session.add(SignupCount(day=day, ip_hash=fingerprint, count=0))
    except IntegrityError:
        pass
    return session.scalars(query).one()


def count_refusal(session: Session, day: date) -> None:
    """Add one refusal for too many accounts from one network to the count of the day, without any address"""

    query = select(SignupRefusal).where(SignupRefusal.day == day).with_for_update()
    row = session.scalar(query)
    if row is None:
        try:
            with session.begin_nested():
                session.add(SignupRefusal(day=day, count=0))
        except IntegrityError:
            pass
        row = session.scalars(query).one()
    row.count += 1
