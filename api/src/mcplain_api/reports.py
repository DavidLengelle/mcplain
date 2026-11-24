"""Reports of the visitors about a report: ALTCHA, the daily limits, the box of the whole site, the admin list and the erasing"""

import unicodedata
import uuid
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mcplain_api.admin_journal import Action, record_action
from mcplain_api.ai_budget import day_start
from mcplain_api.altcha_gate import accept_solution
from mcplain_api.db import (
    REPORT_COMMENT_MAX_CHARS,
    AdminTarget,
    AiAdminAlert,
    Analysis,
    AnalysisState,
    Report,
    ReportCount,
    ReporterKind,
    ReportKind,
    ReportMark,
    ReportStatus,
    as_utc,
)
from mcplain_api.ip_fingerprint import ip_fingerprint, purge_old_fingerprints, utc_day
from mcplain_api.quota import Visitor, VisitorKind, count_quota_refusal, make_visitor, take_slot, user_subject
from mcplain_api.session_user import CurrentUser
from mcplain_api.settings import Settings

REPORTS_SHOWN = 50
COMMENT_KEPT = timedelta(days=90)
SITE_SUBJECT = "site"
SITE_KIND = "site"
REPORT_LIMIT = "report_limit"
REPORT_GLOBAL = "report_global"
BOX_FULL_ALERT = "report_box_full"
KEPT_CONTROLS: frozenset[str] = frozenset({"\n"})
DROPPED_CATEGORIES: frozenset[str] = frozenset({"Cc", "Cs"})
COLORS: tuple[str, ...] = ("red", "orange", "gray", "green")
GRAY = "gray"
FINISHED: tuple[str, ...] = (AnalysisState.DONE.value, AnalysisState.FAILED.value)
CLOSED: tuple[str, ...] = (ReportStatus.HANDLED.value, ReportStatus.REJECTED.value)
STATUS_ACTIONS: dict[str, Action] = {
    ReportStatus.HANDLED.value: Action.REPORT_HANDLED,
    ReportStatus.REJECTED.value: Action.REPORT_REJECTED,
}
KINDS: frozenset[str] = frozenset(kind.value for kind in ReportKind)
STATUSES: frozenset[str] = frozenset(status.value for status in ReportStatus)


class Sent(StrEnum):
    """Class that tells how a report ended: kept, or refused and why"""

    SENT = "sent"
    NOT_FOUND = "not_found"
    NOT_FINISHED = "not_finished"
    ALTCHA_INVALID = "altcha_invalid"
    DUPLICATE = "report_duplicate"
    LIMIT = "report_limit"
    BOX_FULL = "report_global"


class Change(StrEnum):
    """Class that tells how a change of status ended"""

    DONE = "done"
    UNCHANGED = "unchanged"
    NOT_FOUND = "not_found"


class Refused(Exception):
    """Class for a report refused by a limit, raised to give back what the savepoint took"""

    def __init__(self, outcome: Sent) -> None:
        """Keep the reason of the refusal"""

        super().__init__(outcome.value)
        self.outcome = outcome


def comment_fits(text: str | None) -> bool:
    """Tell whether a comment holds at most 500 characters, as sent"""

    return text is None or len(text) <= REPORT_COMMENT_MAX_CHARS


def clean_comment(text: str | None) -> str | None:
    """Return the comment as plain text without control characters, nor the spaces around it; None when nothing is left"""

    if text is None:
        return None
    kept = "".join(
        character
        for character in text
        if character in KEPT_CONTROLS or unicodedata.category(character) not in DROPPED_CATEGORIES
    )
    kept = kept.strip()
    if not kept:
        return None
    return kept


def color_of(row: Analysis) -> str | None:
    """Return the color the report had: gray for a failed analysis, the color of the verdict otherwise"""

    if row.state == AnalysisState.FAILED.value:
        return GRAY
    result = row.result or {}
    verdict = result.get("verdict")
    if not isinstance(verdict, dict):
        return None
    color = verdict.get("color")
    if color in COLORS:
        return color
    return GRAY


def take_report_slots(
    session: Session, settings: Settings, visitor: Visitor, analysis_id: uuid.UUID, kind: str, day: date
) -> Sent | None:
    """Mark the report once per kind and analysis, then take one slot of the sender and one of the site; all or nothing"""

    try:
        with session.begin_nested():
            session.add(ReportMark(subject=visitor.subject, analysis_id=analysis_id, kind=kind, day=day))
            session.flush()
            if not take_slot(session, ReportCount, day, visitor.subject, visitor.kind.value, settings.reports_per_day):
                raise Refused(Sent.LIMIT)
            if not take_slot(session, ReportCount, day, SITE_SUBJECT, SITE_KIND, settings.reports_global_per_day):
                raise Refused(Sent.BOX_FULL)
    except IntegrityError:
        return Sent.DUPLICATE
    except Refused as refused:
        return refused.outcome
    return None


def note_box_full(session: Session, settings: Settings, moment: datetime) -> None:
    """Add one alert for the admin when the box of the site is full, at most once per UTC day"""

    already = session.scalar(
        select(AiAdminAlert.id)
        .where(AiAdminAlert.code == BOX_FULL_ALERT, AiAdminAlert.created_at >= day_start(moment))
        .limit(1)
    )
    if already is None:
        session.add(AiAdminAlert(code=BOX_FULL_ALERT, created_at=moment, details={"limit": settings.reports_global_per_day}))


