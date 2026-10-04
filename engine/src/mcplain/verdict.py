"""Verdict: the rule registry decides the color from the alerts of every registered rule"""

from mcplain.models import (
    AnalysisResult,
    AnalysisStatus,
    Finding,
    LocationKind,
    ServerAnalysis,
    Verdict,
    VerdictColor,
)
from mcplain.rules.base import RuleContext, RuleRegistry
from mcplain.rules.orange import PowerfulCapability
from mcplain.rules.red import RED_RULES

SEVERITY: dict[VerdictColor, int] = {
    VerdictColor.GREEN: 0,
    VerdictColor.ORANGE: 1,
    VerdictColor.RED: 2,
}

DEFAULT_REGISTRY = RuleRegistry()
for rule_class in RED_RULES:
    DEFAULT_REGISTRY.register(rule_class())
DEFAULT_REGISTRY.register(PowerfulCapability())

def counted_findings(server: ServerAnalysis) -> list[Finding]:
    """Return the findings that count for the verdict: server code only"""

    findings = list(server.findings)
    for tool in server.tools:
        findings.extend(tool.findings)
    return [finding for finding in findings if finding.location_kind is LocationKind.SERVER_CODE]


def caveats(result: AnalysisResult) -> list[str]:
    """Return the reason codes that limit how much the verdict can be trusted"""

    codes = []
    servers = result.servers
    if "note.partially_compiled" in result.notes or any(server.compiled_files for server in servers):
        codes.append("caveat.partially_compiled")
    if any(server.minified_files for server in servers):
        codes.append("caveat.minified_files")
    if any(server.parse_errors for server in servers):
        codes.append("caveat.parse_errors")
    if any(server.skipped_files for server in servers):
        codes.append("caveat.skipped_files")
    if any(not server.tools for server in servers):
        codes.append("caveat.no_tools_found")
    if any(tool.description_is_dynamic for server in servers for tool in server.tools):
        codes.append("caveat.dynamic_descriptions")
    if any(
        item.location_kind is LocationKind.SERVER_CODE for server in servers for item in server.invisible_unicode
    ):
        codes.append("caveat.invisible_unicode")
    return codes


def compute_verdict(result: AnalysisResult, registry: RuleRegistry = DEFAULT_REGISTRY) -> Verdict:
    """Compute the verdict of an analysis with the registered rules"""

    provisional = not registry.has_red_rules()
    if result.status is not AnalysisStatus.OK:
        return Verdict(color=VerdictColor.GRAY, reasons=[f"status.{result.status.value}"], provisional=provisional)
    if not result.servers or all(server.files_analyzed == 0 for server in result.servers):
        return Verdict(color=VerdictColor.GRAY, reasons=["nothing_analyzable"], provisional=provisional)
    color = VerdictColor.GREEN
    alerts = []
    for server in result.servers:
        context = RuleContext(result, server)
        for rule in registry.rules():
            found = rule.evaluate(context)
            alerts.extend(found)
            if found and SEVERITY[rule.color] > SEVERITY[color]:
                color = rule.color
    alerts.sort(key=lambda alert: -SEVERITY[alert.color])
    reasons: list[str] = []
    if not alerts:
        reasons.append("no_powerful_capability")
    reasons.extend(caveats(result))
    return Verdict(color=color, alerts=alerts, reasons=reasons, provisional=provisional)
