"""What the AI spent and may still spend: the one place the writer, the admin dashboard and the postman read it from"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mcplain_api.ai_client import call_cost
from mcplain_api.ai_form import canonical_json
from mcplain_api.db import AiCall
from mcplain_api.settings import Settings

CALLS_PER_TEXT_PER_DAY = 4
BYTES_PER_TOKEN_ESTIMATE = 2
REASON_DAILY_FUSE = "daily_fuse"
REASON_MONTHLY_BUDGET = "monthly_budget"


def day_start(moment: datetime) -> datetime:
    """Return the start of the UTC day of a moment"""

    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def month_start(moment: datetime) -> datetime:
    """Return the start of the UTC month of a moment"""

    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_day(moment: datetime) -> datetime:
    """Return the start of the next UTC day"""

    return day_start(moment) + timedelta(days=1)


def next_month(moment: datetime) -> datetime:
    """Return the start of the next UTC month"""

    return (month_start(moment) + timedelta(days=32)).replace(day=1)


def spent_since(session: Session, start: datetime) -> float:
    """Return what the calls recorded since a moment cost, in US dollars"""

    total = session.scalar(select(func.coalesce(func.sum(AiCall.cost_usd), 0.0)).where(AiCall.created_at >= start))
    return float(total or 0.0)


def worst_cost(settings: Settings, body: dict[str, Any]) -> float:
    """Return the most a call can cost: the input estimated from its size, and all of max_tokens as output"""

    size = len(canonical_json(body).encode("utf-8"))
    return call_cost(settings, size // BYTES_PER_TOKEN_ESTIMATE, body["max_tokens"])


def budget_reason(session: Session, settings: Settings, worst: float, now: datetime) -> tuple[str, datetime] | None:
    """Return why the budget forbids a call of this cost, and when it can come back"""

    if spent_since(session, month_start(now)) + worst > settings.ai_monthly_budget_usd:
        return REASON_MONTHLY_BUDGET, next_month(now)
    if spent_since(session, day_start(now)) + worst > settings.daily_fuse():
        return REASON_DAILY_FUSE, next_day(now)
    return None


def calls_today(session: Session, text_id: uuid.UUID, now: datetime) -> int:
    """Return how many calls one text made since the start of the UTC day"""

    count = session.scalar(
        select(func.count()).select_from(AiCall).where(AiCall.text_id == text_id).where(AiCall.created_at >= day_start(now))
    )
    return int(count or 0)
