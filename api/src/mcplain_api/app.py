"""HTTP API: receives analysis requests, gives back their state and result as language-free JSON"""

import socket
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, Protocol

from fastapi import FastAPI, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcplain.errors import InputError, McplainError
from mcplain.i18n import SUPPORTED_LANGUAGES
from mcplain.inputs import parse_input, parse_selection
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from mcplain_api.ai_view import LANGUAGES_BY_KIND, ask_text, full_catalog, read_text
from mcplain_api.altcha_gate import PAYLOAD_MAX_CHARS, new_challenge
from mcplain_api.analysis_gate import BURST_LIMIT, QueueFull, admit, enqueue, quota_view
from mcplain_api.auth_guard import GuardAction, check_action
from mcplain_api.client_ip import FORWARDED_FOR, visitor_ip
from mcplain_api.db import (
    INPUT_MAX_CHARS,
    SELECT_MAX_CHARS,
    USER_ID_MAX_CHARS,
    AiKind,
    Analysis,
    AnalysisState,
    as_utc,
    make_engine,
    make_sessions,
    utc_now,
)
from mcplain_api.history import clear_history, history_view
from mcplain_api.outcomes import stored_failure
from mcplain_api.quota import erase_account, minutes_to_wait
from mcplain_api.session_user import CurrentUser, SessionReader
from mcplain_api.settings import Settings

MAX_BODY_BYTES = 2048
JSON_MEDIA_TYPE = "application/json"
ALLOWED_METHODS: list[str] = ["GET", "POST"]
ALLOWED_HEADERS: list[str] = ["Content-Type"]
ALTCHA_HEADER = "x-altcha"
MESSAGES_CACHE = "public, max-age=300"
FINISHED_STATES: tuple[str, ...] = (AnalysisState.DONE.value, AnalysisState.FAILED.value)
NO_STORE = "no-store"
GUARD_BODY_MAX_BYTES = 8192
IP_HEADER_MAX_CHARS = 1024
IP_HEADERS_MAX = 8
PEER_CACHE_SECONDS = 60.0
REFUSAL_STATUS: dict[str, int] = {"altcha_invalid": 403, "signup_limit": 429}
INTERNAL_BODY_MAX_BYTES = 512


class AnalysisRequest(BaseModel):
    """Class that describes the body of POST /api/analyses"""

    model_config = ConfigDict(extra="forbid")

    input: StrictStr
    select: StrictStr | None = None


class TextRequest(BaseModel):
    """Class that describes the body of POST /api/analyses/{id}/notice and /translation"""

    model_config = ConfigDict(extra="forbid")

    lang: StrictStr


class GuardRequest(BaseModel):
    """Class that describes the body of POST /internal/auth-guard, sent by the counter (guichet) only"""

    model_config = ConfigDict(extra="forbid")

    action: Literal["sign_up", "sign_in", "request_password_reset"]
    altcha: StrictStr | None = Field(default=None, max_length=PAYLOAD_MAX_CHARS)
    ip_headers: dict[StrictStr, StrictStr] = Field(default_factory=dict, max_length=IP_HEADERS_MAX)


class EraseRequest(BaseModel):
    """Class that describes the body of POST /internal/account-erase, sent by the counter before it deletes an account"""

    model_config = ConfigDict(extra="forbid")

    user_id: StrictStr = Field(min_length=1, max_length=USER_ID_MAX_CHARS)


class UserReader(Protocol):
    """Class protocol for what tells who is signed in: the counter in production, a fake in the tests"""

    def current_user(self, cookie_header: str | None) -> CurrentUser | None:
        """Return the signed-in user of a Cookie header, or None"""


def resolve_peers(names: list[str]) -> set[str]:
    """Return every address of the host names allowed to call the guard, as the internal DNS of compose gives them"""

    addresses: set[str] = set()
    for name in names:
        try:
            for item in socket.getaddrinfo(name, None, proto=socket.IPPROTO_TCP):
                addresses.add(str(item[4][0]))
        except OSError:
            continue
    return addresses


