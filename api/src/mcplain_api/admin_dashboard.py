"""The readings of the admin dashboard: totals per UTC day over 7 or 30 days, never anything about one person"""

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mcplain_api.admin_accounts import AccountDesk
from mcplain_api.ai_budget import day_start, month_start, spent_since
from mcplain_api.db import (
    AI_STATE_ROW,
    AiAdminAlert,
    AiCall,
    AiKind,
    AiState,
    AiStatus,
    AiText,
    Analysis,
    AnalysisState,
    QuotaRefusal,
    SignupRefusal,
    as_utc,
)
from mcplain_api.refunds import failure_code, refund_of
from mcplain_api.settings import Settings

DAY_CHOICES: dict[str, int] = {"7": 7, "30": 30}
TOP_LIMIT = 20
LANGUAGES_LIMIT = 20
ALERTS_LIMIT = 50
TEXTS_LIMIT = 20
ENCODING = "encoding"
GRAY = "gray"
GRAY_ERROR = "error"
UNKNOWN = "unknown"
COLORS: tuple[str, ...] = ("red", "orange", "gray", "green")
UNSUPPORTED_LANGUAGE = "unsupported_language"
SIGNUP_LIMIT = "signup_limit"
QUOTA_PREFIX = "quota_exhausted_"
QUOTA_KINDS: tuple[str, ...] = ("anonymous", "account")
RETRYABLE_TEXTS: tuple[str, ...] = (AiStatus.REJECTED.value, AiStatus.FAILED.value)
FINISHED: tuple[str, ...] = (AnalysisState.DONE.value, AnalysisState.FAILED.value)
AI_KINDS: tuple[str, ...] = tuple(kind.value for kind in AiKind)


def parse_days(value: str | None) -> int | None:
    """Return the length of the period, 7 or 30 days, or None for any other value"""

    if value is None:
        return None
    return DAY_CHOICES.get(value)


def period_start(now: datetime, days: int) -> datetime:
    """Return the start of the first UTC day of a period that ends today"""

    return day_start(now) - timedelta(days=days - 1)


def window(now: datetime, days: int) -> list[date]:
    """Return every UTC day of the period, the oldest first"""

    first = period_start(now, days).date()
    return [first + timedelta(days=index) for index in range(days)]


def day_of(moment: datetime) -> date:
    """Return the UTC day of a stored time"""

    utc = as_utc(moment)
    if utc is None:
        return moment.date()
    return utc.date()


def iso(moment: datetime | None) -> str | None:
    """Return a stored time in ISO 8601 with its time zone, or None"""

    utc = as_utc(moment)
    if utc is None:
        return None
    return utc.isoformat()


def writer_state(session: Session, now: datetime) -> dict[str, Any]:
    """Return whether the writer is cut off or paused for everyone, as codes only"""

    state = session.get(AiState, AI_STATE_ROW)
    disabled = None
    paused_until = None
    if state is not None:
        disabled = state.disabled_reason
        paused = as_utc(state.paused_until)
        if paused is not None and paused > now:
            paused_until = paused.isoformat()
    return {"disabled_reason": disabled, "paused_until": paused_until}


def spend_view(session: Session, settings: Settings, now: datetime, days: int) -> dict[str, Any]:
    """Return what the AI cost today, this month and on each day, with the fuse and the budget the writer checks"""

    days_list = window(now, days)
    per_day: dict[date, dict[str, Any]] = {}
    for day in days_list:
        per_day[day] = {"day": day.isoformat(), "cost_usd": 0.0, "notice_usd": 0.0, "translation_usd": 0.0, "paid_calls": 0}
    by_kind = {kind: 0.0 for kind in AI_KINDS}
    paid_calls = 0
    rows = session.execute(
        select(AiCall.created_at, AiCall.kind, AiCall.cost_usd).where(AiCall.created_at >= period_start(now, days))
    ).all()
    for created_at, kind, cost in rows:
        entry = per_day.get(day_of(created_at))
        if entry is None:
            continue
        entry["cost_usd"] += cost
        if kind in by_kind:
            by_kind[kind] += cost
            entry[kind + "_usd"] += cost
        if cost > 0:
            entry["paid_calls"] += 1
            paid_calls += 1
    today = spent_since(session, day_start(now))
    month = spent_since(session, month_start(now))
    fuse = settings.daily_fuse()
    budget = settings.ai_monthly_budget_usd
    return {
        "days": days,
        "today_usd": today,
        "month_usd": month,
        "daily_fuse_usd": fuse,
        "monthly_budget_usd": budget,
        "fuse_reached": today >= fuse,
        "budget_reached": month >= budget,
        "per_day": [per_day[day] for day in days_list],
        "by_kind": by_kind,
        "paid_calls": paid_calls,
        "writer": writer_state(session, now),
    }


