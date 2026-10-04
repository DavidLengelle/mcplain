"""Red rules: code that hides, steals, plants or runs something, or a serious flaw an attacker can use"""

from mcplain.capabilities import Capability, PathKind, find_sensitive_paths
from mcplain.flows import FlowSinkKind, FlowSourceKind
from mcplain.models import (
    Alert,
    AlertKind,
    Flow,
    InvisibleCategory,
    LocationKind,
    OutsideKind,
    TextMatchKind,
    VerdictColor,
)
from mcplain.patterns import analyzer_talk, excerpt, silence_request, transmit_request
from mcplain.rules import sources
from mcplain.rules.base import Rule, RuleContext
from mcplain.rules.text import ToolText, hidden_characters, tool_texts

CODE_SINKS: frozenset[FlowSinkKind] = frozenset({FlowSinkKind.CODE, FlowSinkKind.SHELL})
TAMPERING_KINDS: frozenset[PathKind] = frozenset({PathKind.AUTOSTART, PathKind.TOOL_CONFIG})


def text_alert(rule: Rule, item: ToolText, quote: str, detail: str | None = None) -> Alert:
    """Build an alert on a text of a tool"""

    if item.parameter is not None:
        detail = f"{detail} ({item.parameter})" if detail else item.parameter
    return rule.alert(tool=item.tool.name, file=item.tool.file, line=item.tool.line, quote=quote, detail=detail)


def flows_to(context: RuleContext, sources_kinds: set[FlowSourceKind], sinks: set[FlowSinkKind]) -> list[Flow]:
    """Return the server code flows from some sources to some sinks"""

    return [flow for flow in context.flows() if flow.source in sources_kinds and flow.sink in sinks]


class InvisibleText(Rule):
    """Class for R01: invisible characters that hide text from the user but not from the AI"""

    identifier = "R01"
    slug = "invisible-text"
    color = VerdictColor.RED
    sources = (sources.REHBERGER_TAGS, sources.TROJAN_SOURCE, sources.OWASP_MCP03)
    visible_in_code = False

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Check names and descriptions, then bidirectional controls written anywhere in the code"""

        alerts = []
        for tool in context.tools():
            for item in tool_texts(tool):
                red, _ = hidden_characters(item.text)
                if red:
                    detail = ", ".join(dict.fromkeys(hit.kind for hit in red))
                    alerts.append(text_alert(self, item, excerpt(item.text, red[0].index), detail))
        if context.server is not None:
            for invisible in context.server.invisible_unicode:
                if (
                    invisible.in_source
                    and not invisible.in_description
                    and invisible.category is InvisibleCategory.BIDI_CONTROL
                    and invisible.location_kind is LocationKind.SERVER_CODE
                ):
                    alerts.append(
                        self.alert(
                            tool=invisible.tool,
                            file=invisible.file,
                            line=invisible.line,
                            detail=f"bidi_control {' '.join(invisible.codepoints)}",
                        )
                    )
        return alerts


class AsksForSilence(Rule):
    """Class for R02: a description that asks the AI to hide what it does from the user"""

    identifier = "R02"
    slug = "asks-for-silence"
    color = VerdictColor.RED
    sources = (sources.INVARIANT_POISONING, sources.OWASP_MCP03)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Look for a negation near a verb of telling, aimed at the user or at the current action"""

        alerts = []
        for tool in context.tools():
            for item in tool_texts(tool):
                if item.field == "name":
                    continue
                match = silence_request(item.text)
                if match is not None:
                    alerts.append(text_alert(self, item, excerpt(item.text, match.start(), match.end())))
        return alerts


