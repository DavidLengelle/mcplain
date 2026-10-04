"""Orange rules: powers and signs that deserve a careful look"""

from mcplain.capabilities import POWERFUL_CAPABILITIES, Capability, find_sensitive_paths
from mcplain.flows import ROLE_PROGRAM, FlowSinkKind, FlowSourceKind
from mcplain.models import Alert, Finding, LocationKind, OutsideKind, UrlKind, VerdictColor
from mcplain.patterns import excerpt, transmit_request
from mcplain.rules import sources
from mcplain.rules.base import Rule, RuleContext
from mcplain.rules.text import hidden_characters, tool_texts

READ_ONLY_BREAKERS: frozenset[Capability] = frozenset(
    {Capability.FS_WRITE, Capability.PROCESS_EXEC, Capability.DYNAMIC_CODE}
)


class OpenNetwork(Rule):
    """Class for O01: a tool sends requests to an address whose host is not fixed in the code"""

    identifier = "O01"
    slug = "open-network"
    color = VerdictColor.ORANGE
    sources = (sources.OWASP_MCP06, sources.LETHAL_TRIFECTA)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Raise one alert per tool that reaches a network call with a dynamic URL and no fixed host"""

        alerts = []
        for tool in context.tools():
            for finding in tool.findings:
                if (
                    finding.capability is Capability.NETWORK
                    and finding.url_kind is UrlKind.DYNAMIC
                    and finding.url_host is None
                    and finding.location_kind is LocationKind.SERVER_CODE
                ):
                    alerts.append(self.finding_alert(finding, tool.name, finding.detail))
                    break
        return alerts


class AiChoosesTheCommand(Rule):
    """Class for O02: a tool parameter is the whole command, the program, or code to evaluate"""

    identifier = "O02"
    slug = "ai-chooses-the-command"
    color = VerdictColor.ORANGE
    sources = (sources.OWASP_MCP05, sources.OWASP_LLM06)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Follow tool parameters given as is to a shell, as the program to run, or as code"""

        alerts = []
        for flow in context.flows():
            if flow.source is not FlowSourceKind.TOOL_PARAMETER:
                continue
            whole_command = flow.sink is FlowSinkKind.SHELL and not flow.pasted
            program = flow.sink is FlowSinkKind.PROCESS and flow.sink_role == ROLE_PROGRAM
            if whole_command or program or flow.sink is FlowSinkKind.CODE:
                alerts.append(self.flow_alert(flow, flow.source_detail))
        return alerts


class DescriptionFromInternet(Rule):
    """Class for O03: a tool description computed from a network response"""

    identifier = "O03"
    slug = "description-from-internet"
    color = VerdictColor.ORANGE
    sources = (sources.OWASP_MCP03, sources.INVARIANT_POISONING)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Follow network responses into tool descriptions"""

        return [
            self.flow_alert(flow, flow.sink_detail)
            for flow in context.flows()
            if flow.source is FlowSourceKind.NETWORK_RESPONSE and flow.sink is FlowSinkKind.TOOL_DESCRIPTION
        ]


class AnnotationMismatch(Rule):
    """Class for O04: a tool says it is read-only or closed, but its code writes, runs, sends or goes online"""

    identifier = "O04"
    slug = "annotation-mismatch"
    color = VerdictColor.ORANGE
    sources = (sources.MCP_ANNOTATIONS,)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Compare literal readOnlyHint and openWorldHint values with what the tool reaches"""

        alerts = []
        for tool in context.tools():
            findings = [finding for finding in tool.findings if finding.location_kind is LocationKind.SERVER_CODE]
            if tool.annotations.get("readOnlyHint") is True:
                for finding in findings:
                    sends = finding.capability is Capability.NETWORK and finding.sends
                    if finding.capability in READ_ONLY_BREAKERS or sends:
                        alerts.append(self.finding_alert(finding, tool.name, f"readOnlyHint: {finding.capability.value}"))
                        break
            if tool.annotations.get("openWorldHint") is False:
                for finding in findings:
                    if finding.capability is Capability.NETWORK:
                        alerts.append(self.finding_alert(finding, tool.name, "openWorldHint: network"))
                        break
        return alerts


class MentionsSensitivePath(Rule):
    """Class for O05: a description names a sensitive path without asking for its content"""

    identifier = "O05"
    slug = "mentions-sensitive-path"
    color = VerdictColor.ORANGE
    sources = (sources.INVARIANT_POISONING,)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Raise one alert per description that quotes a sensitive path, unless R03 already covers it"""

        alerts = []
        for tool in context.tools():
            names = [parameter.name for parameter in tool.parameters]
            for item in tool_texts(tool):
                if item.field == "name":
                    continue
                found = find_sensitive_paths(item.text)
                if not found or transmit_request(item.text, names) is not None:
                    continue
                index = item.text.find(found[0][1])
                detail = found[0][1]
                if item.parameter is not None:
                    detail = f"{detail} ({item.parameter})"
                alerts.append(
                    self.alert(
                        tool=tool.name,
                        file=tool.file,
                        line=tool.line,
                        quote=excerpt(item.text, max(index, 0)),
                        detail=detail,
                    )
                )
        return alerts


class DependencyWasMalicious(Rule):
    """Class for O06: a direct dependency has malicious versions, but not every version"""

    identifier = "O06"
    slug = "dependency-was-malicious"
    color = VerdictColor.ORANGE
    sources = (sources.OSV,)
    visible_in_code = False

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Raise one alert per MAL- identifier of a dependency that does not cover every version"""

        reputation = context.result.reputation
        if reputation is None:
            return []
        return [
            self.alert(detail=f"{report.id} {package.name}")
            for package in reputation.packages
            if package.dependency
            for report in package.malicious
            if not report.all_versions
        ]


class LoneInvisibleCharacter(Rule):
    """Class for O07: a single invisible character that its context does not explain"""

    identifier = "O07"
    slug = "lone-invisible-char"
    color = VerdictColor.ORANGE
    sources = (sources.REHBERGER_TAGS,)
    visible_in_code = False

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Raise one alert per tool text with a lone zero-width character"""

        alerts = []
        for tool in context.tools():
            for item in tool_texts(tool):
                _, lone = hidden_characters(item.text)
                if lone:
                    detail = "lone_zero_width"
                    if item.parameter is not None:
                        detail = f"{detail} ({item.parameter})"
                    quote = excerpt(item.text, lone[0].index)
                    alerts.append(self.alert(tool=tool.name, file=tool.file, line=tool.line, quote=quote, detail=detail))
        return alerts


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


ORANGE_RULES: tuple[type[Rule], ...] = (
    OpenNetwork,
    AiChoosesTheCommand,
    DescriptionFromInternet,
    AnnotationMismatch,
    MentionsSensitivePath,
    DependencyWasMalicious,
    LoneInvisibleCharacter,
    PowerfulCapability,
)
