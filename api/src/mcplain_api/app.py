"""HTTP API: receives analysis requests, gives back their state and result as language-free JSON"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcplain.errors import InputError, McplainError
from mcplain.i18n import SUPPORTED_LANGUAGES, load_catalog
from mcplain.inputs import parse_input, parse_selection
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from mcplain_api.db import (
    INPUT_MAX_CHARS,
    SELECT_MAX_CHARS,
    Analysis,
    AnalysisState,
    as_utc,
    make_engine,
    make_sessions,
)
from mcplain_api.outcomes import stored_failure
from mcplain_api.settings import Settings

MAX_BODY_BYTES = 2048
JSON_MEDIA_TYPE = "application/json"
ALLOWED_METHODS: list[str] = ["GET", "POST"]
ALLOWED_HEADERS: list[str] = ["Content-Type"]
MESSAGES_CACHE = "public, max-age=300"


class AnalysisRequest(BaseModel):
    """Class that describes the body of POST /api/analyses"""

    model_config = ConfigDict(extra="forbid")

    input: StrictStr
    select: StrictStr | None = None


class QueueFull(Exception):
    """Class for a request refused because too many analyses are waiting"""


def error_response(status: int, code: str, params: dict[str, str] | None = None) -> JSONResponse:
    """Return an error as a code and its parameters, without any language"""

    return JSONResponse({"error": {"code": code, "params": params or {}}}, status_code=status)


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    """Build the API application, its database access and its CORS policy"""

    if settings is None:
        settings = Settings()
    if engine is None:
        engine = make_engine(settings.database_url)
    sessions = make_sessions(engine)
    app = FastAPI(title="MCPlain API", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        allow_credentials=False,
    )

    @app.middleware("http")
    async def no_sniffing(request: Request, call_next: Any) -> Response:
        """Forbid browsers to guess another content type than JSON"""

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        """Answer unknown routes and methods with the same error format"""

        if error.status_code == 405:
            return error_response(405, "api.method_not_allowed")
        return error_response(error.status_code, "api.not_found")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        """Answer malformed requests with the same error format"""

        return error_response(400, "api.invalid_request")

    @app.post("/api/analyses")
    async def create_analysis(request: Request) -> JSONResponse:
        """Validate the pasted text without network and queue the analysis"""

        media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if media_type != JSON_MEDIA_TYPE:
            return error_response(415, "api.unsupported_media_type")
        body = await _read_body(request, MAX_BODY_BYTES)
        if body is None:
            return error_response(413, "api.body_too_large", {"limit": str(MAX_BODY_BYTES)})
        try:
            payload = AnalysisRequest.model_validate_json(body)
        except ValidationError:
            return error_response(400, "api.invalid_request")
        try:
            selection = _validate(payload)
        except McplainError as error:
            return error_response(400, error.code, error.params)
        try:
            identifier = await run_in_threadpool(_enqueue, sessions, settings, payload.input, selection)
        except QueueFull:
            return error_response(503, "api.queue_full")
        return JSONResponse({"id": str(identifier), "state": AnalysisState.QUEUED.value}, status_code=202)

    @app.get("/api/analyses/{analysis_id}")
    def get_analysis(analysis_id: str) -> JSONResponse:
        """Return the state of an analysis and, once finished, its result as stored"""

        try:
            identifier = uuid.UUID(analysis_id)
        except ValueError:
            return error_response(404, "api.analysis_not_found")
        with sessions() as session:
            row = session.get(Analysis, identifier)
        if row is None:
            return error_response(404, "api.analysis_not_found")
        return JSONResponse(analysis_view(row))

    @app.get("/api/messages/{language}")
    def get_messages(language: str) -> JSONResponse:
        """Return every engine text in one language, the same ones the command line uses"""

        if language not in SUPPORTED_LANGUAGES:
            return error_response(404, "api.unknown_language")
        return JSONResponse(load_catalog(language), headers={"Cache-Control": MESSAGES_CACHE})

    @app.get("/api/health")
    def health() -> JSONResponse:
        """Tell whether the database answers"""

        try:
            with sessions() as session:
                session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return error_response(503, "api.database_unavailable")
        return JSONResponse({"status": "ok"})

    return app


async def _read_body(request: Request, limit: int) -> bytes | None:
    """Read the request body, or return None as soon as it is longer than the limit"""

    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > limit):
        return None
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            return None
    return bytes(data)


def _validate(payload: AnalysisRequest) -> str | None:
    """Check the input and the selection with the engine rules, without any network access"""

    if len(payload.input) > INPUT_MAX_CHARS:
        raise InputError("input.too_long", limit=INPUT_MAX_CHARS)
    parse_input(payload.input)
    if payload.select is None:
        return None
    if len(payload.select) > SELECT_MAX_CHARS:
        raise InputError("input.invalid_selection", path=payload.select[:SELECT_MAX_CHARS])
    return parse_selection(payload.select)


def _enqueue(sessions: sessionmaker, settings: Settings, text_input: str, selection: str | None) -> uuid.UUID:
    """Add a queued analysis unless the queue is full"""

    with sessions.begin() as session:
        waiting = session.scalar(
            select(func.count()).select_from(Analysis).where(Analysis.state == AnalysisState.QUEUED.value)
        )
        if (waiting or 0) >= settings.max_queued:
            raise QueueFull()
        row = Analysis(input_raw=text_input, select=selection, state=AnalysisState.QUEUED.value)
        session.add(row)
        session.flush()
        return row.id


def analysis_view(row: Analysis) -> dict[str, Any]:
    """Return the public view of an analysis; a failed one always carries a gray result"""

    result = row.result
    if row.state == AnalysisState.FAILED.value:
        result = stored_failure(row.error_code, row.result)
    return {
        "id": str(row.id),
        "state": row.state,
        "created_at": _iso(row.created_at),
        "finished_at": _iso(row.finished_at),
        "result": result,
        "error_code": row.error_code,
    }


def _iso(value: datetime | None) -> str | None:
    """Return a stored time in ISO 8601 with its time zone, or None"""

    moment = as_utc(value)
    if moment is None:
        return None
    return moment.isoformat()
