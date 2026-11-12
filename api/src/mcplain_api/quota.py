"""Quotas of new analyses per UTC day, the burst limit per hour, and the tokens given back once"""

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from mcplain_api.db import AnalysisToken, BurstCount, QuotaRefusal, QuotaUsage, UserHistory
from mcplain_api.ip_fingerprint import utc_day
from mcplain_api.session_user import ROLE_ADMIN, ROLE_BENCH, CurrentUser
from mcplain_api.settings import Settings

BURST_WINDOW = timedelta(hours=1)
SECONDS_PER_MINUTE = 60
IP_PREFIX = "ip:"
USER_PREFIX = "user:"
INSERTS: dict[str, Any] = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}


class VisitorKind(StrEnum):
    """Class that lists who asks for an analysis, as the quota sees it"""

    ANONYMOUS = "anonymous"
    ACCOUNT = "account"
    ADMIN = "admin"
    BENCH = "bench"


UNLIMITED_KINDS: frozenset[VisitorKind] = frozenset({VisitorKind.ADMIN, VisitorKind.BENCH})


@dataclass(frozen=True)
class Visitor:
    """Class that holds the kind of a visitor, the subject its counts are kept under, and its account if any"""

    kind: VisitorKind
    subject: str
    user_id: str | None


def visitor_kind(user: CurrentUser | None, settings: Settings) -> VisitorKind:
    """Return the kind of a visitor; a bench account counts as a normal one unless the setting allows the bench role"""

    if user is None:
        return VisitorKind.ANONYMOUS
    if user.role == ROLE_ADMIN:
        return VisitorKind.ADMIN
    if user.role == ROLE_BENCH and settings.allow_bench_role:
        return VisitorKind.BENCH
    return VisitorKind.ACCOUNT


def make_visitor(user: CurrentUser | None, fingerprint: str, settings: Settings) -> Visitor:
    """Return the visitor: an account is counted by its id, anybody else by the fingerprint of its address"""

    kind = visitor_kind(user, settings)
    if user is None:
        return Visitor(kind, IP_PREFIX + fingerprint, None)
    return Visitor(kind, USER_PREFIX + user.id, user.id)


def user_subject(user_id: str) -> str:
    """Return the subject under which the counts of an account are kept"""

    return USER_PREFIX + user_id


def daily_limit(kind: VisitorKind, settings: Settings) -> int | None:
    """Return the number of new analyses a day for a kind of visitor, or None without limit"""

    if kind in UNLIMITED_KINDS:
        return None
    if kind is VisitorKind.ACCOUNT:
        return settings.quota_account
    return settings.quota_anonymous


def _insert(session: Session) -> Any:
    """Return the insert construct of the database in use, which knows ON CONFLICT"""

    return INSERTS[session.get_bind().dialect.name]


def take_token(session: Session, day: date, visitor: Visitor, limit: int) -> bool:
    """Take one token in a single SQL statement: insert at one, or add one only while under the limit"""

    insert = _insert(session)
    statement = (
        insert(QuotaUsage)
        .values(day=day, subject=visitor.subject, kind=visitor.kind.value, count=1)
        .on_conflict_do_update(
            index_elements=[QuotaUsage.day, QuotaUsage.subject],
            set_={"count": QuotaUsage.count + 1},
            where=QuotaUsage.count < limit,
        )
        .returning(QuotaUsage.count)
    )
    return session.execute(statement).first() is not None


def tokens_used(session: Session, day: date, subject: str) -> int:
    """Return how many tokens a subject holds for a day"""

    used = session.scalar(select(QuotaUsage.count).where(QuotaUsage.day == day, QuotaUsage.subject == subject))
    return used or 0


def refund_token(session: Session, analysis_id: uuid.UUID, moment: datetime) -> bool:
    """Give back the token of an analysis, only once: the mark and the count change in the same transaction"""

    token = session.execute(
        update(AnalysisToken)
        .where(AnalysisToken.analysis_id == analysis_id, AnalysisToken.refunded_at.is_(None))
        .values(refunded_at=moment)
        .returning(AnalysisToken.day, AnalysisToken.subject)
    ).first()
    if token is None:
        return False
    session.execute(
        update(QuotaUsage)
        .where(QuotaUsage.day == token.day, QuotaUsage.subject == token.subject, QuotaUsage.count > 0)
        .values(count=QuotaUsage.count - 1)
    )
    return True


def count_quota_refusal(session: Session, day: date, kind: str) -> None:
    """Count one request that ended without analysis because the quota was used up, without any address"""

    insert = _insert(session)
    session.execute(
        insert(QuotaRefusal)
        .values(day=day, kind=kind, count=1)
        .on_conflict_do_update(index_elements=[QuotaRefusal.day, QuotaRefusal.kind], set_={"count": QuotaRefusal.count + 1})
    )


def burst_wait(session: Session, subject: str, moment: datetime, limit: int) -> int | None:
    """Count one request in the sliding hour, or return the seconds to wait when the limit is already reached"""

    start = moment - BURST_WINDOW
    session.execute(delete(BurstCount).where(BurstCount.minute <= start))
    in_window = (BurstCount.subject == subject, BurstCount.minute > start)
    total = session.scalar(select(func.coalesce(func.sum(BurstCount.count), 0)).where(*in_window)) or 0
    if total >= limit:
        oldest = session.scalar(select(func.min(BurstCount.minute)).where(*in_window))
        return _seconds_until(oldest, moment)
    minute = moment.replace(second=0, microsecond=0)
    insert = _insert(session)
    session.execute(
        insert(BurstCount)
        .values(subject=subject, minute=minute, count=1)
        .on_conflict_do_update(
            index_elements=[BurstCount.subject, BurstCount.minute], set_={"count": BurstCount.count + 1}
        )
    )
    return None


def _seconds_until(oldest: datetime | None, moment: datetime) -> int:
    """Return the whole seconds until the oldest minute leaves the sliding hour, at least one"""

    if oldest is None:
        return 1
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=UTC)
    remaining = (oldest + BURST_WINDOW - moment).total_seconds()
    return max(1, math.ceil(remaining))


def minutes_to_wait(seconds: int) -> int:
    """Return the minutes shown to the visitor for a wait in seconds, at least one"""

    return max(1, math.ceil(seconds / SECONDS_PER_MINUTE))


def next_reset(moment: datetime) -> datetime:
    """Return the next midnight UTC, when the daily quotas come back"""

    return datetime.combine(utc_day(moment) + timedelta(days=1), time(0), tzinfo=UTC)


def erase_account(session: Session, user_id: str) -> None:
    """Delete the history, the quota rows, the tokens and the burst counts of an account"""

    subject = user_subject(user_id)
    session.execute(delete(UserHistory).where(UserHistory.user_id == user_id))
    session.execute(delete(QuotaUsage).where(QuotaUsage.subject == subject))
    session.execute(delete(AnalysisToken).where(AnalysisToken.subject == subject))
    session.execute(delete(BurstCount).where(BurstCount.subject == subject))
