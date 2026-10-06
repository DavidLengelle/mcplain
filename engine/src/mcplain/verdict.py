"""Verdict: the rule registry decides the color from the alerts of every registered rule, then the lamps"""

from mcplain.capabilities import Capability
from mcplain.lamps import lamp_states, level_for
from mcplain.models import (
    Alert,
    AnalysisResult,
    AnalysisStatus,
    Finding,
    GrayCase,
    InvisibleCategory,
    Lamp,
    LocationKind,
    Message,
    ServerAnalysis,
    Tool,
    Verdict,
    VerdictColor,
)
from mcplain.rules.base import RuleContext, RuleRegistry
from mcplain.rules.orange import ORANGE_RULES
from mcplain.rules.red import RED_RULES
from mcplain.rules.text import hidden_characters, tool_texts

RULES_VERSION = "1"
SEVERITY: dict[VerdictColor, int] = {
    VerdictColor.GREEN: 0,
    VerdictColor.GRAY: 0,
    VerdictColor.ORANGE: 1,
    VerdictColor.RED: 2,
}

CODE_HIDING_CATEGORIES: frozenset[InvisibleCategory] = frozenset(
    {InvisibleCategory.BIDI_CONTROL, InvisibleCategory.TAG, InvisibleCategory.VARIATION_SELECTOR}
)
STATUS_CASES: dict[AnalysisStatus, GrayCase] = {
    AnalysisStatus.MULTIPLE_SERVERS: GrayCase.MULTIPLE_SERVERS,
    AnalysisStatus.UNSUPPORTED_LANGUAGE: GrayCase.UNSUPPORTED_LANGUAGE,
    AnalysisStatus.COMPILED: GrayCase.COMPILED,
    AnalysisStatus.NOT_A_SERVER: GrayCase.NOT_A_SERVER,
    AnalysisStatus.ERROR: GrayCase.ERROR,
}
TIMEOUT_ERRORS: frozenset[str] = frozenset({"job.atelier_timeout", "fetch.timeout"})
LINK_LIST_NOTE = "note.mostly_documentation"
CAVEAT_PREFIX = "caveat."

DEFAULT_REGISTRY = RuleRegistry()
for rule_class in RED_RULES + ORANGE_RULES:
    DEFAULT_REGISTRY.register(rule_class())


def counted_findings(server: ServerAnalysis) -> list[Finding]:
    """Return the findings that count for the verdict: server code only"""

    findings = list(server.findings)
    for tool in server.tools:
        findings.extend(tool.findings)
    return [finding for finding in findings if finding.location_kind is LocationKind.SERVER_CODE]


def incomplete_reading(result: AnalysisResult) -> list[str]:
    """Return why the code could not be fully read and followed; any of them keeps the verdict from green"""

    codes = []
    servers = result.servers
    if "note.partially_compiled" in result.notes or any(server.compiled_files for server in servers):
        codes.append("caveat.partially_compiled")
    if any(error.location_kind is LocationKind.SERVER_CODE for server in servers for error in server.parse_errors):
        codes.append("caveat.parse_errors")
    if any(item.location_kind is LocationKind.SERVER_CODE for server in servers for item in server.skipped_files):
        codes.append("caveat.skipped_files")
    tools = [tool for server in servers for tool in server.tools if tool.location_kind is LocationKind.SERVER_CODE]
    if any(not server.tools for server in servers):
        codes.append("caveat.no_tools_found")
    if any(tool.gaps for tool in tools):
        codes.append("caveat.incomplete_tracking")
    if any(tool.description_is_dynamic for tool in tools):
        codes.append("caveat.dynamic_descriptions")
    return codes


def caveats(result: AnalysisResult) -> list[str]:
    """Return the warnings that do not change the color"""

    if any(server.minified_files for server in result.servers):
        return ["caveat.minified_files"]
    return []


def network_domains(result: AnalysisResult) -> tuple[list[str], bool]:
    """Return the fixed hosts of network calls in server code, and whether some call has no fixed host"""

    hosts: set[str] = set()
    unknown = False
    for server in result.servers:
        for finding in counted_findings(server):
            if finding.capability is not Capability.NETWORK:
                continue
            if finding.url_host is None:
                unknown = True
            else:
                hosts.add(finding.url_host)
    return sorted(hosts), unknown


def gray_case(result: AnalysisResult, reasons: list[str]) -> GrayCase:
    """Return the first reason of a gray verdict: the status, then nothing to read, then the first caveat"""

    case = STATUS_CASES.get(result.status)
    if case is GrayCase.ERROR and result.error is not None and result.error.code in TIMEOUT_ERRORS:
        return GrayCase.TIMEOUT
    if case is GrayCase.NOT_A_SERVER and LINK_LIST_NOTE in result.notes:
        return GrayCase.LINK_LIST
    if case is not None:
        return case
    known = {item.value for item in GrayCase}
    for reason in reasons:
        name = reason.removeprefix(CAVEAT_PREFIX)
        if name in known:
            return GrayCase(name)
    return GrayCase.NOTHING_ANALYZABLE