class AsksForSensitiveFile(Rule):
    """Class for R03: a description that names a sensitive path and asks to pass its content"""

    identifier = "R03"
    slug = "asks-for-sensitive-file"
    color = VerdictColor.RED
    sources = (sources.INVARIANT_POISONING, sources.OWASP_MCP03)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Look for a sensitive path and a sentence that asks to put content into an argument"""

        alerts = []
        for tool in context.tools():
            names = [parameter.name for parameter in tool.parameters]
            for item in tool_texts(tool):
                if item.field == "name":
                    continue
                found = find_sensitive_paths(item.text)
                if not found:
                    continue
                sentence = transmit_request(item.text, names)
                if sentence is not None:
                    alerts.append(text_alert(self, item, sentence, found[0][1]))
        return alerts


class LeaksSecrets(Rule):
    """Class for R04: a secret file or the whole environment sent over the network"""

    identifier = "R04"
    slug = "leaks-secrets"
    color = VerdictColor.RED
    sources = (sources.OWASP_MCP01, sources.CWE_201, sources.SHAI_HULUD)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Follow flows from secret files and from the whole environment to a network send"""

        alerts = []
        for flow in flows_to(context, {FlowSourceKind.SENSITIVE_FILE, FlowSourceKind.ENVIRONMENT}, {FlowSinkKind.NETWORK}):
            if flow.source is FlowSourceKind.SENSITIVE_FILE and PathKind.SECRET not in flow.path_kinds:
                continue
            alerts.append(self.flow_alert(flow, flow.source_detail))
        return alerts


class HiddenCopy(Rule):
    """Class for R05: an e-mail address written in the code as a cc or bcc recipient"""

    identifier = "R05"
    slug = "hidden-copy"
    color = VerdictColor.RED
    sources = (sources.POSTMARK,)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Raise one alert per hard-coded copy recipient in server code"""

        if context.server is None:
            return []
        return [
            self.alert(
                tool=copy.tool,
                file=copy.file,
                line=copy.line,
                quote=copy.quote,
                detail=f"{copy.field}: {copy.address}",
            )
            for copy in context.server.copy_recipients
            if copy.location_kind is LocationKind.SERVER_CODE
        ]


class HiddenCode(Rule):
    """Class for R06: an encoded literal of the package, decoded, then run"""

    identifier = "R06"
    slug = "hidden-code"
    color = VerdictColor.RED
    sources = (sources.CWE_506, sources.OPENSSF_MALICIOUS)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Follow flows from decoded package literals to code, shell, processes or a written file that is run"""

        sinks = {FlowSinkKind.CODE, FlowSinkKind.SHELL, FlowSinkKind.PROCESS, FlowSinkKind.RUN_FILE}
        return [
            self.flow_alert(flow, flow.source_detail)
            for flow in flows_to(context, {FlowSourceKind.ENCODED_LITERAL}, sinks)
            if flow.sink is not FlowSinkKind.RUN_FILE or flow.written_file
        ]


class DownloadAndRun(Rule):
    """Class for R07: code downloaded from the network, then run"""

    identifier = "R07"
    slug = "download-and-run"
    color = VerdictColor.RED
    sources = (sources.CWE_494, sources.ATTACK_T1105)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Follow network responses into code or a shell, written files that are run, and curl | sh strings"""

        alerts = []
        sinks = {FlowSinkKind.CODE, FlowSinkKind.SHELL, FlowSinkKind.RUN_FILE}
        for flow in flows_to(context, {FlowSourceKind.NETWORK_RESPONSE}, sinks):
            if flow.sink is FlowSinkKind.RUN_FILE and not flow.written_file:
                continue
            alerts.append(self.flow_alert(flow, flow.sink_detail))
        if context.server is not None:
            for match in context.server.text_matches:
                if match.kind is TextMatchKind.PIPE_TO_SHELL and match.location_kind is LocationKind.SERVER_CODE:
                    alerts.append(self.alert(tool=match.tool, file=match.file, line=match.line, quote=match.quote))
        return alerts


class AutostartOrConfigTampering(Rule):
    """Class for R08: a write to a file that starts code automatically or configures another tool"""

    identifier = "R08"
    slug = "autostart-or-config-tampering"
    color = VerdictColor.RED
    sources = (sources.ATTACK_T1546_004, sources.ATTACK_T1098_004, sources.INVARIANT_POISONING)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Follow sensitive paths of the autostart or tool configuration kinds into a file write"""

        return [
            self.flow_alert(flow, flow.source_detail)
            for flow in flows_to(context, {FlowSourceKind.SENSITIVE_PATH}, {FlowSinkKind.FILE_WRITE})
            if flow.sink_role == "path" and TAMPERING_KINDS & set(flow.path_kinds)
        ]