class PeerCheck:
    """Class that tells whether a connection comes from the counter, with the addresses resolved again every minute"""

    def __init__(self, names: list[str], resolver: Callable[[list[str]], set[str]]) -> None:
        """Keep the allowed names and the resolver, without any address yet"""

        self.names = names
        self.resolver = resolver
        self.addresses: set[str] = set()
        self.until = 0.0

    def allows(self, peer: str | None) -> bool:
        """Tell whether the peer address is one of the counter"""

        if peer is None:
            return False
        now = time.monotonic()
        if now >= self.until or peer not in self.addresses:
            self.addresses = self.resolver(self.names)
            self.until = now + PEER_CACHE_SECONDS
        return peer in self.addresses


def error_response(status: int, code: str, params: dict[str, str] | None = None) -> JSONResponse:
    """Return an error as a code and its parameters, without any language"""

    return JSONResponse({"error": {"code": code, "params": params or {}}}, status_code=status)


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    peer_resolver: Callable[[list[str]], set[str]] = resolve_peers,
    user_reader: UserReader | None = None,
) -> FastAPI:
    """Build the API application, its database access and its CORS policy"""

    if settings is None:
        settings = Settings()
    if engine is None:
        engine = make_engine(settings.database_url)
    if user_reader is None:
        user_reader = SessionReader(settings)
    reader = user_reader
    sessions = make_sessions(engine)
    guard_peers = PeerCheck(settings.auth_guard_peer_list(), peer_resolver)
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

    async def signed_in(request: Request) -> CurrentUser | None:
        """Return the account of the request, read by the counter from its session cookie"""

        return await run_in_threadpool(reader.current_user, request.headers.get("cookie"))

    def address_of(request: Request) -> str | None:
        """Return the visitor address, read by the one function allowed to read it"""

        peer = None
        if request.client is not None:
            peer = request.client.host
        return visitor_ip(request.headers.getlist(FORWARDED_FOR), peer, settings.trusted_proxy_hops)

    async def from_counter(request: Request) -> bool:
        """Tell whether a request of an internal route comes from the counter"""

        peer = None
        if request.client is not None:
            peer = request.client.host
        return await run_in_threadpool(guard_peers.allows, peer)

    @app.post("/api/analyses")
    async def create_analysis(request: Request) -> JSONResponse:
        """Check the format, the burst limit, ALTCHA and the input, then take a token and queue the analysis"""

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
        moment = utc_now()
        user = await signed_in(request)
        altcha = request.headers.get(ALTCHA_HEADER)
        admission = await run_in_threadpool(admit, sessions, settings, user, address_of(request), altcha, moment)
        if admission.visitor is None:
            return _refusal(admission.code, admission.retry_after)
        try:
            selection = _validate(payload)
        except McplainError as error:
            return error_response(400, error.code, error.params)
        try:
            created = await run_in_threadpool(
                enqueue, sessions, settings, admission.visitor, payload.input, selection, moment
            )
        except QueueFull:
            return error_response(503, "api.queue_full")
        return JSONResponse(
            {"id": str(created.id), "state": AnalysisState.QUEUED.value, "cache_only": created.cache_only},
            status_code=202,
        )

    @app.get("/api/quota")
    async def get_quota(request: Request) -> JSONResponse:
        """Return what is left of the daily quota of the visitor, without counting anything nor asking ALTCHA"""

        user = await signed_in(request)
        view = await run_in_threadpool(quota_view, sessions, settings, user, address_of(request), utc_now())
        return JSONResponse(view, headers={"Cache-Control": NO_STORE})

    @app.get("/api/account/history")
    async def get_history(request: Request) -> JSONResponse:
        """Return the last 100 analyses asked by the signed-in account"""

        user = await signed_in(request)
        if user is None:
            return error_response(401, "api.sign_in_required")

        def read() -> list[dict[str, Any]]:
            """Read the history in its own session"""

            with sessions() as session:
                return history_view(session, user.id)

        entries = await run_in_threadpool(read)
        return JSONResponse({"entries": entries}, headers={"Cache-Control": NO_STORE})

    @app.delete("/api/account/history")
    async def delete_history(request: Request) -> JSONResponse:
        """Delete the whole history of the signed-in account"""

        user = await signed_in(request)
        if user is None:
            return error_response(401, "api.sign_in_required")

        def clear() -> int:
            """Delete the history in its own transaction"""

            with sessions.begin() as session:
                return clear_history(session, user.id)

        deleted = await run_in_threadpool(clear)
        return JSONResponse({"deleted": deleted}, headers={"Cache-Control": NO_STORE})

    @app.post("/internal/account-erase")
    async def account_erase(request: Request) -> JSONResponse:
        """Erase the history and the quota rows of an account the counter is about to delete; the counter only"""

        if not await from_counter(request):
            return error_response(404, "api.not_found")
        body = await _read_body(request, INTERNAL_BODY_MAX_BYTES)
        if body is None:
            return error_response(413, "api.body_too_large", {"limit": str(INTERNAL_BODY_MAX_BYTES)})
        try:
            payload = EraseRequest.model_validate_json(body)
        except ValidationError:
            return error_response(400, "api.invalid_request")

        def erase() -> None:
            """Erase in one transaction"""

            with sessions.begin() as session:
                erase_account(session, payload.user_id)

        await run_in_threadpool(erase)
        return JSONResponse({"ok": True}, headers={"Cache-Control": NO_STORE})

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
        return JSONResponse(full_catalog(language), headers={"Cache-Control": MESSAGES_CACHE})

    async def ask_ai_text(request: Request, analysis_id: str, kind: str) -> JSONResponse:
        """Serve a text of the AI from the cache or queue it; these routes never count in a quota"""

        media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if media_type != JSON_MEDIA_TYPE:
            return error_response(415, "api.unsupported_media_type")
        body = await _read_body(request, MAX_BODY_BYTES)
        if body is None:
            return error_response(413, "api.body_too_large", {"limit": str(MAX_BODY_BYTES)})
        try:
            payload = TextRequest.model_validate_json(body)
        except ValidationError:
            return error_response(400, "api.invalid_request")
        if payload.lang not in LANGUAGES_BY_KIND[kind]:
            return error_response(400, "api.invalid_request")
        identifier = _analysis_uuid(analysis_id)
        if identifier is None:
            return error_response(404, "api.analysis_not_found")
        answer = await run_in_threadpool(ask_text, sessions, identifier, kind, payload.lang, settings.ai_model)
        if answer is None:
            return error_response(404, "api.analysis_not_found")
        status, content = answer
        if status == 409:
            return error_response(409, "api.analysis_not_finished")
        return JSONResponse(content, status_code=status)

    def read_ai_text(analysis_id: str, kind: str, lang: str) -> JSONResponse:
        """Return the state and the result of a text of the AI, without asking for anything"""

        if lang not in LANGUAGES_BY_KIND[kind]:
            return error_response(400, "api.invalid_request")
        identifier = _analysis_uuid(analysis_id)
        if identifier is None:
            return error_response(404, "api.analysis_not_found")
        with sessions() as session:
            row = session.get(Analysis, identifier)
            if row is None:
                return error_response(404, "api.analysis_not_found")
            if row.state not in FINISHED_STATES:
                return error_response(409, "api.analysis_not_finished")
            return JSONResponse(read_text(session, row, kind, lang, settings.ai_model))

    @app.post("/api/analyses/{analysis_id}/notice")
    async def ask_notice(request: Request, analysis_id: str) -> JSONResponse:
        """Ask for the notice of an analysis"""

        return await ask_ai_text(request, analysis_id, AiKind.NOTICE.value)

    @app.get("/api/analyses/{analysis_id}/notice")
    def get_notice(analysis_id: str, lang: str = Query()) -> JSONResponse:
        """Return the notice of an analysis"""

        return read_ai_text(analysis_id, AiKind.NOTICE.value, lang)

    @app.post("/api/analyses/{analysis_id}/translation")
    async def ask_translation(request: Request, analysis_id: str) -> JSONResponse:
        """Ask for the translation of the author descriptions of an analysis"""

        return await ask_ai_text(request, analysis_id, AiKind.TRANSLATION.value)

    @app.get("/api/analyses/{analysis_id}/translation")
    def get_translation(analysis_id: str, lang: str = Query()) -> JSONResponse:
        """Return the translation of the author descriptions of an analysis"""

        return read_ai_text(analysis_id, AiKind.TRANSLATION.value, lang)

    @app.get("/api/altcha/challenge")
    def altcha_challenge() -> JSONResponse:
        """Return a new ALTCHA challenge, signed, valid five minutes, never cached"""

        challenge = new_challenge(settings, utc_now())
        if challenge is None:
            return error_response(503, "api.altcha_unavailable")
        return JSONResponse(challenge, headers={"Cache-Control": NO_STORE})

    @app.post("/internal/auth-guard")
    async def auth_guard(request: Request) -> JSONResponse:
        """Check an action of the counter: only the counter may call it, and the website relay never forwards /internal"""

        if not await from_counter(request):
            return error_response(404, "api.not_found")
        body = await _read_body(request, GUARD_BODY_MAX_BYTES)
        if body is None:
            return error_response(413, "api.body_too_large", {"limit": str(GUARD_BODY_MAX_BYTES)})
        try:
            payload = GuardRequest.model_validate_json(body)
        except ValidationError:
            return error_response(400, "api.invalid_request")
        headers = {name: value[:IP_HEADER_MAX_CHARS] for name, value in payload.ip_headers.items()}
        answer = await run_in_threadpool(
            check_action, sessions, settings, GuardAction(payload.action), payload.altcha, headers, utc_now()
        )
        if answer.ok:
            return JSONResponse({"ok": True}, headers={"Cache-Control": NO_STORE})
        return JSONResponse(
            {"ok": False, "code": answer.code},
            status_code=REFUSAL_STATUS.get(answer.code or "", 403),
            headers={"Cache-Control": NO_STORE},
        )

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


