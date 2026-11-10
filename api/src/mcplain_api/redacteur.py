"""Writer: takes the texts asked from the AI, one at a time; only this service holds the Anthropic key"""

import logging
import signal
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import FrameType
from typing import Any

import httpx
from mcplain.models import AnalysisResult
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from mcplain_api.ai_check import Checked, OutputRejected, RejectReason, check_notice, check_translation
from mcplain_api.ai_client import CallKind, Reply, call_api, call_cost, notice_body, translation_body
from mcplain_api.ai_form import build_form, canonical_json, content_hash, translation_items
from mcplain_api.ai_logging import install_secret_filter
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
    as_utc,
    make_engine,
    make_sessions,
    utc_now,
)
from mcplain_api.settings import Settings

LOGGER = logging.getLogger("mcplain.redacteur")
IDLE_SECONDS = 1.0
LIMIT_PAUSE = timedelta(hours=1)
FAILURE_WAIT = timedelta(minutes=10)
ALERT_SPACING = timedelta(hours=24)
ENCODING_WAIT = timedelta(hours=1)
CALLS_PER_TEXT_PER_DAY = 4
ATTEMPTS_ON_ENCODING = 2
BYTES_PER_TOKEN_ESTIMATE = 2
END_TURN = "end_turn"
NO_KEY = "no_key"
AUTH_REFUSED = "auth"
REASON_USAGE_LIMIT = "usage_limit"
REASON_DAILY_FUSE = "daily_fuse"
REASON_MONTHLY_BUDGET = "monthly_budget"
REASON_UNAVAILABLE = "unavailable"
REASON_BAD_REQUEST = "bad_request"
REASON_NO_REPORT = "no_report"
REASON_DAILY_TEXT_CAP = "daily_text_cap"
REASON_INTERNAL = "internal"
ALERT_USAGE_LIMIT = "usage_limit"
ALERT_AUTH = "auth_refused"
ALERT_BAD_REQUEST = "bad_request"


@dataclass(frozen=True)
class Prepared:
    """Class that holds one call ready to go and how to check its answer"""

    body: dict[str, Any]
    check: Callable[[str], Checked]


def get_state(session: Session) -> AiState:
    """Return the single state row, created on first use"""

    state = session.get(AiState, AI_STATE_ROW)
    if state is None:
        state = AiState(id=AI_STATE_ROW)
        session.add(state)
        session.flush()
    return state