def alert_view(alert: AiAdminAlert) -> dict[str, Any]:
    """Return one alert for the admin: its code, its dates, the kind of text and the HTTP status, never a request identifier"""

    details = alert.details or {}
    kind = details.get("kind")
    if kind not in AI_KINDS:
        kind = None
    status = details.get("status")
    if not isinstance(status, int) or isinstance(status, bool):
        status = None
    return {
        "id": str(alert.id),
        "code": alert.code,
        "created_at": iso(alert.created_at),
        "kind": kind,
        "status": status,
        "emailed_at": iso(alert.emailed_at),
        "read_at": iso(alert.read_at),
    }


def text_view(row: AiText) -> dict[str, Any]:
    """Return one rejected or failed text of the AI: its kind, its language, its state and its report, never a cost"""

    analysis_id = None
    if row.analysis_id is not None:
        analysis_id = str(row.analysis_id)
    return {
        "id": str(row.id),
        "kind": row.kind,
        "lang": row.lang,
        "status": row.status,
        "reject_reason": row.reject_reason,
        "updated_at": iso(row.updated_at),
        "analysis_id": analysis_id,
    }


def ai_view(session: Session, now: datetime, days: int) -> dict[str, Any]:
    """Return the refusals of the AI per reason and per day, the encoding rate, the alerts and the texts to ask again"""

    start = period_start(now, days)
    days_list = window(now, days)
    per_day: dict[date, Counter[str]] = {day: Counter() for day in days_list}
    totals: Counter[str] = Counter()
    encoding = 0
    paid_notices = 0
    rows = session.execute(
        select(AiCall.created_at, AiCall.kind, AiCall.reject_reason, AiCall.cost_usd).where(AiCall.created_at >= start)
    ).all()
    for created_at, kind, reason, cost in rows:
        counts = per_day.get(day_of(created_at))
        if counts is None:
            continue
        if kind == AiKind.NOTICE.value and cost > 0:
            paid_notices += 1
        if reason is None:
            continue
        counts[reason] += 1
        totals[reason] += 1
        if kind == AiKind.NOTICE.value and reason == ENCODING:
            encoding += 1
    rate = None
    if paid_notices:
        rate = encoding / paid_notices
    alerts = session.scalars(
        select(AiAdminAlert)
        .where(AiAdminAlert.created_at >= start)
        .order_by(AiAdminAlert.created_at.desc(), AiAdminAlert.id)
        .limit(ALERTS_LIMIT)
    ).all()
    texts = session.scalars(
        select(AiText)
        .where(AiText.status.in_(RETRYABLE_TEXTS))
        .where(AiText.updated_at >= start)
        .order_by(AiText.updated_at.desc(), AiText.id)
        .limit(TEXTS_LIMIT)
    ).all()
    return {
        "days": days,
        "per_day": [{"day": day.isoformat(), "reasons": dict(sorted(per_day[day].items()))} for day in days_list],
        "reasons": dict(sorted(totals.items())),
        "encoding": {"rejected": encoding, "paid_notice_calls": paid_notices, "rate": rate},
        "alerts": [alert_view(alert) for alert in alerts],
        "texts": [text_view(row) for row in texts],
        "writer": writer_state(session, now),
    }


def ranked(counts: Counter[str], limit: int) -> list[dict[str, Any]]:
    """Return the most frequent codes first, then by name, at most a limit"""

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"code": code, "count": count} for code, count in ordered[:limit]]


