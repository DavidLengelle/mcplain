"""What POST /api/analyses checks before creating an analysis: burst limit, ALTCHA, then the token, in this order"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from mcplain_api.altcha_gate import accept_solution
from mcplain_api.db import Analysis, AnalysisState, AnalysisToken
from mcplain_api.history import record_request
from mcplain_api.ip_fingerprint import ip_fingerprint, purge_old_fingerprints, utc_day
from mcplain_api.quota import (
    UNLIMITED_KINDS,
    Visitor,
    burst_wait,
    count_quota_refusal,
    daily_limit,
    make_visitor,
    next_reset,
    take_token,
    tokens_used,
)
from mcplain_api.session_user import CurrentUser
from mcplain_api.settings import Settings

BURST_LIMIT = "burst_limit"
ALTCHA_INVALID = "altcha_invalid"


class QueueFull(Exception):
    """Class for a request refused because too many analyses are waiting"""


@dataclass(frozen=True)
class Admission:
    """Class that holds the visitor let in, or the code of the refusal and the seconds to wait"""

    visitor: Visitor | None
    code: str | None = None
    retry_after: int | None = None


@dataclass(frozen=True)
class Created:
    """Class that holds a new analysis and whether it may only be served from the cache"""

    id: uuid.UUID
    cache_only: bool


def admit(
    sessions: sessionmaker,
    settings: Settings,
    user: CurrentUser | None,
    ip: str | None,
    altcha: str | None,
    moment: datetime,
) -> Admission:
    """Count the request against the burst limit, unless the visitor has none, then check the ALTCHA solution"""

    with sessions.begin() as session:
        purge_old_fingerprints(session, moment)
        visitor = make_visitor(user, ip_fingerprint(session, ip, moment), settings)
        if visitor.kind not in UNLIMITED_KINDS:
            wait = burst_wait(session, visitor.subject, moment, settings.burst_per_hour)
            if wait is not None:
                return Admission(None, BURST_LIMIT, wait)
        if not accept_solution(session, settings, altcha, moment):
            return Admission(None, ALTCHA_INVALID)
    return Admission(visitor)


def enqueue(
    sessions: sessionmaker,
    settings: Settings,
    visitor: Visitor,
    text_input: str,
    selection: str | None,
    moment: datetime,
) -> Created:
    """Take a token and create the analysis in one transaction; without token left, create a cache-only request"""

    with sessions.begin() as session:
        waiting = session.scalar(
            select(func.count()).select_from(Analysis).where(Analysis.state == AnalysisState.QUEUED.value)
        )
        if (waiting or 0) >= settings.max_queued:
            raise QueueFull()
        day = utc_day(moment)
        limit = daily_limit(visitor.kind, settings)
        took = False
        cache_only = False
        if limit is not None:
            took = take_token(session, day, visitor, limit)
            cache_only = not took
        if cache_only:
            count_quota_refusal(session, day, visitor.kind.value)
        row = Analysis(
            input_raw=text_input,
            select=selection,
            state=AnalysisState.QUEUED.value,
            cache_only=cache_only,
            created_at=moment,
        )
        session.add(row)
        session.flush()
        if took:
            session.add(AnalysisToken(analysis_id=row.id, day=day, subject=visitor.subject))
        if visitor.user_id is not None:
            record_request(session, visitor.user_id, row, moment)
        return Created(row.id, cache_only)


def quota_view(
    sessions: sessionmaker,
    settings: Settings,
    user: CurrentUser | None,
    ip: str | None,
    moment: datetime,
) -> dict[str, Any]:
    """Return the kind of the visitor, its daily limit, what it used and when it comes back; nothing is counted"""

    with sessions.begin() as session:
        visitor = make_visitor(user, ip_fingerprint(session, ip, moment), settings)
        used = tokens_used(session, utc_day(moment), visitor.subject)
    limit = daily_limit(visitor.kind, settings)
    remaining = None
    if limit is not None:
        remaining = max(0, limit - used)
    return {
        "kind": visitor.kind.value,
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "resets_at": next_reset(moment).isoformat(),
    }
