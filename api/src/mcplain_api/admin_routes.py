"""The routes of the admin dashboard, all under /api/admin, so behind admin_gate: admin with second factor, Origin for a change"""

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, TypeVar

from fastapi import FastAPI, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictFloat, StrictStr, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from mcplain_api.admin_accounts import AccountDesk
from mcplain_api.admin_actions import Rerun, Retry, RetryAnswer, mark_read, rerun_analysis, retry_text
from mcplain_api.admin_dashboard import (
    accounts_view,
    ai_view,
    analyses_view,
    parse_days,
    refusals_view,
    reports_view,
    spend_view,
)
from mcplain_api.admin_journal import Action, journal_view, record_action
from mcplain_api.credit import DeleteOutcome, add_entry, clean_note, credit_view, delete_last, note_fits, valid_amount
from mcplain_api.db import AdminTarget, utc_now
from mcplain_api.reports import KINDS, STATUSES, Change, change_status, reports_list
from mcplain_api.responses import error_response, no_store, read_body
from mcplain_api.settings import Settings

DASHBOARD_PREFIX = "/api/admin/dashboard"
CREDIT_PATH = "/api/admin/credit"
REPORTS_PATH = "/api/admin/reports"
JSON_MEDIA_TYPE = "application/json"
BODY_MAX_BYTES = 1024
RETRY_ERRORS: dict[Retry, tuple[int, str]] = {
    Retry.NOT_FOUND: (404, "api.text_not_found"),
    Retry.NOT_RETRYABLE: (409, "api.text_not_retryable"),
    Retry.NO_REPORT: (409, "api.text_no_report"),
    Retry.DISABLED: (409, "api.ai_disabled"),
    Retry.PAUSED: (409, "api.ai_paused"),
    Retry.DAILY_TEXT_CAP: (409, "api.daily_text_cap"),
    Retry.DAILY_FUSE: (409, "api.daily_fuse"),
    Retry.MONTHLY_BUDGET: (409, "api.monthly_budget"),
}
RERUN_ERRORS: dict[Rerun, tuple[int, str]] = {
    Rerun.NOT_FOUND: (404, "api.analysis_not_found"),
    Rerun.NOT_FINISHED: (409, "api.analysis_not_finished"),
    Rerun.QUEUE_FULL: (503, "api.queue_full"),
}
Body = TypeVar("Body", bound=BaseModel)


class StatusRequest(BaseModel):
    """Class that describes the body of POST /api/admin/reports/{id}/status: handled or rejected"""

    model_config = ConfigDict(extra="forbid")

    status: Literal["handled", "rejected"]


