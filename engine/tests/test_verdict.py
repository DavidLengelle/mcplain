"""Tests for the verdict rule engine"""

import pytest

from mcplain.capabilities import Capability
from mcplain.models import (
    AnalysisResult,
    AnalysisStatus,
    DeclarationKind,
    Finding,
    LocationKind,
    ServerAnalysis,
    Tool,
    Verdict,
    VerdictColor,
)
from mcplain.models import Alert
from mcplain.rules.base import Rule, RuleContext, RuleRegistry
from mcplain.rules.orange import PowerfulCapability
from mcplain.verdict import DEFAULT_REGISTRY, compute_verdict


def finding(capability: Capability, location: LocationKind = LocationKind.SERVER_CODE) -> Finding:
    """Build a finding at a fixed place"""

    return Finding(capability=capability, file="server.py", line=1, column=1, snippet="x", location_kind=location)


def result(findings: list[Finding], status: AnalysisStatus = AnalysisStatus.OK) -> AnalysisResult:
    """Build a result with one server holding one tool"""

    server = ServerAnalysis(
        path=".",
        language="python",
        files_analyzed=1,
        tools=[
            Tool(
                name="t",
                description="d",
                description_is_dynamic=False,
                file="server.py",
                line=1,
                declaration=DeclarationKind.DECORATOR,
                location_kind=LocationKind.SERVER_CODE,
                findings=findings,
            )
        ],
    )
    return AnalysisResult(
        status=status,
        servers=[server],
        verdict=Verdict(color=VerdictColor.GRAY, provisional=True),
    )


class RedRule(Rule):
    """Class for a test rule that is always red"""

    identifier = "T01"
    color = VerdictColor.RED

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Always raise one alert"""

        return [self.alert(detail="test")]


def test_default_registry_has_red_rules() -> None:
    """Red rules exist, so verdicts are final"""

    assert DEFAULT_REGISTRY.has_red_rules()
    assert not compute_verdict(result([])).provisional


def test_green_without_powerful_capability() -> None:
    """Network and file reads alone stay green"""

    verdict = compute_verdict(result([finding(Capability.NETWORK), finding(Capability.FS_READ)]))
    assert verdict.color is VerdictColor.GREEN
    assert verdict.reasons == ["no_powerful_capability"]


@pytest.mark.parametrize(
    "capability",
    [
        Capability.PROCESS_EXEC,
        Capability.FS_WRITE,
        Capability.ENV_READ_SECRET,
        Capability.DYNAMIC_CODE,
        Capability.SENSITIVE_PATH,
        Capability.INSTALL_SCRIPT,
    ],
)
def test_orange_for_each_powerful_capability(capability: Capability) -> None:
    """Each powerful capability in server code turns the verdict orange"""

    verdict = compute_verdict(result([finding(capability)]))
    assert verdict.color is VerdictColor.ORANGE
    assert [(alert.rule, alert.tool, alert.detail) for alert in verdict.alerts] == [("O08", "t", capability.value)]


def test_tests_and_build_scripts_do_not_count() -> None:
    """Powerful capabilities outside server code do not change the verdict"""

    findings = [
        finding(Capability.PROCESS_EXEC, LocationKind.TEST_OR_EXAMPLE),
        finding(Capability.FS_WRITE, LocationKind.BUILD_SCRIPT),
    ]
    assert compute_verdict(result(findings)).color is VerdictColor.GREEN


@pytest.mark.parametrize(
    "status",
    [
        AnalysisStatus.MULTIPLE_SERVERS,
        AnalysisStatus.UNSUPPORTED_LANGUAGE,
        AnalysisStatus.COMPILED,
        AnalysisStatus.NOT_A_SERVER,
        AnalysisStatus.ERROR,
    ],
)
def test_gray_when_status_is_not_ok(status: AnalysisStatus) -> None:
    """Any status other than ok gives gray"""

    verdict = compute_verdict(result([finding(Capability.PROCESS_EXEC)], status))
    assert verdict.color is VerdictColor.GRAY
    assert verdict.reasons == [f"status.{status.value}"]


def test_gray_when_nothing_was_analyzed() -> None:
    """A server with no analyzed file gives gray"""

    empty = result([])
    empty.servers[0].files_analyzed = 0
    assert compute_verdict(empty).reasons == ["nothing_analyzable"]


def test_red_rule_makes_the_verdict_final() -> None:
    """Once a red rule exists, verdicts are no longer provisional"""

    registry = RuleRegistry()
    registry.register(PowerfulCapability())
    registry.register(RedRule())
    verdict = compute_verdict(result([finding(Capability.FS_WRITE)]), registry)
    assert verdict.color is VerdictColor.RED
    assert not verdict.provisional
    assert [alert.rule for alert in verdict.alerts] == ["T01", "O08"]


def test_duplicate_rule_is_refused() -> None:
    """Two rules cannot share an identifier"""

    registry = RuleRegistry()
    registry.register(RedRule())
    with pytest.raises(ValueError):
        registry.register(RedRule())