def _analysis_uuid(analysis_id: str) -> uuid.UUID | None:
    """Return the identifier of an analysis, or None for a text that is not one"""

    try:
        return uuid.UUID(analysis_id)
    except ValueError:
        return None


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


def _refusal(code: str | None, retry_after: int | None) -> JSONResponse:
    """Answer a request refused by the burst limit (429, with Retry-After) or by ALTCHA (403)"""

    if code == BURST_LIMIT and retry_after is not None:
        response = error_response(
            429, BURST_LIMIT, {"retry_after": str(retry_after), "minutes": str(minutes_to_wait(retry_after))}
        )
        response.headers["Retry-After"] = str(retry_after)
        return response
    return error_response(403, code or "altcha_invalid")


def analysis_view(row: Analysis) -> dict[str, Any]:
    """Return the public view of an analysis, with what was asked; a failed one always carries a gray result"""

    result = row.result
    if row.state == AnalysisState.FAILED.value:
        result = stored_failure(row.error_code, row.result)
    if row.state == AnalysisState.QUOTA_EXHAUSTED.value:
        result = None
    analyzed_at = row.analyzed_at
    if analyzed_at is None and row.state in FINISHED_STATES:
        analyzed_at = row.finished_at
    return {
        "id": str(row.id),
        "input": row.input_raw,
        "select": row.select,
        "state": row.state,
        "created_at": _iso(row.created_at),
        "finished_at": _iso(row.finished_at),
        "analyzed_at": _iso(analyzed_at),
        "from_cache": bool(row.from_cache),
        "cache_only": bool(row.cache_only),
        "result": result,
        "error_code": row.error_code,
    }


def _iso(value: datetime | None) -> str | None:
    """Return a stored time in ISO 8601 with its time zone, or None"""

    moment = as_utc(value)
    if moment is None:
        return None
    return moment.isoformat()
