"""Orange rules: powers and signs that deserve a careful look"""

from mcplain.capabilities import POWERFUL_CAPABILITIES, Capability, find_sensitive_paths
from mcplain.flows import ROLE_PROGRAM, FlowSinkKind, FlowSourceKind
from mcplain.models import (
    Alert,
    AlertKind,
    AnalysisResult,
    Finding,
    Flow,
    LocationKind,
    MaliciousReport,
    Message,
    OutsideKind,
    PackageReputation,
    UrlKind,
    VerdictColor,
)
from mcplain.patterns import (
    excerpt,
    plain_download,
    sentence_around,
    silence_request,
    silenced_sensitive_action,
    transmit_request,
)
from mcplain.rules import sources
from mcplain.rules.base import Rule, RuleContext
from mcplain.rules.red import (
    client_of,
    install_requests,
    installs_client_config,
    plain_install_request,
    tampering_flows,
)
from mcplain.rules.text import hidden_characters, tool_texts
from mcplain.version_ranges import range_excludes

RETIRED = "retired"
DOCKER_TITLE = "rule.O08.docker.plain_title"
QUOTE_LIMIT = 300
OUT_OF_RANGE = "range"
REGISTRY_NAMES: dict[str, str] = {"npm": "npm", "PyPI": "PyPI"}

READ_ONLY_BREAKERS: frozenset[Capability] = frozenset(
    {Capability.FS_WRITE, Capability.PROCESS_EXEC, Capability.DYNAMIC_CODE}
)


class OpenNetwork(Rule):
    """Class for O01: a tool sends requests to an address whose host is not fixed in the code"""

    identifier = "O01"
    slug = "open-network"
    color = VerdictColor.ORANGE
    kind = AlertKind.POWER_TO_KNOW
    sources = (sources.OWASP_MCP06, sources.LETHAL_TRIFECTA)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Raise alerts per tool on requests with a dynamic URL and no fixed host, the most direct one first"""

        flows = [
            flow
            for flow in context.flows()
            if flow.source is FlowSourceKind.TOOL_PARAMETER and flow.sink is FlowSinkKind.NETWORK
        ]
        alerts = []
        for tool in context.tools():
            ranked: list[tuple[tuple[int, int], Finding, Flow | None]] = []
            places: set[tuple[str, int]] = set()
            for finding in tool.findings:
                if not _open_request(finding) or (finding.file, finding.line) in places:
                    continue
                places.add((finding.file, finding.line))
                flow = _most_direct_flow(flows, tool.name, finding)
                ranked.append((_directness(flow, finding), finding, flow))
            ranked.sort(key=lambda item: item[0])
            for _, finding, flow in ranked:
                if flow is not None:
                    alerts.append(self.flow_alert(flow, finding.detail))
                    continue
                if not any(alert.tool == tool.name for alert in alerts):
                    alerts.append(self.finding_alert(finding, tool.name, finding.detail))
                break
        return alerts


def _open_request(finding: Finding) -> bool:
    """Tell whether a finding is a network call of server code with a dynamic URL and no fixed host"""

    return (
        finding.capability is Capability.NETWORK
        and finding.url_kind is UrlKind.DYNAMIC
        and finding.url_host is None
        and finding.location_kind is LocationKind.SERVER_CODE
    )


def _most_direct_flow(flows: list[Flow], tool: str, finding: Finding) -> Flow | None:
    """Return the flow of a tool parameter that reaches the request of a finding with the fewest steps"""

    matching = [
        flow
        for flow in flows
        if flow.tool == tool and flow.sink_point.file == finding.file and flow.sink_point.line == finding.line
    ]
    if not matching:
        return None
    return min(matching, key=lambda flow: (flow.pasted, len(flow.steps)))


def _directness(flow: Flow | None, finding: Finding) -> tuple[int, int]:
    """Rank a request: a value from the AI given as is, then pasted into text, then no flow; fewer steps first"""

    if flow is None:
        return 2, len(finding.call_chain)
    if flow.pasted:
        return 1, len(flow.steps)
    return 0, len(flow.steps)


class AiChoosesTheCommand(Rule):
    """Class for O02: a tool parameter is the whole command, the program, or code to evaluate"""

    identifier = "O02"
    slug = "ai-chooses-the-command"
    color = VerdictColor.ORANGE
    kind = AlertKind.POWER_TO_KNOW
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
    kind = AlertKind.POWER_TO_KNOW
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
    kind = AlertKind.POWER_TO_KNOW
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
    kind = AlertKind.POWER_TO_KNOW
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
    kind = AlertKind.POWER_TO_KNOW
    sources = (sources.OSV,)
    visible_in_code = False

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Raise one alert per MAL- identifier of a dependency whose versions may still be installed"""

        reputation = context.result.reputation
        if reputation is None:
            return []
        return [
            self.alert(detail=f"{report.id} {package.name}")
            for package in reputation.packages
            if package.dependency
            for report in package.malicious
            if not report.all_versions and cleared_reason(package, report) is None
        ]


