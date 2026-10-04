"""Rule cards: every verdict rule is a registered class with its sources, kind and texts"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from mcplain.config import DEFAULT_LIMITS
from mcplain.models import (
    Alert,
    AlertKind,
    AnalysisResult,
    CallStep,
    Finding,
    Flow,
    LocationKind,
    ServerAnalysis,
    Tool,
    VerdictColor,
)

TEXT_FIELDS: tuple[str, ...] = ("title", "explanation", "false_positive")


@dataclass(frozen=True)
class RuleSource:
    """Class that names a public source that justifies a rule"""

    name: str
    url: str


@dataclass(frozen=True)
class RuleContext:
    """Class that gives a rule the analysis result and the analyzed server"""

    result: AnalysisResult
    server: ServerAnalysis | None

    def tools(self) -> list[Tool]:
        """Return the tools declared in server code"""

        if self.server is None:
            return []
        return [tool for tool in self.server.tools if tool.location_kind is LocationKind.SERVER_CODE]

    def outside_findings(self) -> list[Finding]:
        """Return the server code findings that no tool reaches"""

        if self.server is None:
            return []
        return [finding for finding in self.server.findings if finding.location_kind is LocationKind.SERVER_CODE]

    def flows(self) -> list[Flow]:
        """Return the flows whose sink is in server code"""

        if self.server is None:
            return []
        return [flow for flow in self.server.flows if flow.location_kind is LocationKind.SERVER_CODE]


class Rule(ABC):
    """Class for one verdict rule; its title, explanation and known false positive live in the locale files"""

    identifier: str = ""
    slug: str = ""
    color: VerdictColor = VerdictColor.ORANGE
    kind: AlertKind = AlertKind.SUSPICIOUS_USE
    sources: tuple[RuleSource, ...] = ()
    visible_in_code: bool = True

    @property
    def fixtures(self) -> str:
        """Return the folder of the rule fixtures, relative to engine/tests/fixtures"""

        return f"rules/{self.identifier}"

    def text_key(self, field: str) -> str:
        """Return the locale key of one text of the rule"""

        return f"rule.{self.identifier}.{field}"

    def alert(self, **values: object) -> Alert:
        """Build an alert of this rule"""

        quote = values.pop("quote", None)
        if isinstance(quote, str):
            quote = quote[: DEFAULT_LIMITS.max_snippet_chars]
        return Alert(rule=self.identifier, color=self.color, kind=self.kind, quote=quote, **values)

    def flow_alert(self, flow: Flow, detail: str | None = None) -> Alert:
        """Build an alert at the sink of a flow, with its source and the functions crossed"""

        return self.alert(
            tool=flow.tool,
            shared_by_tools=flow.shared_by_tools,
            outside=flow.outside,
            file=flow.sink_point.file,
            line=flow.sink_point.line,
            function=flow.sink_point.function,
            source=flow.source_point,
            steps=list(flow.steps),
            quote=flow.sink_point.snippet,
            detail=detail,
        )

    def finding_alert(self, finding: Finding, tool: str | None, detail: str | None = None) -> Alert:
        """Build an alert at a capability finding"""

        steps: list[CallStep] = list(finding.call_chain)
        return self.alert(
            tool=tool,
            shared_by_tools=finding.shared_by_tools,
            outside=finding.outside,
            file=finding.file,
            line=finding.line,
            function=finding.function,
            steps=steps,
            quote=finding.snippet,
            detail=detail,
        )

    @abstractmethod
    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Return the alerts this rule raises"""


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

    def get(self, identifier: str) -> Rule | None:
        """Return the rule with an identifier"""

        return self._rules.get(identifier)

    def has_red_rules(self) -> bool:
        """Tell whether at least one red rule is registered"""

        return any(rule.color is VerdictColor.RED for rule in self._rules.values())