def headline(result: AnalysisResult, verdict: Verdict, unknown_network: bool) -> tuple[Message, Message]:
    """Return the title and the sentence of a verdict: the plain texts of the first alert, or those of its color"""

    if verdict.alerts:
        rule = verdict.alerts[0].rule
        return Message(code=f"rule.{rule}.plain_title"), Message(code=f"rule.{rule}.plain_found")
    if verdict.color is VerdictColor.GRAY and verdict.gray_case is not None:
        params: dict[str, str] = {}
        if verdict.gray_case is GrayCase.UNSUPPORTED_LANGUAGE:
            params["language"] = result.language or ""
        prefix = f"gray.{verdict.gray_case.value}"
        return Message(code=f"{prefix}.reason", params=params), Message(code=f"{prefix}.advice", params=params)
    title = Message(code="verdict.green.title")
    if unknown_network:
        return title, Message(code="verdict.green.summary_network")
    if verdict.contacted_domains:
        domains = ", ".join(verdict.contacted_domains)
        return title, Message(code="verdict.green.summary_domains", params={"domains": domains})
    return title, Message(code="verdict.green.summary")


def compute_verdict(result: AnalysisResult, registry: RuleRegistry = DEFAULT_REGISTRY) -> Verdict:
    """Red if a red rule fires, else orange if an orange rule fires, else gray if the reading is not complete, else green"""

    alerts: list[Alert] = []
    contexts = [RuleContext(result, server) for server in result.servers] or [RuleContext(result, None)]
    for context in contexts:
        for rule in registry.rules():
            alerts.extend(rule.evaluate(context))
    alerts.sort(key=lambda alert: -SEVERITY[alert.color])
    verdict = Verdict(
        color=VerdictColor.GREEN,
        alerts=alerts,
        rules_version=RULES_VERSION,
        rules_count=len(registry.rules()),
    )
    if alerts:
        verdict.color = alerts[0].color
    reasons: list[str] = []
    if result.status is not AnalysisStatus.OK:
        reasons.append(f"status.{result.status.value}")
    elif not result.servers or all(server.files_analyzed == 0 for server in result.servers):
        reasons.append("nothing_analyzable")
    reasons.extend(incomplete_reading(result))
    if not alerts and reasons:
        verdict.color = VerdictColor.GRAY
        verdict.gray_case = gray_case(result, reasons)
    unknown = False
    if verdict.color is VerdictColor.GREEN:
        domains, unknown = network_domains(result)
        verdict.contacted_domains = domains
        reasons.append("no_alert")
        if unknown:
            reasons.append("green.network_partly")
        elif domains:
            reasons.append("green.network")
    reasons.extend(caveats(result))
    verdict.reasons = reasons
    verdict.title, verdict.summary = headline(result, verdict, unknown)
    return verdict


def internet_domains(server: ServerAnalysis) -> list[str] | None:
    """Return the domains a server reaches when every network call of its counted code has a fixed host, else None"""

    calls = [finding for finding in counted_findings(server) if finding.capability is Capability.NETWORK]
    if not calls or any(finding.url_host is None for finding in calls):
        return None
    return sorted({finding.url_host for finding in calls if finding.url_host is not None})


def text_is_hidden(tool: Tool) -> bool:
    """Tell whether a name, title or description of a tool holds invisible characters the text rules report"""

    for item in tool_texts(tool):
        red, lone = hidden_characters(item.text)
        if red or lone:
            return True
    return False


def code_hides_text(server: ServerAnalysis, tool: str | None) -> bool:
    """Tell whether counted code outside the tool texts holds bidi controls, tags or variation selectors"""

    return any(
        item.location_kind is LocationKind.SERVER_CODE
        and not item.in_description
        and item.category in CODE_HIDING_CATEGORIES
        and (tool is None or item.tool == tool)
        for item in server.invisible_unicode
    )


def _lamps(capabilities: set[Capability], red_rules: set[str], hidden: bool) -> list[Lamp]:
    """Build the six lamps from what was found"""

    return [Lamp(id=lamp, state=state, rules=rules) for lamp, state, rules in lamp_states(capabilities, red_rules, hidden)]


def attach_lamps(result: AnalysisResult) -> None:
    """Set the lamps and fixed domains of each server, and the lamps and level of each tool, from the counted code"""

    alerts = result.verdict.alerts
    red_rules = {alert.rule for alert in alerts if alert.color is VerdictColor.RED}
    for server in result.servers:
        tools = [tool for tool in server.tools if tool.location_kind is LocationKind.SERVER_CODE]
        capabilities = {finding.capability for finding in counted_findings(server)}
        hidden = code_hides_text(server, None) or any(text_is_hidden(tool) for tool in tools)
        server.lamps = _lamps(capabilities, red_rules, hidden)
        server.internet_domains = internet_domains(server)
        for tool in server.tools:
            attached = [alert for alert in alerts if alert.tool is not None and alert.tool == tool.name]
            tool_red = {alert.rule for alert in attached if alert.color is VerdictColor.RED}
            orange = any(alert.color is VerdictColor.ORANGE for alert in attached)
            tool_capabilities = {
                finding.capability for finding in tool.findings if finding.location_kind is LocationKind.SERVER_CODE
            }
            tool_hidden = text_is_hidden(tool) or code_hides_text(server, tool.name)
            tool.lamps = _lamps(tool_capabilities, tool_red, tool_hidden)
            tool.level = level_for(bool(tool_red), orange)


def apply_verdict(result: AnalysisResult, registry: RuleRegistry = DEFAULT_REGISTRY) -> AnalysisResult:
    """Compute and attach the verdict, then the lamps it lights"""

    result.verdict = compute_verdict(result, registry)
    attach_lamps(result)
    return result


def has_lamps(result: AnalysisResult) -> bool:
    """Tell whether every server and every tool of a result carries its six lamps"""

    return all(server.lamps and all(tool.lamps for tool in server.tools) for server in result.servers)