def send_report(
    sessions: sessionmaker,
    settings: Settings,
    user: CurrentUser | None,
    ip: str | None,
    altcha: str | None,
    analysis_id: uuid.UUID,
    kind: str,
    comment: str | None,
    moment: datetime,
) -> Sent:
    """Keep a report about a finished analysis after ALTCHA and the limits; a refusal by a limit is counted without address"""

    with sessions.begin() as session:
        purge_old_fingerprints(session, moment)
        row = session.get(Analysis, analysis_id)
        if row is None:
            return Sent.NOT_FOUND
        if row.state not in FINISHED:
            return Sent.NOT_FINISHED
        if not accept_solution(session, settings, altcha, moment):
            return Sent.ALTCHA_INVALID
        visitor = make_visitor(user, ip_fingerprint(session, ip, moment), settings)
        day = utc_day(moment)
        if visitor.kind is not VisitorKind.ADMIN:
            refusal = take_report_slots(session, settings, visitor, analysis_id, kind, day)
            if refusal is not None:
                counted = REPORT_LIMIT
                if refusal is Sent.BOX_FULL:
                    counted = REPORT_GLOBAL
                    note_box_full(session, settings, moment)
                count_quota_refusal(session, day, counted)
                return refusal
        reporter_kind = ReporterKind.ANONYMOUS.value
        reporter_id = None
        if user is not None:
            reporter_kind = ReporterKind.ACCOUNT.value
            reporter_id = user.id
        session.add(
            Report(
                id=uuid.uuid4(),
                analysis_id=analysis_id,
                kind=kind,
                status=ReportStatus.NEW.value,
                comment=clean_comment(comment),
                engine_version=row.engine_version,
                rules_version=row.rules_version,
                color=color_of(row),
                reporter_kind=reporter_kind,
                reporter_user_id=reporter_id,
                created_at=moment,
            )
        )
    return Sent.SENT


def erase_old_comments(session: Session, now: datetime) -> int:
    """Erase the comment of every report handled or rejected more than 90 days ago; the row itself stays"""

    result = session.execute(
        update(Report)
        .where(Report.comment_erased_at.is_(None), Report.closed_at.is_not(None), Report.closed_at < now - COMMENT_KEPT)
        .values(comment=None, comment_erased_at=now)
    )
    return int(result.rowcount or 0)


def forget_reporter(session: Session, user_id: str) -> None:
    """Before an account is deleted: its reports stay without its id nor its comments, and its counts and marks go"""

    subject = user_subject(user_id)
    session.execute(
        update(Report)
        .where(Report.reporter_user_id == user_id)
        .values(reporter_user_id=None, reporter_kind=ReporterKind.DELETED.value, comment=None)
    )
    session.execute(delete(ReportCount).where(ReportCount.subject == subject))
    session.execute(delete(ReportMark).where(ReportMark.subject == subject))


def iso(moment: datetime | None) -> str | None:
    """Return a stored time in ISO 8601 with its time zone, or None"""

    utc = as_utc(moment)
    if utc is None:
        return None
    return utc.isoformat()


def report_view(row: Report) -> dict[str, Any]:
    """Return one report for the admin: never an address fingerprint, the account id only to be able to ban an abuse"""

    analysis_id = None
    if row.analysis_id is not None:
        analysis_id = str(row.analysis_id)
    return {
        "id": str(row.id),
        "analysis_id": analysis_id,
        "kind": row.kind,
        "unverified": row.kind == ReportKind.AUTHOR_ERROR.value,
        "status": row.status,
        "comment": row.comment,
        "engine_version": row.engine_version,
        "rules_version": row.rules_version,
        "color": row.color,
        "reporter_kind": row.reporter_kind,
        "account_id": row.reporter_user_id,
        "created_at": iso(row.created_at),
        "closed_at": iso(row.closed_at),
        "comment_erased_at": iso(row.comment_erased_at),
    }


def reports_list(session: Session, now: datetime, status: str | None, kind: str | None) -> dict[str, Any]:
    """Erase the overdue comments, then return the 50 last reports, filtered by status and kind, and how many are new"""

    erase_old_comments(session, now)
    query = select(Report)
    if status is not None:
        query = query.where(Report.status == status)
    if kind is not None:
        query = query.where(Report.kind == kind)
    rows = session.scalars(query.order_by(Report.created_at.desc(), Report.id).limit(REPORTS_SHOWN)).all()
    new_count = session.scalar(select(func.count()).select_from(Report).where(Report.status == ReportStatus.NEW.value))
    return {"reports": [report_view(row) for row in rows], "new_count": new_count or 0}


def change_status(session: Session, report_id: uuid.UUID, status: str, now: datetime) -> Change:
    """Mark a report handled or rejected and write it in the journal; the 90 days of its comment start the first time"""

    row = session.get(Report, report_id)
    if row is None:
        return Change.NOT_FOUND
    if row.status == status:
        return Change.UNCHANGED
    row.status = status
    if row.closed_at is None:
        row.closed_at = now
    record_action(session, STATUS_ACTIONS[status], AdminTarget.REPORT, str(report_id), now)
    return Change.DONE
