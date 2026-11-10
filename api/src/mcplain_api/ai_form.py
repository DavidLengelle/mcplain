"""The form given to the AI, built only from a validated report; no text of a third party ever enters it"""

import hashlib
import json
import re
from typing import Any

from mcplain.models import AnalysisResult, LocationKind, ServerAnalysis

MAX_FORM_TOOLS = 60
MAX_TOOL_NAME_CHARS = 40
MAX_DOMAINS = 20
MAX_DOMAIN_CHARS = 253
MAX_TRANSLATION_CHARS = 12_000
LANGUAGES: frozenset[str] = frozenset({"python", "javascript", "typescript"})
UNKNOWN_LANGUAGE = "unknown"
CAPABILITIES: dict[str, str] = {
    "files_read": "reads_files",
    "files_write": "writes_files",
    "internet": "internet",
    "commands": "commands",
    "secrets": "secrets",
    "hidden_text": "hidden_text",
}
LAMP_OFF = "off"
NAME_REJECTED = re.compile(r"[^A-Za-z0-9_]+")
DOMAIN_ALLOWED = re.compile(r"^[a-z0-9.-]+$")
TOOL_ID_PREFIX = "tool_"
PARAMETER_ID_PART = "_param_"


def first_server(result: AnalysisResult) -> ServerAnalysis | None:
    """Return the server the report shows, or None"""

    if not result.servers:
        return None
    return result.servers[0]


def has_tools(result: AnalysisResult) -> bool:
    """Tell whether the engine recognized at least one tool"""

    server = first_server(result)
    return server is not None and len(server.tools) > 0


def form_tool_name(name: str, position: int, taken: set[str]) -> str:
    """Return a tool name made only of letters, digits and underscores, different from those already taken"""

    base = NAME_REJECTED.sub("_", name).strip("_")[:MAX_TOOL_NAME_CHARS].strip("_")
    if not base:
        base = f"{TOOL_ID_PREFIX}{position}"
    candidate = base
    suffix = 2
    while candidate in taken:
        ending = f"_{suffix}"
        candidate = base[: MAX_TOOL_NAME_CHARS - len(ending)] + ending
        suffix += 1
    taken.add(candidate)
    return candidate


def tool_capabilities(lamps: list[Any]) -> dict[str, bool]:
    """Return yes or no for the six lamps: danger counts as yes, and the AI never sees a color"""

    states = {lamp.id: lamp.state for lamp in lamps}
    return {name: states.get(lamp, LAMP_OFF) != LAMP_OFF for lamp, name in CAPABILITIES.items()}


def cited_domains(server: ServerAnalysis) -> list[str]:
    """Return the host names of the URLs written in the server code, filtered; they may never be contacted"""

    domains: set[str] = set()
    for reference in server.domains:
        domain = reference.domain.strip().lower()
        if reference.location_kind is not LocationKind.SERVER_CODE:
            continue
        if len(domain) <= MAX_DOMAIN_CHARS and DOMAIN_ALLOWED.match(domain):
            domains.add(domain)
    return sorted(domains)[:MAX_DOMAINS]


def build_form(result: AnalysisResult) -> dict[str, Any] | None:
    """Return the form of a validated report, or None without any recognized tool"""

    server = first_server(result)
    if server is None or not server.tools:
        return None
    taken: set[str] = set()
    tools = []
    for position, tool in enumerate(server.tools[:MAX_FORM_TOOLS], start=1):
        tools.append({"name": form_tool_name(tool.name, position, taken), "capabilities": tool_capabilities(tool.lamps)})
    language = UNKNOWN_LANGUAGE
    if server.language in LANGUAGES:
        language = server.language
    return {
        "language": language,
        "tool_count": len(server.tools),
        "tools": tools,
        "domains_cited_in_code": cited_domains(server),
        "libraries": [],
    }


def canonical_json(value: Any) -> str:
    """Return one exact JSON text for a value: sorted keys, no spaces"""

    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_hash(value: Any) -> str:
    """Return the SHA-256 of the canonical JSON of a value"""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parameter_id(tool_index: int, parameter_index: int) -> str:
    """Return the identifier MCPlain gives to a parameter description: positions only, never a name"""

    return f"{TOOL_ID_PREFIX}{tool_index}{PARAMETER_ID_PART}{parameter_index}"


def translation_items(result: AnalysisResult) -> list[dict[str, str]]:
    """Return the author descriptions to translate: every tool first, then the parameters in tool order, until the limit"""

    server = first_server(result)
    if server is None:
        return []
    candidates: list[tuple[str, str]] = []
    for index, tool in enumerate(server.tools):
        if tool.description.strip():
            candidates.append((f"{TOOL_ID_PREFIX}{index}", tool.description))
    for index, tool in enumerate(server.tools):
        for position, parameter in enumerate(tool.parameters):
            if parameter.description is not None and parameter.description.strip():
                candidates.append((parameter_id(index, position), parameter.description))
    items: list[dict[str, str]] = []
    total = 0
    for identifier, text in candidates:
        total += len(text)
        if total > MAX_TRANSLATION_CHARS:
            break
        items.append({"id": identifier, "text": text})
    return items
