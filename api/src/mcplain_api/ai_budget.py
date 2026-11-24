"""What the AI spent and may still spend: the one place the writer, the admin dashboard and the postman read it from"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mcplain_api.ai_client import call_cost
from mcplain_api.ai_form import canonical_json
from mcplain_api.db import AiCall, CreditEntry, CreditKind, as_utc
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


@dataclass(frozen=True)
class Balance:
    """Class that holds the estimated credit: the last statement, the top-ups and the spend since; no amount without statement"""

    amount_usd: float | None
    statement_usd: float | None
    statement_at: datetime | None
    top_ups_usd: float
    spent_usd: float


def estimated_balance(session: Session) -> Balance:
    """Return the last statement plus the top-ups since it, minus what ai_calls recorded since it"""

    statement = session.scalars(
        select(CreditEntry)
        .where(CreditEntry.kind == CreditKind.STATEMENT.value)
        .order_by(CreditEntry.created_at.desc(), CreditEntry.id.desc())
        .limit(1)
    ).first()
    if statement is None:
        return Balance(None, None, None, 0.0, 0.0)
    moment = as_utc(statement.created_at) or statement.created_at
    top_ups = session.scalar(
        select(func.coalesce(func.sum(CreditEntry.amount_usd), 0.0))
        .where(CreditEntry.kind == CreditKind.TOP_UP.value)
        .where(CreditEntry.created_at > statement.created_at)
    )
    added = float(top_ups or 0.0)
    spent = spent_since(session, moment)
    return Balance(statement.amount_usd + added - spent, statement.amount_usd, moment, added, spent)


def is_low(balance: Balance, threshold: float) -> bool:
    """Tell whether the estimated credit is under the threshold; never without a statement"""

    return balance.amount_usd is not None and balance.amount_usd < threshold

