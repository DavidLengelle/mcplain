"""The routes of the admin dashboard, all under /api/admin, so behind admin_gate: admin with second factor, Origin for a change"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from mcplain_api.admin_accounts import AccountDesk
from mcplain_api.admin_dashboard import accounts_view, ai_view, analyses_view, parse_days, refusals_view, spend_view
from mcplain_api.db import utc_now
from mcplain_api.responses import error_response, no_store
from mcplain_api.settings import Settings

DASHBOARD_PREFIX = "/api/admin/dashboard"


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
