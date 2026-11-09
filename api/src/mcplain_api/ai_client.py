"""Client of the Anthropic Messages API, with httpx: one fixed address, no redirect, no proxy"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from mcplain_api.ai_prompts import (
    NOTICE_SCHEMA,
    NOTICE_SYSTEM,
    TRANSLATION_SCHEMA,
    TRANSLATION_SYSTEM,
    notice_message,
    translation_message,
)
from mcplain_api.settings import Settings

LOGGER = logging.getLogger("mcplain.redacteur")
API_URL = "https://api.anthropic.com/v1/messages"
RETRY_DELAY_SECONDS = 20
USAGE_LIMIT_TEXT = "usage limits"
INVALID_REQUEST = "invalid_request_error"
BILLING_STATUS = 402
AUTH_STATUSES: frozenset[int] = frozenset({401, 403})
RETRY_STATUSES: frozenset[int] = frozenset({429, 529})
REQUEST_ID_HEADER = "request-id"
REQUEST_ID_MAX_CHARS = 128


class CallKind(StrEnum):
    """Class that lists what can come out of a call"""

    ANSWERED = "answered"
    LIMIT = "limit"
    AUTH = "auth"
    BAD_REQUEST = "bad_request"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Reply:
    """Class that holds what the writer keeps from a call; never the text of an error"""

    kind: CallKind
    text: str = ""
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    request_id: str | None = None
    status: int | None = None


def build_body(
    settings: Settings, system: str, message: str, max_tokens: int, schema: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return the body of a request: no sampling setting and no tool, ever; a schema is only for the diagnosis script"""

    output_config: dict[str, Any] = {"effort": settings.ai_effort}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    return {
        "model": settings.ai_model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": message}],
        "output_config": output_config,
        "thinking": {"type": settings.ai_thinking},
    }


def notice_body(settings: Settings, form: dict[str, Any], lang: str, with_format: bool = False) -> dict[str, Any]:
    """Return the request of a notice, the one the writer sends; with_format only serves the diagnosis script"""

    schema = None
    if with_format:
        schema = NOTICE_SCHEMA
    return build_body(settings, NOTICE_SYSTEM, notice_message(form, lang), settings.ai_max_tokens, schema)


def translation_body(settings: Settings, items: list[dict[str, str]], with_format: bool = False) -> dict[str, Any]:
    """Return the request of a translation, the one the writer sends"""

    schema = None
    if with_format:
        schema = TRANSLATION_SCHEMA
    return build_body(settings, TRANSLATION_SYSTEM, translation_message(items), settings.ai_translation_max_tokens, schema)


def _whole_number(value: object) -> int:
    """Return a token count, or 0 when the answer holds something else"""

    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _json_object(response: httpx.Response) -> dict[str, Any]:
    """Return the body of a response when it is a JSON object, otherwise an empty one"""

    try:
        document = response.json()
    except ValueError:
        return {}
    if isinstance(document, dict):
        return document
    return {}


def _request_id(response: httpx.Response) -> str | None:
    """Return the request identifier given by the API, cut to the size of its column"""

    value = response.headers.get(REQUEST_ID_HEADER)
    if value is None:
        return None
    return value[:REQUEST_ID_MAX_CHARS]


def _answered(response: httpx.Response) -> Reply:
    """Read an answer: the text blocks, why it stopped and how many tokens it used"""

    document = _json_object(response)
    blocks = document.get("content")
    text = ""
    if isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                text += block["text"]
    usage = document.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    stop_reason = document.get("stop_reason")
    if not isinstance(stop_reason, str):
        stop_reason = None
    return Reply(
        kind=CallKind.ANSWERED,
        text=text,
        stop_reason=stop_reason,
        input_tokens=_whole_number(usage.get("input_tokens")),
        output_tokens=_whole_number(usage.get("output_tokens")),
        request_id=_request_id(response),
        status=response.status_code,
    )


def _is_usage_limit(response: httpx.Response) -> bool:
    """Tell whether a 400 says that the monthly limit of the workspace is reached"""

    error = _json_object(response).get("error")
    if not isinstance(error, dict) or error.get("type") != INVALID_REQUEST:
        return False
    message = error.get("message")
    return isinstance(message, str) and USAGE_LIMIT_TEXT in message.lower()


def _classify(response: httpx.Response) -> Reply:
    """Turn a response into what the writer must do with it"""

    status = response.status_code
    request_id = _request_id(response)
    if status == 200:
        return _answered(response)
    if status == BILLING_STATUS or (status == 400 and _is_usage_limit(response)):
        return Reply(kind=CallKind.LIMIT, request_id=request_id, status=status)
    if status in AUTH_STATUSES:
        return Reply(kind=CallKind.AUTH, request_id=request_id, status=status)
    if status in RETRY_STATUSES or status >= 500:
        return Reply(kind=CallKind.UNAVAILABLE, request_id=request_id, status=status)
    return Reply(kind=CallKind.BAD_REQUEST, request_id=request_id, status=status)


def _send(settings: Settings, api_key: str, body: dict[str, Any], transport: httpx.BaseTransport | None) -> Reply:
    """Send one request; an unreachable API or a timeout counts as unavailable, and its text is dropped"""

    headers = {
        "x-api-key": api_key,
        "anthropic-version": settings.ai_api_version,
        "content-type": "application/json",
    }
    try:
        with httpx.Client(
            follow_redirects=False, trust_env=False, transport=transport, timeout=settings.ai_timeout_s
        ) as client:
            return _classify(client.post(API_URL, headers=headers, json=body))
    except httpx.HTTPError as error:
        LOGGER.warning("the AI API did not answer: %s", type(error).__name__)
        return Reply(kind=CallKind.UNAVAILABLE)


def call_api(
    settings: Settings,
    body: dict[str, Any],
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Reply:
    """Call the API; when it is overloaded or down, try once more 20 seconds later"""

    if settings.anthropic_api_key is None:
        raise ValueError("the AI API needs a key")
    api_key = settings.anthropic_api_key.get_secret_value()
    reply = _send(settings, api_key, body, transport)
    if reply.kind is CallKind.UNAVAILABLE:
        sleep(RETRY_DELAY_SECONDS)
        reply = _send(settings, api_key, body, transport)
    return reply


def call_cost(settings: Settings, input_tokens: int, output_tokens: int) -> float:
    """Return what a number of tokens costs, in US dollars, at the prices of the settings"""

    return (input_tokens * settings.ai_price_input_per_mtok + output_tokens * settings.ai_price_output_per_mtok) / 1_000_000
