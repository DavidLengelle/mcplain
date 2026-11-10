"""What the API says about the texts of the AI: the fallback notice, the cache lookup and the public answer"""

import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

from mcplain.i18n import load_catalog
from mcplain.models import AnalysisResult
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mcplain_api.ai_form import build_form, content_hash, first_server, translation_items
from mcplain_api.ai_prompts import NOTICE_PROMPT_VERSION, TRANSLATION_PROMPT_VERSION
from mcplain_api.db import AI_STATE_ROW, AiKind, AiState, AiStatus, AiText, Analysis, AnalysisState, as_utc, utc_now

LAMP_OFF = "off"
RESUME_BY_REASON: dict[str, str] = {
    "daily_fuse": "tomorrow",
    "monthly_budget": "next_month",
    "usage_limit": "later",
    "daily_text_cap": "tomorrow",
}
RESUME_LATER = "later"
STATUS_TEMPLATE = "template"
STATUS_NONE = "none"
SOURCE_AI = "ai"
SOURCE_TEMPLATE = "template"
FINISHED: tuple[str, ...] = (AnalysisState.DONE.value, AnalysisState.FAILED.value)
LANGUAGES_BY_KIND: dict[str, tuple[str, ...]] = {
    AiKind.NOTICE.value: ("en", "fr"),
    AiKind.TRANSLATION.value: ("fr",),
}
PROMPT_VERSIONS: dict[str, str] = {
    AiKind.NOTICE.value: NOTICE_PROMPT_VERSION,
    AiKind.TRANSLATION.value: TRANSLATION_PROMPT_VERSION,
}
REQUEUED_STATUSES: frozenset[str] = frozenset({AiStatus.FAILED.value, AiStatus.PAUSED.value, AiStatus.DISABLED.value})


@cache
def api_catalog(language: str) -> dict[str, str]:
    """Read the texts that belong to the API"""

    text = files("mcplain_api").joinpath("locales", f"{language}.json").read_text(encoding="utf-8")
    return json.loads(text)


def full_catalog(language: str) -> dict[str, str]:
    """Return the texts of the engine and those of the API, the way the site reads them"""

    return {**load_catalog(language), **api_catalog(language)}


@dataclass(frozen=True)
class Asked:
    """Class that holds what one analysis can ask from the AI"""

    result: AnalysisResult | None
    hash: str | None
    tool_names: list[str]


def _report(row: Analysis) -> AnalysisResult | None:
    """Return the validated report of a finished analysis; a failed one has nothing to show to the AI"""

    if row.state != AnalysisState.DONE.value:
        return None
    try:
        return AnalysisResult.model_validate(row.result)
    except ValidationError:
        return None


def what_is_asked(row: Analysis, kind: str) -> Asked:
    """Return the cache hash of a text of one analysis; no hash means no call, for lack of a recognized tool"""

    result = _report(row)
    if result is None:
        return Asked(None, None, [])
    form = build_form(result)
    if form is None:
        return Asked(result, None, [])
    names = [tool["name"] for tool in form["tools"]]
    if kind == AiKind.NOTICE.value:
        return Asked(result, content_hash(form), names)
    items = translation_items(result)
    if not items:
        return Asked(result, None, names)
    return Asked(result, content_hash(items), names)


def fallback_notice(result: AnalysisResult | None) -> dict[str, Any]:
    """Return the notice written by hand, as text codes and parameters; the lamps give what the server can do"""

    server = None
    if result is not None:
        server = first_server(result)
    if server is None or not server.tools:
        return {"variant": "no_tools", "messages": [{"code": "ai.notice.fallback.no_tools", "params": {}}], "actions": []}
    actions = [f"lamp.{lamp.id}.phrase" for lamp in server.lamps if lamp.state != LAMP_OFF]
    second = "ai.notice.fallback.nothing"
    if actions:
        second = "ai.notice.fallback.can"
    return {
        "variant": "tools",
        "messages": [
            {"code": "ai.notice.fallback.count", "params": {"count": str(len(server.tools))}},
            {"code": second, "params": {}},
            {"code": "ai.notice.fallback.unavailable", "params": {}},
        ],
        "actions": actions,
    }


def public_content(row: AiText, asked: Asked) -> dict[str, Any] | None:
    """Return the checked text for the site; titles point at the tools of this report by their position"""

    if row.content is None:
        return None
    if row.kind == AiKind.TRANSLATION.value:
        return row.content
    positions = {name: index for index, name in enumerate(asked.tool_names)}
    titles = [
        {"tool_index": positions[entry["name"]], "title": entry["title"], "sentence": entry["sentence"]}
        for entry in row.content["tool_titles"]
        if entry["name"] in positions
    ]
    return {
        "summary": row.content["summary"],
        "use_cases": row.content["use_cases"],
        "tool_titles": titles,
        "alert": row.content["alert"],
    }