def cleared_reason(package: PackageReputation, report: MaliciousReport) -> str | None:
    """Tell why the malicious versions of a dependency cannot be installed: retired, out of the declared range, or None"""

    if report.all_versions or not report.versions:
        return None
    candidates = report.versions
    if report.published is not None:
        candidates = report.published
        if not candidates:
            return RETIRED
    if all(range_excludes(package.ecosystem, package.declared_range, version) for version in candidates):
        return OUT_OF_RANGE
    return None


def cleared_dependencies(result: AnalysisResult) -> list[Message]:
    """Return one engine text per malicious report that O06 leaves out, with the reason"""

    if result.reputation is None:
        return []
    messages = []
    for package in result.reputation.packages:
        if not package.dependency:
            continue
        for report in package.malicious:
            reason = cleared_reason(package, report)
            if reason is None:
                continue
            params = {
                "package": package.name,
                "versions": ", ".join(report.versions),
                "registry": REGISTRY_NAMES.get(package.ecosystem, package.ecosystem),
                "range": package.declared_range or "",
                "id": report.id,
            }
            messages.append(Message(code=f"cleared.O06.{reason}", params=params))
    return messages


class LoneInvisibleCharacter(Rule):
    """Class for O07: a single invisible character that its context does not explain"""

    identifier = "O07"
    slug = "lone-invisible-char"
    color = VerdictColor.ORANGE
    kind = AlertKind.POWER_TO_KNOW
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
    kind = AlertKind.POWER_TO_KNOW
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
                    alerts.append(self._capability_alert(finding, tool.name))
        grouped: dict[tuple[str, bool, OutsideKind | None], Finding] = {}
        for finding in context.outside_findings():
            if finding.capability in POWERFUL_CAPABILITIES and finding.unused_library is None:
                grouped.setdefault((finding.capability.value, finding.shared_by_tools, finding.outside), finding)
        for finding in grouped.values():
            alerts.append(self._capability_alert(finding, None))
        return alerts

    def _capability_alert(self, finding: Finding, tool: str | None) -> Alert:
        """Build the alert of one capability, with the precise title of the Docker socket"""

        alert = self.finding_alert(finding, tool, finding.capability.value)
        if finding.capability is Capability.DOCKER_SOCKET:
            alert.title = DOCKER_TITLE
        return alert


class SilenceToCheck(Rule):
    """Class for O09: a description asks the AI to keep something from the user, without a sensitive action"""

    identifier = "O09"
    slug = "silence-to-check"
    color = VerdictColor.ORANGE
    kind = AlertKind.POWER_TO_KNOW
    sources = (sources.INVARIANT_POISONING, sources.OWASP_MCP03)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Quote every request for silence that R02 leaves aside, so that the user can read it"""

        alerts = []
        for tool in context.tools():
            for item in tool_texts(tool):
                if item.field == "name":
                    continue
                match = silence_request(item.text)
                if match is None or silenced_sensitive_action(item.text, match):
                    continue
                sentence = sentence_around(item.text, match.start(), match.end(), with_mark=True)
                quote = " ".join(sentence.split())[:QUOTE_LIMIT]
                detail = item.parameter
                alerts.append(self.alert(tool=tool.name, file=tool.file, line=tool.line, quote=quote, detail=detail))
        return alerts


class InstallerEditsClientConfig(Rule):
    """Class for O10: an install command the user runs writes the configuration of an MCP client"""

    identifier = "O10"
    slug = "installer-edits-client-config"
    color = VerdictColor.ORANGE
    kind = AlertKind.POWER_TO_KNOW
    sources = (sources.INVARIANT_POISONING, sources.ATTACK_T1546_004)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Take the writes that R08 leaves aside: an install command, not the server, writes an MCP client config"""

        alerts = []
        seen: set[tuple[str, int, str]] = set()
        for flow in tampering_flows(context):
            if not installs_client_config(context, flow):
                continue
            client = client_of(context, flow)
            key = (flow.sink_point.file, flow.sink_point.line, client)
            if key in seen:
                continue
            seen.add(key)
            alert = self.flow_alert(flow, flow.source_detail)
            alert.params = {"client": client}
            alerts.append(alert)
        return alerts


class InstallContactsInternet(Rule):
    """Class for O11: a request made at install time that only carries plain values, to a fixed host"""

    identifier = "O11"
    slug = "install-contacts-internet"
    color = VerdictColor.ORANGE
    kind = AlertKind.POWER_TO_KNOW
    sources = (sources.SHAI_HULUD_PREINSTALL, sources.OWASP_MCP04)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Take the install requests that R10 leaves aside, naming the host each one contacts"""

        alerts: list[Alert] = []
        if context.server is None:
            return alerts
        for script in context.server.install_scripts:
            host = plain_download(script.command)
            if script.downloads and host is not None:
                alert = self.alert(file=script.file, line=script.line, quote=script.command, detail=script.kind)
                alert.params = {"domain": host}
                alerts.append(alert)
        for finding in install_requests(context):
            if plain_install_request(finding) and finding.url_host is not None:
                alert = self.finding_alert(finding, None, finding.detail)
                alert.params = {"domain": finding.url_host}
                alerts.append(alert)
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
    SilenceToCheck,
    InstallerEditsClientConfig,
    InstallContactsInternet,
)
