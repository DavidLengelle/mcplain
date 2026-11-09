"""Control of what the AI wrote, before anything is stored or shown; a rejected text only leaves a reason code"""

import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from mcplain.adapters.common import INVISIBLE_PATTERN
from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr, ValidationError

from mcplain_api.ai_words import has_forbidden_word

MAX_SUMMARY = 600
MAX_USE_CASES = 3
MAX_USE_CASE = 160
MAX_TITLE = 40
MAX_SENTENCE = 160
MAX_ALERT = 240
TRANSLATION_FACTOR = 3
TRANSLATION_MARGIN = 50
LINK_MARKS: tuple[str, ...] = ("http://", "https://", "www.", "<", ">", "](")
EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
DOMAIN_PATTERN = re.compile(r"(?<![\w.@-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}(?![\w-])")
FILE_EXTENSIONS: frozenset[str] = frozenset(
    {
        "cjs", "css", "csv", "env", "html", "ini", "js", "json", "jsx", "lock", "log", "md", "mjs", "pdf", "png",
        "py", "sh", "sql", "toml", "ts", "tsx", "txt", "xml", "yaml", "yml",
    }
)
MOJIBAKE_PATTERN = re.compile("[\u00c3\u0102].|\u00c2\u00a0|\u00e2\u20ac|\ufffd", re.DOTALL)
URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s\"'<>`]+", re.IGNORECASE)
URL_TRAILING = ".,;:!?)]}»"


class RejectReason(StrEnum):
    """Class that lists the only things kept about a rejected text"""

    FORBIDDEN_WORD = "forbidden_word"
    LINK = "link"
    LENGTH = "length"
    UNKNOWN_TOOL = "unknown_tool"
    INVISIBLE = "invisible"
    ENCODING = "encoding"
    REFUSAL = "refusal"
    MAX_TOKENS = "max_tokens"
    BAD_JSON = "bad_json"


class OutputRejected(Exception):
    """Class for an output that must not be shown; it holds a reason code and never the text"""

    def __init__(self, reason: RejectReason) -> None:
        """Keep the reason code"""

        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True)
class Checked:
    """Class that holds a text allowed on the site, and why a part of it was dropped, if any"""

    content: dict[str, Any]
    dropped: RejectReason | None = None


class ToolTitleOutput(BaseModel):
    """Class that describes one entry of tool_titles"""

    model_config = ConfigDict(extra="forbid")

    name: StrictStr
    title: StrictStr
    sentence: StrictStr


class NoticeOutput(BaseModel):
    """Class that describes a notice as the AI must answer it; the API does not check lengths, this code does"""

    model_config = ConfigDict(extra="forbid")

    summary: StrictStr
    use_cases: list[StrictStr]
    tool_titles: list[ToolTitleOutput]
    mismatch: StrictBool
    alert: StrictStr


class TranslationItem(BaseModel):
    """Class that describes one translated description"""

    model_config = ConfigDict(extra="forbid")

    id: StrictStr
    text: StrictStr


class TranslationOutput(BaseModel):
    """Class that describes a translation as the AI must answer it"""

    model_config = ConfigDict(extra="forbid")

    items: list[TranslationItem]


def _parse(text: str, model: type[BaseModel]) -> Any:
    """Check an answer against its model, on this side of the API"""

    try:
        return model.model_validate(json.loads(text))
    except (ValueError, ValidationError) as error:
        raise OutputRejected(RejectReason.BAD_JSON) from error


def has_invisible(text: str) -> bool:
    """Tell whether a text holds a character of the invisible list of R01 and O07"""

    return INVISIBLE_PATTERN.search(text) is not None


def has_mojibake(text: str) -> bool:
    """Tell whether a text holds a sequence typical of UTF-8 read in another encoding, or the replacement character"""

    return MOJIBAKE_PATTERN.search(text) is not None


def _allowed_domain(domain: str, form_domains: list[str]) -> bool:
    """Tell whether a domain is one of the form or a parent of one of them"""

    return any(known == domain or known.endswith("." + domain) for known in form_domains)


def has_link(text: str, form_domains: list[str]) -> bool:
    """Tell whether a text holds a link mark, an e-mail address or a domain that the form does not hold"""

    lowered = text.lower()
    if any(mark in lowered for mark in LINK_MARKS) or EMAIL_PATTERN.search(lowered) is not None:
        return True
    for match in DOMAIN_PATTERN.finditer(lowered):
        domain = match.group(0)
        if domain.rsplit(".", 1)[1] in FILE_EXTENSIONS:
            continue
        if not _allowed_domain(domain, form_domains):
            return True
    return False