def analyses_view(session: Session, now: datetime, days: int) -> dict[str, Any]:
    """Return the analyses per day, the colors, the gray cases, the languages, the failures and the most analyzed MCP"""

    days_list = window(now, days)
    per_day: dict[date, dict[str, Any]] = {}
    for day in days_list:
        per_day[day] = {"day": day.isoformat(), "total": 0, "cached": 0, "new": 0}
    colors: Counter[str] = Counter({color: 0 for color in COLORS})
    gray_cases: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    top: dict[tuple[str, str], dict[str, Any]] = {}
    result = Analysis.result
    rows = session.execute(
        select(
            Analysis.id,
            Analysis.created_at,
            Analysis.state,
            Analysis.from_cache,
            Analysis.error_code,
            result[("verdict", "color")].as_string(),
            result[("verdict", "gray_case")].as_string(),
            result[("status",)].as_string(),
            result[("language",)].as_string(),
            result[("error", "code")].as_string(),
            result[("source", "kind")].as_string(),
            result[("source", "name")].as_string(),
        )
        .where(Analysis.created_at >= period_start(now, days))
        .where(Analysis.state.in_(FINISHED))
    ).all()
    for identifier, created_at, state, from_cache, error_code, color, gray_case, status, language, detail, kind, name in rows:
        entry = per_day.get(day_of(created_at))
        if entry is None:
            continue
        entry["total"] += 1
        if from_cache:
            entry["cached"] += 1
        else:
            entry["new"] += 1
        if state == AnalysisState.FAILED.value:
            color = GRAY
            failures[failure_code(error_code, {"error": {"code": detail}}) or UNKNOWN] += 1
            if gray_case is None:
                gray_case = GRAY_ERROR
        if color not in COLORS:
            color = GRAY
        colors[color] += 1
        if color == GRAY:
            gray_cases[gray_case or UNKNOWN] += 1
        if status == UNSUPPORTED_LANGUAGE:
            languages[language or UNKNOWN] += 1
        if state == AnalysisState.DONE.value and kind and name:
            moment = as_utc(created_at)
            item = top.setdefault((kind, name), {"kind": kind, "name": name, "count": 0, "last": None, "at": None})
            item["count"] += 1
            if item["at"] is None or moment >= item["at"]:
                item["at"] = moment
                item["last"] = str(identifier)
    ordered = sorted(top.values(), key=lambda item: (-item["count"], item["name"], item["kind"]))
    return {
        "days": days,
        "per_day": [per_day[day] for day in days_list],
        "colors": {color: colors[color] for color in COLORS},
        "gray_cases": ranked(gray_cases, len(gray_cases)),
        "languages": ranked(languages, LANGUAGES_LIMIT),
        "failures": [{**item, "refund": refund_of(item["code"]).value} for item in ranked(failures, len(failures))],
        "top": [
            {"kind": item["kind"], "name": item["name"], "count": item["count"], "last_analysis_id": item["last"]}
            for item in ordered[:TOP_LIMIT]
        ],
    }


def refusals_view(session: Session, now: datetime, days: int) -> dict[str, Any]:
    """Return the refused sign-ups and the requests that came with the quota used up, per day, without any address"""

    days_list = window(now, days)
    first = days_list[0]
    kinds = [SIGNUP_LIMIT] + [QUOTA_PREFIX + kind for kind in QUOTA_KINDS]
    per_day: dict[date, dict[str, int]] = {day: {kind: 0 for kind in kinds} for day in days_list}
    for day, count in session.execute(select(SignupRefusal.day, SignupRefusal.count).where(SignupRefusal.day >= first)).all():
        if day in per_day:
            per_day[day][SIGNUP_LIMIT] += count
    for day, kind, count in session.execute(
        select(QuotaRefusal.day, QuotaRefusal.kind, QuotaRefusal.count).where(QuotaRefusal.day >= first)
    ).all():
        if day not in per_day:
            continue
        name = QUOTA_PREFIX + kind
        if name not in kinds:
            kinds.append(name)
            for counts in per_day.values():
                counts.setdefault(name, 0)
        per_day[day][name] += count
    totals = {kind: sum(per_day[day][kind] for day in days_list) for kind in kinds}
    return {
        "days": days,
        "kinds": kinds,
        "per_day": [{"day": day.isoformat(), "counts": per_day[day]} for day in days_list],
        "totals": totals,
    }


def accounts_view(desk: AccountDesk, now: datetime, days: int) -> dict[str, Any] | None:
    """Return the accounts created per UTC day, read from the counter; None when the counter does not answer"""

    counts = desk.created_per_day(days)
    if counts is None:
        return None
    days_list = window(now, days)
    per_day = [{"day": day.isoformat(), "count": counts.get(day.isoformat(), 0)} for day in days_list]
    return {"days": days, "per_day": per_day, "total": sum(item["count"] for item in per_day)}
