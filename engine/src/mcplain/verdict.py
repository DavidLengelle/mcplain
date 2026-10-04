"""Extensible rule engine that turns an analysis into a verdict"""

from abc import ABC, abstractmethod

from mcplain.capabilities import POWERFUL_CAPABILITIES
from mcplain.models import (
    AnalysisResult,
    AnalysisStatus,
    Finding,
    LocationKind,
    ServerAnalysis,
    Verdict,
    VerdictColor,
)

SEVERITY: dict[VerdictColor, int] = {
    VerdictColor.GREEN: 0,
    VerdictColor.ORANGE: 1,
    VerdictColor.RED: 2,
}


class Rule(ABC):
    """Class that describes one verdict rule and where it comes from"""

    identifier: str = ""
    color: VerdictColor = VerdictColor.GREEN
    source: str = ""
    description: str = ""

    @abstractmethod
    def evaluate(self, server: ServerAnalysis) -> list[str]:
        """Return the reason codes this rule raises for a server"""


class RuleRegistry:
    """Class that keeps the rules used to compute verdicts"""

    def __init__(self) -> None:
        """Start with no rule"""

        self._rules: dict[str, Rule] = {}

    def register(self, rule: Rule) -> None:
        """Add a rule, refusing duplicate identifiers"""

        if rule.identifier in self._rules:
            raise ValueError(rule.identifier)
        self._rules[rule.identifier] = rule

    def rules(self) -> list[Rule]:
        """Return the registered rules in registration order"""

        return list(self._rules.values())

    def has_red_rules(self) -> bool:
        """Tell whether at least one red rule is registered"""

        return any(rule.color is VerdictColor.RED for rule in self._rules.values())


def counted_findings(server: ServerAnalysis) -> list[Finding]:
    """Return the findings that count for the verdict: server code only"""

    findings = list(server.findings)
    for tool in server.tools:
        findings.extend(tool.findings)
    return [finding for finding in findings if finding.location_kind is LocationKind.SERVER_CODE]


class PowerfulCapabilityRule(Rule):
    """Class for the provisional rule that flags powerful capabilities in server code"""

    identifier = "provisional.powerful_capability"
    color = VerdictColor.ORANGE
    source = "mcplain:provisional"
    description = "rule.provisional.powerful_capability"

    def evaluate(self, server: ServerAnalysis) -> list[str]:
        """Return one reason per powerful capability found in server code"""

        found = {finding.capability for finding in counted_findings(server)}
        return [f"capability.{capability.value}" for capability in sorted(found & POWERFUL_CAPABILITIES)]


DEFAULT_REGISTRY = RuleRegistry()
DEFAULT_REGISTRY.register(PowerfulCapabilityRule())


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
    reasons: list[str] = []
    for server in result.servers:
        for rule in registry.rules():
            codes = rule.evaluate(server)
            if not codes:
                continue
            for code in codes:
                if code not in reasons:
                    reasons.append(code)
            if SEVERITY[rule.color] > SEVERITY[color]:
                color = rule.color
    if not reasons:
        reasons.append("no_powerful_capability")
    reasons.extend(caveats(result))
    return Verdict(color=color, reasons=reasons, provisional=provisional)
