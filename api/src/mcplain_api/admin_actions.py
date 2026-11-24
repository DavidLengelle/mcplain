"""The actions of the admin: ask a text of the AI again, analyze again without the cache, mark an alert as read"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from mcplain_api.admin_journal import Action, record_action
from mcplain_api.ai_budget import CALLS_PER_TEXT_PER_DAY, REASON_DAILY_FUSE, budget_reason, calls_today, worst_cost
from mcplain_api.db import (
    AI_STATE_ROW,
    AdminTarget,
    AiAdminAlert,
    AiState,
    AiStatus,
    AiText,
    Analysis,
    AnalysisState,
    as_utc,
)
from mcplain_api.redacteur import Redacteur, validated_report
from mcplain_api.settings import Settings

RETRYABLE: frozenset[str] = frozenset({AiStatus.REJECTED.value, AiStatus.FAILED.value})
FINISHED: frozenset[str] = frozenset({AnalysisState.DONE.value, AnalysisState.FAILED.value})


class Retry(StrEnum):
    """Class that lists how asking a text again can end"""

    QUEUED = "queued"
    NOT_FOUND = "not_found"
    NOT_RETRYABLE = "not_retryable"
    NO_REPORT = "no_report"
    DISABLED = "disabled"
    PAUSED = "paused"
    DAILY_TEXT_CAP = "daily_text_cap"
    DAILY_FUSE = "daily_fuse"
    MONTHLY_BUDGET = "monthly_budget"


class Rerun(StrEnum):
    """Class that lists how analyzing again can end"""

    QUEUED = "queued"
    NOT_FOUND = "not_found"
    NOT_FINISHED = "not_finished"
    QUEUE_FULL = "queue_full"


@dataclass(frozen=True)
class RetryAnswer:
    """Class that holds how asking a text again ended, and the state or the date that explains it"""

    outcome: Retry
    detail: str | None = None


def global_block(session: Session, now: datetime) -> RetryAnswer | None:
    """Return why the writer takes no text at all now: cut off, or paused for everyone"""

    state = session.get(AiState, AI_STATE_ROW)
    if state is None:
        return None
    if state.disabled_reason is not None:
        return RetryAnswer(Retry.DISABLED, state.disabled_reason)
    paused_until = as_utc(state.paused_until)
    if paused_until is not None and paused_until > now:
        return RetryAnswer(Retry.PAUSED, paused_until.isoformat())
    return None


def retry_text(session: Session, sessions: sessionmaker, settings: Settings, text_id: uuid.UUID, now: datetime) -> RetryAnswer:
    """Queue a rejected or failed text again; the pause, the cap of 4 calls and the fuses of the writer always apply"""

    row = session.scalars(select(AiText).where(AiText.id == text_id).with_for_update()).first()
    if row is None:
        return RetryAnswer(Retry.NOT_FOUND)
    if row.status not in RETRYABLE:
        return RetryAnswer(Retry.NOT_RETRYABLE, row.status)
    blocked = global_block(session, now)
    if blocked is not None:
        return blocked
    if calls_today(session, row.id, now) >= CALLS_PER_TEXT_PER_DAY:
        return RetryAnswer(Retry.DAILY_TEXT_CAP)
    report = validated_report(session, row)
    prepared = None
    if report is not None:
        prepared = Redacteur(settings, sessions)._prepare(row, report)
    if prepared is None:
        return RetryAnswer(Retry.NO_REPORT)
    refused = budget_reason(session, settings, worst_cost(settings, prepared.body), now)
    if refused is not None:
        reason, back_at = refused
        if reason == REASON_DAILY_FUSE:
            return RetryAnswer(Retry.DAILY_FUSE, back_at.isoformat())
        return RetryAnswer(Retry.MONTHLY_BUDGET, back_at.isoformat())
    row.status = AiStatus.PENDING.value
    row.retry_at = None
    row.reject_reason = None
    row.updated_at = now
    record_action(session, Action.TEXT_RETRY, AdminTarget.TEXT, str(row.id), now)
    return RetryAnswer(Retry.QUEUED)


def rerun_analysis(session: Session, settings: Settings, analysis_id: uuid.UUID, now: datetime) -> tuple[Rerun, uuid.UUID | None]:
    """Queue a new analysis of the same request that skips the cache, without quota nor token; a success replaces the cache"""

    target = session.get(Analysis, analysis_id)
    if target is None:
        return Rerun.NOT_FOUND, None
    if target.state not in FINISHED:
        return Rerun.NOT_FINISHED, None
    waiting = session.scalar(select(func.count()).select_from(Analysis).where(Analysis.state == AnalysisState.QUEUED.value))
    if (waiting or 0) >= settings.max_queued:
        return Rerun.QUEUE_FULL, None
    rerun = Analysis(
        id=uuid.uuid4(),
        input_raw=target.input_raw,
        select=target.select,
        state=AnalysisState.QUEUED.value,
        ignore_cache=True,
        cache_only=False,
        created_at=now,
    )
    session.add(rerun)
    session.flush()
    record_action(session, Action.ANALYSIS_RERUN, AdminTarget.ANALYSIS, str(rerun.id), now)
    return Rerun.QUEUED, rerun.id


def mark_read(session: Session, alert_id: uuid.UUID, now: datetime) -> bool:
    """Mark an alert as read, once; False when it does not exist"""

    alert = session.get(AiAdminAlert, alert_id)
    if alert is None:
        return False
    if alert.read_at is None:
        alert.read_at = now
        record_action(session, Action.ALERT_READ, AdminTarget.ALERT, str(alert.id), now)
    return True
