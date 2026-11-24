"""The journal of the admin: what was done, when, and to which analysis, text, alert, entry or account"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mcplain_api.db import AdminAction, AdminTarget, as_utc

JOURNAL_LIMIT = 50


class Action(StrEnum):
    """Class that lists the actions kept in the journal"""

    BAN = "ban"
    UNBAN = "unban"
    TEXT_RETRY = "text_retry"
    ANALYSIS_RERUN = "analysis_rerun"
    ALERT_READ = "alert_read"
    CREDIT_ADD = "credit_add"
    CREDIT_DELETE = "credit_delete"
    REPORT_HANDLED = "report_handled"
    REPORT_REJECTED = "report_rejected"


def record_action(session: Session, action: Action, target: AdminTarget, target_id: str, now: datetime) -> None:
    """Add one line to the journal"""

    session.add(AdminAction(id=uuid.uuid4(), action=action.value, target_kind=target.value, target_id=target_id, created_at=now))


def journal_view(session: Session) -> list[dict[str, Any]]:
    """Return the 50 last lines of the journal, the newest first"""

    rows = session.scalars(
        select(AdminAction).order_by(AdminAction.created_at.desc(), AdminAction.id).limit(JOURNAL_LIMIT)
    ).all()
    lines = []
    for row in rows:
        moment = as_utc(row.created_at)
        created = None
        if moment is not None:
            created = moment.isoformat()
        lines.append({"id": str(row.id), "action": row.action, "target_kind": row.target_kind, "target_id": row.target_id, "created_at": created})
    return lines