class CommandInjection(Rule):
    """Class for R09: a tool parameter pasted into a command run by a shell"""

    identifier = "R09"
    slug = "command-injection"
    color = VerdictColor.RED
    kind = AlertKind.SERIOUS_FLAW
    sources = (sources.OWASP_MCP05, sources.CWE_78)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Follow tool parameters pasted into a string that a shell runs"""

        return [
            self.flow_alert(flow, flow.source_detail)
            for flow in flows_to(context, {FlowSourceKind.TOOL_PARAMETER}, {FlowSinkKind.SHELL})
            if flow.pasted
        ]


class InstallGoesOnline(Rule):
    """Class for R10: code run at install time that downloads something or reaches the network"""

    identifier = "R10"
    slug = "install-goes-online"
    color = VerdictColor.RED
    sources = (sources.SHAI_HULUD, sources.SHAI_HULUD_PREINSTALL, sources.OWASP_MCP04, sources.OSV_SETUP_PY)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Check install scripts and the code they run"""

        alerts: list[Alert] = []
        if context.server is None:
            return alerts
        for script in context.server.install_scripts:
            if script.downloads:
                alerts.append(self.alert(file=script.file, line=script.line, quote=script.command, detail=script.kind))
        for finding in context.outside_findings():
            if finding.capability is Capability.NETWORK and finding.outside is OutsideKind.INSTALL:
                alerts.append(self.finding_alert(finding, None, finding.detail))
        return alerts


class KnownMalicious(Rule):
    """Class for R11: OSV.dev lists the analyzed package, or every version of a dependency, as malicious"""

    identifier = "R11"
    slug = "known-malicious"
    color = VerdictColor.RED
    sources = (sources.OPENSSF_MALICIOUS, sources.OSV)
    visible_in_code = False

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Raise one alert per MAL- identifier of the package, or of a dependency that is malicious in every version"""

        reputation = context.result.reputation
        if reputation is None:
            return []
        alerts = []
        for package in reputation.packages:
            for report in package.malicious:
                if not package.dependency or report.all_versions:
                    name = package.name if package.version is None else f"{package.name} {package.version}"
                    alerts.append(self.alert(detail=f"{report.id} {name}"))
        return alerts


class TalksToTheAnalyzer(Rule):
    """Class for R12: strings, comments or descriptions that speak to an analysis tool"""

    identifier = "R12"
    slug = "talks-to-the-analyzer"
    color = VerdictColor.RED
    sources = (sources.OWASP_LLM01, sources.MCPLAIN_RULE)

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Raise one alert per passage that addresses a scanner, a reviewer or MCPlain"""

        alerts = []
        if context.server is not None:
            for match in context.server.text_matches:
                if match.kind is TextMatchKind.ANALYZER_TALK and match.location_kind is LocationKind.SERVER_CODE:
                    alerts.append(self.alert(tool=match.tool, file=match.file, line=match.line, quote=match.quote))
        for tool in context.tools():
            quotes = [alert.quote for alert in alerts if alert.tool == tool.name and alert.quote]
            for item in tool_texts(tool):
                found = analyzer_talk(item.text)
                if found is None or any(quote in item.text for quote in quotes):
                    continue
                alerts.append(text_alert(self, item, excerpt(item.text, found.start(), found.end())))
        return alerts


RED_RULES: tuple[type[Rule], ...] = (
    InvisibleText,
    AsksForSilence,
    AsksForSensitiveFile,
    LeaksSecrets,
    HiddenCopy,
    HiddenCode,
    DownloadAndRun,
    AutostartOrConfigTampering,
    CommandInjection,
    InstallGoesOnline,
    KnownMalicious,
    TalksToTheAnalyzer,
)