def _check_text(text: str, form_domains: list[str]) -> None:
    """Reject a text of the notice that holds an invisible character, a link or a reassuring word"""

    normalized = unicodedata.normalize("NFC", text)
    if has_mojibake(normalized):
        raise OutputRejected(RejectReason.ENCODING)
    if has_invisible(normalized):
        raise OutputRejected(RejectReason.INVISIBLE)
    if has_link(normalized, form_domains):
        raise OutputRejected(RejectReason.LINK)
    if has_forbidden_word(normalized):
        raise OutputRejected(RejectReason.FORBIDDEN_WORD)


def _check_length(text: str, limit: int) -> None:
    """Reject a text longer than its limit"""

    if len(text) > limit:
        raise OutputRejected(RejectReason.LENGTH)


def check_notice(text: str, form: dict[str, Any]) -> Checked:
    """Return the notice that may be shown, or reject it; mismatch false means no alert at all, never a good word"""

    output: NoticeOutput = _parse(text, NoticeOutput)
    domains: list[str] = form["domains_cited_in_code"]
    if not output.summary.strip():
        raise OutputRejected(RejectReason.BAD_JSON)
    _check_length(output.summary, MAX_SUMMARY)
    if len(output.use_cases) > MAX_USE_CASES:
        raise OutputRejected(RejectReason.LENGTH)
    for use_case in output.use_cases:
        _check_length(use_case, MAX_USE_CASE)
    alert = None
    if output.mismatch and output.alert.strip():
        _check_length(output.alert, MAX_ALERT)
        alert = output.alert
    for shown in (output.summary, *output.use_cases):
        _check_text(shown, domains)
    if alert is not None:
        _check_text(alert, domains)
    known = {tool["name"] for tool in form["tools"]}
    titles: dict[str, dict[str, str]] = {}
    dropped: RejectReason | None = None
    for entry in output.tool_titles:
        if entry.name not in known:
            dropped = dropped or RejectReason.UNKNOWN_TOOL
            continue
        if len(entry.title) > MAX_TITLE or len(entry.sentence) > MAX_SENTENCE or not entry.title.strip():
            dropped = dropped or RejectReason.LENGTH
            continue
        _check_text(entry.title, domains)
        _check_text(entry.sentence, domains)
        titles.setdefault(entry.name, {"name": entry.name, "title": entry.title, "sentence": entry.sentence})
    content = {
        "summary": output.summary,
        "use_cases": output.use_cases,
        "tool_titles": list(titles.values()),
        "alert": alert,
    }
    return Checked(content, dropped)


def _urls(text: str) -> set[str]:
    """Return the URLs of a text, without the punctuation that follows them"""

    return {match.group(0).rstrip(URL_TRAILING) for match in URL_PATTERN.finditer(text)}


def _translation_problem(translated: str, original: str) -> RejectReason | None:
    """Return why one translated description cannot be shown; reassuring words are the author's, not the AI's"""

    if not translated.strip() or len(translated) > TRANSLATION_FACTOR * len(original) + TRANSLATION_MARGIN:
        return RejectReason.LENGTH
    if has_mojibake(translated) and not has_mojibake(original):
        return RejectReason.ENCODING
    if has_invisible(translated):
        return RejectReason.INVISIBLE
    if not _urls(translated) <= _urls(original):
        return RejectReason.LINK
    return None


def check_translation(text: str, items: list[dict[str, str]]) -> Checked:
    """Return the translations that may be shown; a rejected one, or a missing one, stays in the original language"""

    output: TranslationOutput = _parse(text, TranslationOutput)
    originals = {item["id"]: item["text"] for item in items}
    accepted: dict[str, dict[str, str]] = {}
    dropped: RejectReason | None = None
    for item in output.items:
        if item.id not in originals:
            dropped = dropped or RejectReason.UNKNOWN_TOOL
            continue
        problem = _translation_problem(item.text, originals[item.id])
        if problem is not None:
            dropped = dropped or problem
            continue
        accepted.setdefault(item.id, {"id": item.id, "text": item.text})
    if not accepted:
        raise OutputRejected(dropped or RejectReason.BAD_JSON)
    return Checked({"items": list(accepted.values())}, dropped)