class CreditRequest(BaseModel):
    """Class that describes the body of POST /api/admin/credit: a statement or a top-up in dollars, and an optional note"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["statement", "top_up"]
    amount_usd: StrictFloat
    note: StrictStr | None = None


async def json_body(request: Request, model: type[Body]) -> Body | JSONResponse:
    """Read a small JSON body into its model, or return the error to answer"""

    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type != JSON_MEDIA_TYPE:
        return no_store(error_response(415, "api.unsupported_media_type"))
    body = await read_body(request, BODY_MAX_BYTES)
    if body is None:
        return no_store(error_response(413, "api.body_too_large", {"limit": str(BODY_MAX_BYTES)}))
    try:
        return model.model_validate_json(body)
    except ValidationError:
        return no_store(error_response(400, "api.invalid_request"))


def uuid_of(text: str) -> uuid.UUID | None:
    """Return the identifier written in a path, or None"""

    try:
        return uuid.UUID(text)
    except ValueError:
        return None


def invalid_days() -> JSONResponse:
    """Answer a period that is neither 7 nor 30 days"""

    return no_store(error_response(400, "api.invalid_days"))


def add_admin_routes(app: FastAPI, sessions: sessionmaker, settings: Settings, desk: AccountDesk) -> None:
    """Add the routes of the dashboard to the application"""

    async def reading(days: str | None, read: Callable[[Session, datetime, int], dict[str, Any]]) -> JSONResponse:
        """Answer one group of dials over 7 or 30 days, read in one session"""

        length = parse_days(days)
        if length is None:
            return invalid_days()

        def run() -> dict[str, Any]:
            """Read the dials"""

            with sessions() as session:
                return read(session, utc_now(), length)

        return no_store(JSONResponse(await run_in_threadpool(run)))

    @app.get(DASHBOARD_PREFIX + "/spend")
    async def dashboard_spend(days: str | None = Query(default=None)) -> JSONResponse:
        """Return what the AI cost, with the fuse of the day and the budget of the month"""

        return await reading(days, lambda session, now, length: spend_view(session, settings, now, length))

    @app.get(DASHBOARD_PREFIX + "/ai")
    async def dashboard_ai(days: str | None = Query(default=None)) -> JSONResponse:
        """Return the refusals of the AI, the encoding rate, the alerts and the texts that can be asked again"""

        return await reading(days, ai_view)

    @app.get(DASHBOARD_PREFIX + "/analyses")
    async def dashboard_analyses(days: str | None = Query(default=None)) -> JSONResponse:
        """Return the analyses per day, the colors, the gray cases, the languages, the failures and the most analyzed MCP"""

        return await reading(days, analyses_view)

    @app.get(DASHBOARD_PREFIX + "/refusals")
    async def dashboard_refusals(days: str | None = Query(default=None)) -> JSONResponse:
        """Return the refused sign-ups and the requests with the quota used up, per day"""

        return await reading(days, refusals_view)

    @app.get(DASHBOARD_PREFIX + "/reports")
    async def dashboard_reports(days: str | None = Query(default=None)) -> JSONResponse:
        """Return the reports per day and per kind, as totals only"""

        return await reading(days, reports_view)

    @app.get(REPORTS_PATH)
    async def reports_read(status: str | None = Query(default=None), kind: str | None = Query(default=None)) -> JSONResponse:
        """Return the 50 last reports, filtered by status and kind, after erasing the comments kept more than 90 days"""

        if (status is not None and status not in STATUSES) or (kind is not None and kind not in KINDS):
            return no_store(error_response(400, "api.invalid_request"))

        def run() -> dict[str, Any]:
            """Erase and read in one transaction"""

            with sessions.begin() as session:
                return reports_list(session, utc_now(), status, kind)

        return no_store(JSONResponse(await run_in_threadpool(run)))

    @app.post(REPORTS_PATH + "/{report_id}/status")
    async def report_status(request: Request, report_id: str) -> JSONResponse:
        """Mark a report handled or rejected, written in the journal of the admin"""

        payload = await json_body(request, StatusRequest)
        if isinstance(payload, JSONResponse):
            return payload
        identifier = uuid_of(report_id)
        if identifier is None:
            return no_store(error_response(404, "api.report_not_found"))

        def run() -> Change:
            """Change the status and write the journal in one transaction"""

            with sessions.begin() as session:
                return change_status(session, identifier, payload.status, utc_now())

        outcome = await run_in_threadpool(run)
        if outcome is Change.NOT_FOUND:
            return no_store(error_response(404, "api.report_not_found"))
        return no_store(JSONResponse({"id": str(identifier), "status": payload.status}))

    @app.get(DASHBOARD_PREFIX + "/accounts")
    async def dashboard_accounts(days: str | None = Query(default=None)) -> JSONResponse:
        """Return the accounts created per day, asked from the counter"""

        length = parse_days(days)
        if length is None:
            return invalid_days()
        view = await run_in_threadpool(accounts_view, desk, utc_now(), length)
        if view is None:
            return no_store(error_response(503, "api.guichet_unavailable"))
        return no_store(JSONResponse(view))

    @app.get(CREDIT_PATH)
    async def credit_read() -> JSONResponse:
        """Return the estimated credit, the state of the low balance mail and the last entries"""

        def run() -> dict[str, Any]:
            """Read the ledger"""

            with sessions() as session:
                return credit_view(session, settings.balance_alert_usd)

        return no_store(JSONResponse(await run_in_threadpool(run)))

    @app.post(CREDIT_PATH)
    async def credit_add(request: Request) -> JSONResponse:
        """Add a statement or a top-up, dated now; the mail is armed again when the credit goes back over the threshold"""

        payload = await json_body(request, CreditRequest)
        if isinstance(payload, JSONResponse):
            return payload
        note = clean_note(payload.note)
        if not valid_amount(payload.kind, payload.amount_usd):
            return no_store(error_response(400, "api.invalid_amount"))
        if not note_fits(note):
            return no_store(error_response(400, "api.note_too_long"))

        def run() -> dict[str, Any]:
            """Write the entry and its line of the journal in one transaction"""

            now = utc_now()
            with sessions.begin() as session:
                entry = add_entry(session, payload.kind, payload.amount_usd, note, now, settings.balance_alert_usd)
                record_action(session, Action.CREDIT_ADD, AdminTarget.CREDIT, str(entry.id), now)
            with sessions() as session:
                return credit_view(session, settings.balance_alert_usd)

        return no_store(JSONResponse(await run_in_threadpool(run), status_code=201))

    @app.delete(CREDIT_PATH + "/{entry_id}")
    async def credit_delete(entry_id: str) -> JSONResponse:
        """Delete the newest entry only, a typing mistake; any older one stays"""

        identifier = uuid_of(entry_id)
        if identifier is None:
            return no_store(error_response(404, "api.credit_not_found"))

        def run() -> DeleteOutcome:
            """Delete the entry and write its line of the journal in one transaction"""

            now = utc_now()
            with sessions.begin() as session:
                outcome = delete_last(session, identifier, settings.balance_alert_usd)
                if outcome is DeleteOutcome.DONE:
                    record_action(session, Action.CREDIT_DELETE, AdminTarget.CREDIT, str(identifier), now)
                return outcome

        outcome = await run_in_threadpool(run)
        if outcome is DeleteOutcome.NOT_FOUND:
            return no_store(error_response(404, "api.credit_not_found"))
        if outcome is DeleteOutcome.NOT_LAST:
            return no_store(error_response(409, "api.credit_not_last"))

        def view() -> dict[str, Any]:
            """Read the ledger after the deletion"""

            with sessions() as session:
                return credit_view(session, settings.balance_alert_usd)

        return no_store(JSONResponse(await run_in_threadpool(view)))

    @app.post("/api/admin/texts/{text_id}/retry")
    async def text_retry(text_id: str) -> JSONResponse:
        """Ask a rejected or failed text of the AI again; the pause, the cap of 4 and the fuses always apply"""

        identifier = uuid_of(text_id)
        if identifier is None:
            return no_store(error_response(404, "api.text_not_found"))

        def run() -> RetryAnswer:
            """Check and queue the text in one transaction"""

            with sessions.begin() as session:
                return retry_text(session, sessions, settings, identifier, utc_now())

        answer = await run_in_threadpool(run)
        if answer.outcome is not Retry.QUEUED:
            status, code = RETRY_ERRORS[answer.outcome]
            params = {}
            if answer.detail is not None:
                params["detail"] = answer.detail
            return no_store(error_response(status, code, params))
        return no_store(JSONResponse({"id": str(identifier), "status": "pending"}, status_code=202))

    @app.post("/api/admin/analyses/{analysis_id}/rerun")
    async def analysis_rerun(analysis_id: str) -> JSONResponse:
        """Analyze the same request again without the cache, without quota nor token; a failure keeps the old cached result"""

        identifier = uuid_of(analysis_id)
        if identifier is None:
            return no_store(error_response(404, "api.analysis_not_found"))

        def run() -> tuple[Rerun, uuid.UUID | None]:
            """Queue the new analysis in one transaction"""

            with sessions.begin() as session:
                return rerun_analysis(session, settings, identifier, utc_now())

        outcome, created = await run_in_threadpool(run)
        if outcome is not Rerun.QUEUED or created is None:
            status, code = RERUN_ERRORS.get(outcome, RERUN_ERRORS[Rerun.NOT_FOUND])
            return no_store(error_response(status, code))
        return no_store(JSONResponse({"id": str(created), "state": "queued"}, status_code=202))

    @app.post("/api/admin/alerts/{alert_id}/read")
    async def alert_read(alert_id: str) -> JSONResponse:
        """Mark an alert of the AI as read"""

        identifier = uuid_of(alert_id)
        if identifier is None:
            return no_store(error_response(404, "api.alert_not_found"))

        def run() -> bool:
            """Mark it in one transaction"""

            with sessions.begin() as session:
                return mark_read(session, identifier, utc_now())

        if not await run_in_threadpool(run):
            return no_store(error_response(404, "api.alert_not_found"))
        return no_store(JSONResponse({"ok": True}))

    @app.get("/api/admin/journal")
    async def journal_read() -> JSONResponse:
        """Return the 50 last actions of the admin"""

        def run() -> list[dict[str, Any]]:
            """Read the journal"""

            with sessions() as session:
                return journal_view(session)

        return no_store(JSONResponse({"lines": await run_in_threadpool(run)}))

