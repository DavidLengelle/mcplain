"""Tests for the verdict rule engine"""

import pytest

from mcplain.capabilities import Capability
from mcplain.models import (
    Alert,
    AnalysisResult,
    AnalysisStatus,
    DeclarationKind,
    Finding,
    LocationKind,
    ServerAnalysis,
    Tool,
    TrackingGap,
    Verdict,
    VerdictColor,
)
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
        verdict=Verdict(color=VerdictColor.GRAY),
    )


class RedRule(Rule):
    """Class for a test rule that is always red"""

    identifier = "T01"
    color = VerdictColor.RED

    def evaluate(self, context: RuleContext) -> list[Alert]:
        """Always raise one alert"""

        return [self.alert(detail="test")]


def test_default_registry_has_the_twenty_rules() -> None:
    """The verdict says which version of the rules it used and how many rules there are"""

    assert DEFAULT_REGISTRY.has_red_rules()
    verdict = compute_verdict(result([]))
    assert (verdict.rules_version, verdict.rules_count) == ("1", 20)


def test_green_without_powerful_capability() -> None:
    """Network and file reads alone stay green; the network part is described"""

    verdict = compute_verdict(result([finding(Capability.NETWORK), finding(Capability.FS_READ)]))
    assert verdict.color is VerdictColor.GREEN
    assert verdict.reasons == ["no_alert", "green.network_partly"]


def test_green_lists_the_fixed_addresses_contacted() -> None:
    """A green verdict with network calls to fixed hosts lists those domains"""

    network = finding(Capability.NETWORK).model_copy(update={"url_host": "api.example.com"})
    verdict = compute_verdict(result([network]))
    assert verdict.color is VerdictColor.GREEN
    assert verdict.reasons == ["no_alert", "green.network"]
    assert verdict.contacted_domains == ["api.example.com"]


def test_gray_when_a_tool_is_not_fully_followed() -> None:
    """Green requires everything to be read and followed: a tracking gap gives gray"""

    gapped = result([])
    gapped.servers[0].tools[0].gaps = [TrackingGap.DICT_CALL]
    verdict = compute_verdict(gapped)
    assert verdict.color is VerdictColor.GRAY
    assert verdict.reasons == ["caveat.incomplete_tracking"]


def test_orange_wins_over_gray() -> None:
    """A rule that fires decides the color even when the reading is incomplete"""

    gapped = result([finding(Capability.FS_WRITE)])
    gapped.servers[0].tools[0].gaps = [TrackingGap.DICT_CALL]
    verdict = compute_verdict(gapped)
    assert verdict.color is VerdictColor.ORANGE
    assert "caveat.incomplete_tracking" in verdict.reasons


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
    """Any status other than ok gives gray when no rule fires"""

    verdict = compute_verdict(result([], status))
    assert verdict.color is VerdictColor.GRAY
    assert verdict.reasons == [f"status.{status.value}"]


def test_gray_when_nothing_was_analyzed() -> None:
    """A server with no analyzed file gives gray"""

    empty = result([])
    empty.servers[0].files_analyzed = 0
    assert compute_verdict(empty).reasons == ["nothing_analyzable"]


def test_red_rule_wins_and_red_alerts_come_first() -> None:
    """A red alert makes the verdict red, and red alerts are listed before orange ones"""

    registry = RuleRegistry()
    registry.register(PowerfulCapability())
    registry.register(RedRule())
    verdict = compute_verdict(result([finding(Capability.FS_WRITE)]), registry)
    assert verdict.color is VerdictColor.RED
    assert [alert.rule for alert in verdict.alerts] == ["T01", "O08"]


def test_duplicate_rule_is_refused() -> None:
    """Two rules cannot share an identifier"""

    registry = RuleRegistry()
    registry.register(RedRule())
    with pytest.raises(ValueError):
        registry.register(RedRule())