def view(
    analysis: Analysis,
    kind: str,
    lang: str,
    asked: Asked,
    status: str,
    row: AiText | None = None,
    resume: str | None = None,
) -> dict[str, Any]:
    """Return the public answer: never a cost, never a request identifier"""

    fallback = None
    if kind == AiKind.NOTICE.value:
        fallback = fallback_notice(asked.result)
    source = SOURCE_TEMPLATE
    content = None
    model = None
    date = None
    reason = None
    if row is not None:
        reason = row.reject_reason
        if row.status == AiStatus.READY.value:
            content = public_content(row, asked)
            source = SOURCE_AI
            model = row.model
            date = as_utc(row.updated_at).isoformat()
            reason = None
    return {
        "id": str(analysis.id),
        "kind": kind,
        "lang": lang,
        "status": status,
        "source": source,
        "fallback": fallback,
        "content": content,
        "model": model,
        "date": date,
        "reject_reason": reason,
        "resume": resume,
    }


def _find(session: Session, kind: str, lang: str, text_hash: str, model: str) -> AiText | None:
    """Return the cache row of a text, if it exists"""

    return session.scalars(
        select(AiText)
        .where(AiText.kind == kind)
        .where(AiText.lang == lang)
        .where(AiText.hash == text_hash)
        .where(AiText.prompt_version == PROMPT_VERSIONS[kind])
        .where(AiText.model == model)
    ).first()


def _row_view(analysis: Analysis, kind: str, lang: str, asked: Asked, row: AiText) -> dict[str, Any]:
    """Return the public answer for a row of the cache"""

    resume = None
    if row.status == AiStatus.PAUSED.value:
        resume = RESUME_BY_REASON.get(row.reject_reason or "", RESUME_LATER)
    return view(analysis, kind, lang, asked, row.status, row, resume)


def read_text(session: Session, analysis: Analysis, kind: str, lang: str, model: str) -> dict[str, Any]:
    """Return the state and the result of a text, without asking for anything"""

    asked = what_is_asked(analysis, kind)
    if asked.hash is None:
        return view(analysis, kind, lang, asked, STATUS_TEMPLATE)
    row = _find(session, kind, lang, asked.hash, model)
    if row is None:
        return view(analysis, kind, lang, asked, STATUS_NONE)
    return _row_view(analysis, kind, lang, asked, row)


def _blocked_view(session: Session, analysis: Analysis, kind: str, lang: str, asked: Asked) -> dict[str, Any] | None:
    """Return the answer when the writer is cut off or paused for everyone, so that nothing is queued"""

    state = session.get(AiState, AI_STATE_ROW)
    if state is None:
        return None
    if state.disabled_reason is not None:
        return view(analysis, kind, lang, asked, AiStatus.DISABLED.value)
    paused_until = as_utc(state.paused_until)
    if paused_until is not None and paused_until > utc_now():
        return view(analysis, kind, lang, asked, AiStatus.PAUSED.value, resume=RESUME_LATER)
    return None


def ask_text(sessions: sessionmaker, analysis_id: Any, kind: str, lang: str, model: str) -> tuple[int, dict[str, Any]] | None:
    """Serve a text from the cache or queue it; the unique key means ten visitors make one row and one call"""

    with sessions.begin() as session:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None:
            return None
        if analysis.state not in FINISHED:
            return 409, {}
        asked = what_is_asked(analysis, kind)
        if asked.hash is None:
            return 200, view(analysis, kind, lang, asked, STATUS_TEMPLATE)
        row = _find(session, kind, lang, asked.hash, model)
        if row is not None and not _can_retry(row):
            status = 200
            if row.status == AiStatus.PENDING.value:
                status = 202
            return status, _row_view(analysis, kind, lang, asked, row)
        blocked = _blocked_view(session, analysis, kind, lang, asked)
        if blocked is not None:
            return 200, blocked
        if row is not None:
            row.status = AiStatus.PENDING.value
            row.retry_at = None
            row.reject_reason = None
            row.analysis_id = analysis.id
            row.updated_at = utc_now()
            return 202, _row_view(analysis, kind, lang, asked, row)
    return _insert(sessions, analysis_id, kind, lang, model)


def _can_retry(row: AiText) -> bool:
    """Tell whether a text that did not come back can be asked again now"""

    if row.status not in REQUEUED_STATUSES:
        return False
    retry_at = as_utc(row.retry_at)
    return retry_at is None or retry_at <= utc_now()


def _insert(sessions: sessionmaker, analysis_id: Any, kind: str, lang: str, model: str) -> tuple[int, dict[str, Any]]:
    """Add a text to the queue; when another visitor just added it, answer with their row"""

    with sessions() as session:
        analysis = session.get(Analysis, analysis_id)
        asked = what_is_asked(analysis, kind)
        row = AiText(
            kind=kind,
            lang=lang,
            hash=asked.hash,
            prompt_version=PROMPT_VERSIONS[kind],
            model=model,
            status=AiStatus.PENDING.value,
            analysis_id=analysis.id,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            row = _find(session, kind, lang, asked.hash, model)
        status = 202
        if row.status != AiStatus.PENDING.value:
            status = 200
        return status, _row_view(analysis, kind, lang, asked, row)
