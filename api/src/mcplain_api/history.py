"""History of the analyses asked by a signed-in account: one row per request, cache included, no row for a used-up quota"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mcplain_api.db import Analysis, AnalysisState, UserHistory, as_utc

SAME_REQUEST_WINDOW = timedelta(minutes=1)
HISTORY_LIMIT = 100
GRAY = "gray"


def record_request(session: Session, user_id: str, row: Analysis, moment: datetime) -> bool:
    """Add a request to the history, unless the same input was asked by the same account less than a minute ago"""

    selection = Analysis.select.is_(None)
    if row.select is not None:
        selection = Analysis.select == row.select
    recent = session.scalar(
        select(UserHistory.id)
        .join(Analysis, Analysis.id == UserHistory.analysis_id)
        .where(
            UserHistory.user_id == user_id,
            UserHistory.created_at > moment - SAME_REQUEST_WINDOW,
            Analysis.input_raw == row.input_raw,
            Analysis.state != AnalysisState.QUOTA_EXHAUSTED.value,
            selection,
        )
        .limit(1)
    )
    if recent is not None:
        return False
    session.add(UserHistory(user_id=user_id, analysis_id=row.id, created_at=moment))
    return True


def forget_analysis(session: Session, analysis_id: uuid.UUID) -> None:
    """Remove an analysis from every history, for a request that ended on a used-up quota"""

    session.execute(delete(UserHistory).where(UserHistory.analysis_id == analysis_id))


def clear_history(session: Session, user_id: str) -> int:
    """Delete the whole history of an account and return how many rows went"""

    result = session.execute(delete(UserHistory).where(UserHistory.user_id == user_id))
    return int(getattr(result, "rowcount", 0) or 0)


def history_view(session: Session, user_id: str) -> list[dict[str, Any]]:
    """Return the last 100 requests of an account, the newest first, with what the report page needs"""

    rows = session.execute(
        select(UserHistory.created_at, Analysis)
        .join(Analysis, Analysis.id == UserHistory.analysis_id)
        .where(UserHistory.user_id == user_id, Analysis.state != AnalysisState.QUOTA_EXHAUSTED.value)
        .order_by(UserHistory.created_at.desc(), UserHistory.id)
        .limit(HISTORY_LIMIT)
    ).all()
    return [_entry(created_at, analysis) for created_at, analysis in rows]


def _entry(created_at: datetime, analysis: Analysis) -> dict[str, Any]:
    """Return one line of the history"""

    moment = as_utc(created_at)
    date = None
    if moment is not None:
        date = moment.isoformat()
    color, status = _verdict(analysis)
    return {
        "date": date,
        "id": str(analysis.id),
        "input": analysis.input_raw,
        "select": analysis.select,
        "state": analysis.state,
        "color": color,
        "status": status,
        "from_cache": bool(analysis.from_cache),
    }


def _verdict(analysis: Analysis) -> tuple[str | None, str | None]:
    """Return the color and the status of a finished analysis; a failed one is gray, a waiting one has neither"""

    if analysis.state == AnalysisState.FAILED.value:
        return GRAY, None
    if analysis.state != AnalysisState.DONE.value or not isinstance(analysis.result, dict):
        return None, None
    status = analysis.result.get("status")
    verdict = analysis.result.get("verdict")
    color = None
    if isinstance(verdict, dict) and isinstance(verdict.get("color"), str):
        color = str(verdict["color"])
    if not isinstance(status, str):
        status = None
    return color, status
