"""The credit ledger of the admin: statements read in the Anthropic console, top-ups, and the low balance mail armed again"""

import math
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mcplain_api.ai_budget import estimated_balance
from mcplain_api.db import BALANCE_ALERT_ROW, CREDIT_NOTE_MAX_CHARS, BalanceAlert, CreditEntry, CreditKind, as_utc

ENTRIES_SHOWN = 20
AMOUNT_MAX_USD = 100_000.0


class DeleteOutcome(StrEnum):
    """Class that tells how the deletion of an entry ended"""

    DONE = "done"
    NOT_FOUND = "not_found"
    NOT_LAST = "not_last"


def valid_amount(kind: str, amount: float) -> bool:
    """Tell whether an amount fits its kind: a statement may be zero, a top-up adds something, both finite and bounded"""

    if not math.isfinite(amount) or amount < 0 or amount > AMOUNT_MAX_USD:
        return False
    if kind == CreditKind.TOP_UP.value:
        return amount > 0
    return True


def clean_note(note: str | None) -> str | None:
    """Return the note without the spaces around it, None when empty; its length is checked by the caller"""

    if note is None or not note.strip():
        return None
    return note.strip()


def note_fits(note: str | None) -> bool:
    """Tell whether a note holds at most 100 characters"""

    return note is None or len(note) <= CREDIT_NOTE_MAX_CHARS


def alert_state(session: Session) -> BalanceAlert:
    """Return the single row of the low balance mail, created on first use"""

    state = session.get(BalanceAlert, BALANCE_ALERT_ROW)
    if state is None:
        state = BalanceAlert(id=BALANCE_ALERT_ROW, sent_at=None)
        session.add(state)
        session.flush()
    return state


def rearm(session: Session, threshold: float) -> None:
    """Arm the low balance mail again when the estimated credit is no longer under the threshold"""

    balance = estimated_balance(session)
    if balance.amount_usd is None or balance.amount_usd < threshold:
        return
    alert_state(session).sent_at = None


def add_entry(session: Session, kind: str, amount: float, note: str | None, now: datetime, threshold: float) -> CreditEntry:
    """Add one entry dated now, then arm the mail again if the credit went back over the threshold"""

    alert_state(session)
    entry = CreditEntry(id=uuid.uuid4(), kind=kind, amount_usd=amount, note=note, created_at=now)
    session.add(entry)
    session.flush()
    rearm(session, threshold)
    return entry


def last_entry(session: Session) -> CreditEntry | None:
    """Return the newest entry of the ledger"""

    return session.scalars(select(CreditEntry).order_by(CreditEntry.created_at.desc(), CreditEntry.id.desc()).limit(1)).first()


def delete_last(session: Session, entry_id: uuid.UUID, threshold: float) -> DeleteOutcome:
    """Delete an entry only when it is the newest one, a typing mistake, then arm the mail again if the credit went up"""

    entry = session.get(CreditEntry, entry_id)
    if entry is None:
        return DeleteOutcome.NOT_FOUND
    last = last_entry(session)
    if last is None or last.id != entry.id:
        return DeleteOutcome.NOT_LAST
    session.delete(entry)
    session.flush()
    rearm(session, threshold)
    return DeleteOutcome.DONE


def iso(moment: datetime | None) -> str | None:
    """Return a stored time in ISO 8601 with its time zone, or None"""

    utc = as_utc(moment)
    if utc is None:
        return None
    return utc.isoformat()


def credit_view(session: Session, threshold: float) -> dict[str, Any]:
    """Return the estimated credit, the threshold of the mail, whether it was sent, and the last entries"""

    balance = estimated_balance(session)
    state = session.get(BalanceAlert, BALANCE_ALERT_ROW)
    sent_at = None
    if state is not None:
        sent_at = state.sent_at
    entries = session.scalars(
        select(CreditEntry).order_by(CreditEntry.created_at.desc(), CreditEntry.id.desc()).limit(ENTRIES_SHOWN)
    ).all()
    last_id = None
    if entries:
        last_id = str(entries[0].id)
    return {
        "balance_usd": balance.amount_usd,
        "statement_usd": balance.statement_usd,
        "statement_at": iso(balance.statement_at),
        "top_ups_usd": balance.top_ups_usd,
        "spent_usd": balance.spent_usd,
        "threshold_usd": threshold,
        "low": balance.amount_usd is not None and balance.amount_usd < threshold,
        "alert_sent_at": iso(sent_at),
        "last_entry_id": last_id,
        "entries": [
            {
                "id": str(entry.id),
                "kind": entry.kind,
                "amount_usd": entry.amount_usd,
                "note": entry.note,
                "created_at": iso(entry.created_at),
            }
            for entry in entries
        ],
    }
