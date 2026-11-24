"""Fingerprint of a visitor address: HMAC-SHA256 with the random salt of the UTC day, never the address itself"""

import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mcplain_api.db import AnalysisToken, IpSalt, QuotaUsage, ReportCount, ReportMark, SignupCount

SALT_BYTES = 32
SALT_KEEP_DAYS = 2
UNKNOWN_ADDRESS = "unknown"
FINGERPRINT_SUBJECT_PREFIX = "ip:"


def utc_day(moment: datetime) -> date:
    """Return the UTC day of a moment"""

    return moment.date()


def salt_of_day(session: Session, day: date) -> bytes:
    """Return the salt of a day, created at random the first time it is asked for"""

    stored = session.scalar(select(IpSalt.salt).where(IpSalt.day == day))
    if stored is not None:
        return bytes.fromhex(stored)
    try:
        with session.begin_nested():
            session.add(IpSalt(day=day, salt=secrets.token_hex(SALT_BYTES)))
    except IntegrityError:
        pass
    return bytes.fromhex(session.scalar(select(IpSalt.salt).where(IpSalt.day == day)) or "")


def ip_fingerprint(session: Session, ip: str | None, moment: datetime) -> str:
    """Return the fingerprint of an address for the day of the moment; an unknown address shares one fingerprint"""

    text = ip
    if text is None:
        text = UNKNOWN_ADDRESS
    salt = salt_of_day(session, utc_day(moment))
    return hmac.new(salt, text.encode("utf-8"), hashlib.sha256).hexdigest()


def purge_old_fingerprints(session: Session, moment: datetime) -> None:
    """Delete the salts, the sign-up, quota and report counts, the tokens and the report marks of fingerprints, after two days"""

    oldest_kept = utc_day(moment) - timedelta(days=SALT_KEEP_DAYS - 1)
    session.execute(delete(IpSalt).where(IpSalt.day < oldest_kept))
    session.execute(delete(SignupCount).where(SignupCount.day < oldest_kept))
    session.execute(delete(QuotaUsage).where(QuotaUsage.day < oldest_kept))
    session.execute(delete(AnalysisToken).where(AnalysisToken.day < oldest_kept))
    session.execute(delete(ReportCount).where(ReportCount.day < oldest_kept))
    session.execute(
        delete(ReportMark).where(ReportMark.day < oldest_kept, ReportMark.subject.startswith(FINGERPRINT_SUBJECT_PREFIX))
    )