def claim_waiting(session: Session) -> AiText | None:
    """Take the oldest waiting text, locked until the end of the transaction so that another writer skips it"""

    return session.scalars(
        select(AiText)
        .where(AiText.status == AiStatus.PENDING.value)
        .order_by(AiText.created_at, AiText.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()


def validated_report(session: Session, row: AiText) -> AnalysisResult | None:
    """Return the validated report of a finished analysis, or None; the code and the archive are never read"""

    if row.analysis_id is None:
        return None
    analysis = session.get(Analysis, row.analysis_id)
    if analysis is None or analysis.state != AnalysisState.DONE.value:
        return None
    try:
        return AnalysisResult.model_validate(analysis.result)
    except ValidationError:
        return None


def next_day(moment: datetime) -> datetime:
    """Return the start of the next UTC day"""

    return moment.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)


def next_month(moment: datetime) -> datetime:
    """Return the start of the next UTC month"""

    first = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (first + timedelta(days=32)).replace(day=1)


class Redacteur:
    """Class that empties the queue of texts, with one call at a time"""

    def __init__(
        self,
        settings: Settings,
        sessions: sessionmaker,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Keep the settings, the database sessions and what the tests replace"""

        self.settings = settings
        self.sessions = sessions
        self.transport = transport
        self.sleep = sleep
        self.clock = clock
        self.stopping = threading.Event()

    def start(self) -> None:
        """Record at startup whether the function is on: no key cuts it, and a restart ends a refused key"""

        with self.sessions.begin() as session:
            state = get_state(session)
            if self.settings.anthropic_api_key is None:
                state.disabled_reason = NO_KEY
            else:
                state.disabled_reason = None

    def run_once(self) -> bool:
        """Process one waiting text; the lock is held during the call, so a second writer skips it"""

        with self.sessions.begin() as session:
            state = get_state(session)
            now = self.clock()
            paused_until = as_utc(state.paused_until)
            if state.disabled_reason is not None or self.settings.anthropic_api_key is None:
                self._park_waiting(session, AiStatus.DISABLED, None, None, now)
                return False
            if paused_until is not None and paused_until > now:
                self._park_waiting(session, AiStatus.PAUSED, paused_until, REASON_USAGE_LIMIT, now)
                return False
            row = claim_waiting(session)
            if row is None:
                return False
            try:
                self._process(session, state, row)
            except SQLAlchemyError:
                raise
            except Exception as error:
                LOGGER.error("text %s: internal error %s", row.id, type(error).__name__)
                self._finish(row, AiStatus.FAILED, REASON_INTERNAL, now + FAILURE_WAIT)
            return True

    def run_forever(self) -> None:
        """Process the queue until asked to stop, waiting 1 s when it is empty"""

        while not self.stopping.is_set():
            try:
                worked = self.run_once()
            except SQLAlchemyError as error:
                LOGGER.error("cannot read the queue: %s", type(error).__name__)
                worked = False
            if not worked:
                self.stopping.wait(IDLE_SECONDS)

    def stop(self) -> None:
        """Ask the loop to stop after the current text"""

        self.stopping.set()

    def _park_waiting(
        self, session: Session, status: AiStatus, retry_at: datetime | None, reason: str | None, now: datetime
    ) -> None:
        """Give their state to every waiting text that no other writer is processing, without any call"""

        rows = session.scalars(
            select(AiText).where(AiText.status == AiStatus.PENDING.value).with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            row.status = status.value
            row.retry_at = retry_at
            row.reject_reason = reason
            row.updated_at = now

    def _prepare(self, row: AiText, result: AnalysisResult) -> Prepared | None:
        """Build the call of one text from the report; None if the report no longer gives what was asked"""

        if row.kind == AiKind.NOTICE.value:
            form = build_form(result)
            if form is None or content_hash(form) != row.hash:
                return None
            body = notice_body(self.settings, form, row.lang)
            return Prepared(body, lambda text: check_notice(text, form))
        items = translation_items(result)
        if not items or content_hash(items) != row.hash:
            return None
        body = translation_body(self.settings, items)
        return Prepared(body, lambda text: check_translation(text, items))

    def worst_cost(self, body: dict[str, Any]) -> float:
        """Return the most a call can cost: the input estimated from its size, and all of max_tokens as output"""

        size = len(canonical_json(body).encode("utf-8"))
        return call_cost(self.settings, size // BYTES_PER_TOKEN_ESTIMATE, body["max_tokens"])

    def _spent_since(self, session: Session, start: datetime) -> float:
        """Return what the calls recorded since a moment cost"""

        total = session.scalar(select(func.coalesce(func.sum(AiCall.cost_usd), 0.0)).where(AiCall.created_at >= start))
        return float(total or 0.0)

    def _budget_reason(self, session: Session, worst: float, now: datetime) -> tuple[str, datetime] | None:
        """Return why the budget forbids a call of this cost, and when it can come back"""

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if self._spent_since(session, month_start) + worst > self.settings.ai_monthly_budget_usd:
            return REASON_MONTHLY_BUDGET, next_month(now)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self._spent_since(session, day_start) + worst > self.settings.daily_fuse():
            return REASON_DAILY_FUSE, next_day(now)
        return None

    def _calls_today(self, session: Session, row: AiText, now: datetime) -> int:
        """Return how many calls this text made since the start of the UTC day"""

        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        count = session.scalar(
            select(func.count()).select_from(AiCall).where(AiCall.text_id == row.id).where(AiCall.created_at >= day_start)
        )
        return int(count or 0)

    def _process(self, session: Session, state: AiState, row: AiText) -> None:
        """Call the API, and once more at once when the text came back with broken encoding, in the transaction of the lock"""

        now = self.clock()
        result = validated_report(session, row)
        prepared = None
        if result is not None:
            prepared = self._prepare(row, result)
        if prepared is None:
            self._finish(row, AiStatus.FAILED, REASON_NO_REPORT, now + FAILURE_WAIT)
            return
        for attempt in range(1, ATTEMPTS_ON_ENCODING + 1):
            if not self._may_call(session, row, prepared):
                return
            reply = call_api(self.settings, prepared.body, self.transport, self.sleep)
            rejected = self._record_reply(session, state, row, reply, prepared)
            if rejected is not RejectReason.ENCODING:
                return
            LOGGER.warning("text %s: broken encoding, try %d of %d", row.id, attempt, ATTEMPTS_ON_ENCODING)
        self._finish(row, AiStatus.FAILED, RejectReason.ENCODING.value, self.clock() + ENCODING_WAIT)

    def _may_call(self, session: Session, row: AiText, prepared: Prepared) -> bool:
        """Check the cap of calls of this text today, then the fuses with the worst cost; pause the text otherwise"""

        now = self.clock()
        if self._calls_today(session, row, now) >= CALLS_PER_TEXT_PER_DAY:
            LOGGER.warning("text %s: not sent, %s", row.id, REASON_DAILY_TEXT_CAP)
            self._finish(row, AiStatus.PAUSED, REASON_DAILY_TEXT_CAP, next_day(now))
            return False
        refused = self._budget_reason(session, self.worst_cost(prepared.body), now)
        if refused is not None:
            reason, back_at = refused
            LOGGER.warning("text %s: not sent, %s", row.id, reason)
            self._finish(row, AiStatus.PAUSED, reason, back_at)
            return False
        return True

    def _record_reply(
        self, session: Session, state: AiState, row: AiText, reply: Reply, prepared: Prepared
    ) -> RejectReason | None:
        """Log the call, then give the text its state; return why its text was refused, if it was"""

        now = self.clock()
        cost = call_cost(self.settings, reply.input_tokens, reply.output_tokens)
        row.request_id = reply.request_id
        row.input_tokens += reply.input_tokens
        row.output_tokens += reply.output_tokens
        row.cost_usd += cost
        call = AiCall(
            text_id=row.id,
            kind=row.kind,
            lang=row.lang,
            outcome=reply.kind.value,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            cost_usd=cost,
            request_id=reply.request_id,
            created_at=now,
        )
        session.add(call)
        if reply.kind is CallKind.LIMIT:
            state.paused_until = now + LIMIT_PAUSE
            self._alert(session, ALERT_USAGE_LIMIT, row, reply, now)
            self._finish(row, AiStatus.PAUSED, REASON_USAGE_LIMIT, state.paused_until)
        elif reply.kind is CallKind.AUTH:
            state.disabled_reason = AUTH_REFUSED
            self._alert(session, ALERT_AUTH, row, reply, now)
            self._finish(row, AiStatus.DISABLED, AUTH_REFUSED, None)
        elif reply.kind is CallKind.BAD_REQUEST:
            self._alert(session, ALERT_BAD_REQUEST, row, reply, now)
            self._finish(row, AiStatus.FAILED, REASON_BAD_REQUEST, now + FAILURE_WAIT)
        elif reply.kind is CallKind.UNAVAILABLE:
            self._finish(row, AiStatus.FAILED, REASON_UNAVAILABLE, now + FAILURE_WAIT)
        else:
            rejected = self._record_answer(row, reply, prepared)
            call.reject_reason = None
            if rejected is not None:
                call.reject_reason = rejected.value
            return rejected
        return None

    def _record_answer(self, row: AiText, reply: Reply, prepared: Prepared) -> RejectReason | None:
        """Record the checked text; a rejected text only leaves its reason code, broken encoding is left to the caller"""

        try:
            checked = self._read_answer(reply, prepared)
        except OutputRejected as rejected:
            LOGGER.warning("text %s: rejected, %s", row.id, rejected.reason.value)
            if rejected.reason is not RejectReason.ENCODING:
                self._finish(row, AiStatus.REJECTED, rejected.reason.value, None)
            return rejected.reason
        row.content = checked.content
        reason = None
        if checked.dropped is not None:
            reason = checked.dropped.value
        self._finish(row, AiStatus.READY, reason, None)
        LOGGER.info("text %s: ready, %d tokens in, %d tokens out", row.id, reply.input_tokens, reply.output_tokens)
        return None

    def _read_answer(self, reply: Reply, prepared: Prepared) -> Checked:
        """Refuse an answer that did not end normally, then check its text"""

        if reply.stop_reason == RejectReason.REFUSAL.value:
            raise OutputRejected(RejectReason.REFUSAL)
        if reply.stop_reason == RejectReason.MAX_TOKENS.value:
            raise OutputRejected(RejectReason.MAX_TOKENS)
        if reply.stop_reason != END_TURN:
            raise OutputRejected(RejectReason.BAD_JSON)
        return prepared.check(reply.text)

    def _finish(self, row: AiText, status: AiStatus, reason: str | None, retry_at: datetime | None) -> None:
        """Give a text its state; only a checked text is ever ready"""

        row.status = status.value
        row.reject_reason = reason
        row.retry_at = retry_at
        row.updated_at = self.clock()

    def _alert(self, session: Session, code: str, row: AiText, reply: Reply, now: datetime) -> None:
        """Record an alert for the admin, at most one per code in 24 hours, with a log line; no text of a third party"""

        recent = session.scalar(
            select(func.count())
            .select_from(AiAdminAlert)
            .where(AiAdminAlert.code == code)
            .where(AiAdminAlert.created_at > now - ALERT_SPACING)
        )
        if recent:
            return
        details = {"kind": row.kind, "status": reply.status, "request_id": reply.request_id}
        session.add(AiAdminAlert(code=code, created_at=now, details=details))
        LOGGER.warning("admin alert: %s, status %s", code, reply.status)


def main() -> int:
    """Run the writer until SIGTERM or SIGINT; without a key, no call is ever tried"""

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    settings = Settings()
    secret = None
    if settings.anthropic_api_key is not None:
        secret = settings.anthropic_api_key.get_secret_value()
    install_secret_filter(secret)
    engine = make_engine(settings.database_url)
    redacteur = Redacteur(settings, make_sessions(engine))

    def stop(signal_number: int, frame: FrameType | None) -> None:
        """Stop taking new texts"""

        redacteur.stop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    redacteur.start()
    LOGGER.info("writer started, function on: %s", settings.anthropic_api_key is not None)
    redacteur.run_forever()
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
