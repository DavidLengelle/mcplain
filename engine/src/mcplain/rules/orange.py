"""Orange rules: powers and signs that deserve a careful look"""

from mcplain.capabilities import POWERFUL_CAPABILITIES
from mcplain.models import Alert, Finding, LocationKind, OutsideKind, VerdictColor
from mcplain.rules import sources
from mcplain.rules.base import Rule, RuleContext


class PowerfulCapability(Rule):
    """Class for O08: a powerful capability in server code, one alert per capability and place"""

    identifier = "O08"
    slug = "powerful-capability"
    color = VerdictColor.ORANGE
    sources = (sources.OWASP_LLM06, sources.OWASP_MCP02)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Raise one alert per powerful capability of each tool, and of each kind of code outside the tools"""

        alerts = []
        for tool in context.tools():
            seen: set[str] = set()
            for finding in tool.findings:
                if finding.location_kind is not LocationKind.SERVER_CODE:
                    continue
                if finding.capability in POWERFUL_CAPABILITIES and finding.capability.value not in seen:
                    seen.add(finding.capability.value)
                    alerts.append(self.finding_alert(finding, tool.name, finding.capability.value))
        grouped: dict[tuple[str, bool, OutsideKind | None], Finding] = {}
        for finding in context.outside_findings():
            if finding.capability in POWERFUL_CAPABILITIES:
                grouped.setdefault((finding.capability.value, finding.shared_by_tools, finding.outside), finding)
        for (capability, _, _), finding in grouped.items():
            alerts.append(self.finding_alert(finding, None, capability))
        return alerts
