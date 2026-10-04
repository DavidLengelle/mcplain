"""Verdict: the rule registry decides the color from the alerts of every registered rule"""

from mcplain.capabilities import Capability
from mcplain.models import (
    Alert,
    AnalysisResult,
    AnalysisStatus,
    Finding,
    LocationKind,
    ServerAnalysis,
    Verdict,
    VerdictColor,
)
from mcplain.rules.base import RuleContext, RuleRegistry
from mcplain.rules.orange import ORANGE_RULES
from mcplain.rules.red import RED_RULES

RULES_VERSION = "1"
SEVERITY: dict[VerdictColor, int] = {
    VerdictColor.GREEN: 0,
    VerdictColor.GRAY: 0,
    VerdictColor.ORANGE: 1,
    VerdictColor.RED: 2,
}

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
    return verdict
