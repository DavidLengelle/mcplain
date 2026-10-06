"""Tests for the lamps: the table, the states of the server and of each tool, the tool levels and the fixed domains"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from mcplain.analyze import analyze_directory
from mcplain.capabilities import Capability
from mcplain.lamps import LAMP_ORDER, LAMPS, LampId, LampState, ToolLevel, lamp_states, lamps_for_rule, level_for
from mcplain.models import (
    AnalysisResult,
    AnalysisStatus,
    Finding,
    Lamp,
    LocationKind,
    Reputation,
    ServerAnalysis,
    Tool,
    UrlKind,
    Verdict,
    VerdictColor,
)
from mcplain.verdict import DEFAULT_REGISTRY, apply_verdict, has_lamps, internet_domains

REPUTATION_FILE = "reputation.json"
RED_RULE_LAMPS: dict[str, set[LampId]] = {
    "R01": {LampId.HIDDEN_TEXT},
    "R02": {LampId.HIDDEN_TEXT},
    "R03": {LampId.SECRETS},
    "R04": {LampId.SECRETS, LampId.INTERNET},
    "R05": {LampId.INTERNET},
    "R06": {LampId.HIDDEN_TEXT},
    "R07": {LampId.COMMANDS, LampId.INTERNET},
    "R08": {LampId.FILES_WRITE},
    "R09": {LampId.COMMANDS},
    "R10": {LampId.COMMANDS, LampId.INTERNET},
    "R11": set(),
    "R12": {LampId.HIDDEN_TEXT},
}


def analyze_fixture(folder: Path) -> AnalysisResult:
    """Analyze a fixture, with the OSV reputation it ships as data when there is one"""

    reputation = None
    if (folder / REPUTATION_FILE).is_file():
        reputation = Reputation.model_validate_json((folder / REPUTATION_FILE).read_text(encoding="utf-8"))
    return analyze_directory(folder, reputation=reputation)


def states(lamps: list[Lamp]) -> dict[LampId, LampState]:
    """Map each lamp to its state"""

    return {lamp.id: lamp.state for lamp in lamps}


def finding(capability: Capability, host: str | None = None, location: LocationKind = LocationKind.SERVER_CODE) -> Finding:
    """Build a finding of one capability in server code"""

    url_kind = None
    if capability is Capability.NETWORK:
        url_kind = UrlKind.LITERAL
    return Finding(
        capability=capability,
        file="server.py",
        line=1,
        column=0,
        snippet="call()",
        location_kind=location,
        url_kind=url_kind,
        url_host=host,
    )


def tool(name: str, findings: list[Finding]) -> Tool:
    """Build a tool of server code with some findings"""

    return Tool(
        name=name,
        description="Does one thing",
        description_is_dynamic=False,
        file="server.py",
        line=1,
        declaration="decorator",
        location_kind=LocationKind.SERVER_CODE,
        findings=findings,
    )


def result_with(tools: list[Tool], findings: list[Finding] | None = None) -> AnalysisResult:
    """Build a result of one server, then compute its verdict and lamps"""

    server = ServerAnalysis(path=".", language="python", tools=tools, findings=findings or [], files_analyzed=1)
    result = AnalysisResult(status=AnalysisStatus.OK, servers=[server], verdict=Verdict(color=VerdictColor.GRAY))
    return apply_verdict(result)


def test_the_table_holds_the_six_lamps_once_in_order() -> None:
    """The six lamps keep stable identifiers, and only red rules can turn a lamp red"""

    assert LAMP_ORDER == (
        LampId.FILES_READ,
        LampId.FILES_WRITE,
        LampId.INTERNET,
        LampId.COMMANDS,
        LampId.SECRETS,
        LampId.HIDDEN_TEXT,
    )
    red = {rule.identifier for rule in DEFAULT_REGISTRY.rules() if rule.color is VerdictColor.RED}
    assert all(spec.red_rules <= red for spec in LAMPS)
    for rule, lamps in RED_RULE_LAMPS.items():
        assert set(lamps_for_rule(rule)) == lamps, rule


def test_capabilities_light_their_lamps_and_env_read_lights_nothing() -> None:
    """Each capability lights the lamp of the table; a plain environment read lights nothing"""

    expected = {
        Capability.FS_READ: LampId.FILES_READ,
        Capability.FS_WRITE: LampId.FILES_WRITE,
        Capability.NETWORK: LampId.INTERNET,
        Capability.PROCESS_EXEC: LampId.COMMANDS,
        Capability.DYNAMIC_CODE: LampId.COMMANDS,
        Capability.INSTALL_SCRIPT: LampId.COMMANDS,
        Capability.ENV_READ_SECRET: LampId.SECRETS,
        Capability.SENSITIVE_PATH: LampId.SECRETS,
    }
    for capability, lamp in expected.items():
        lit = {item for item, state, _ in lamp_states({capability}, set(), False) if state is not LampState.OFF}
        assert lit == {lamp}, capability
    assert all(state is LampState.OFF for _, state, _ in lamp_states({Capability.ENV_READ}, set(), False))
    hidden = {lamp: state for lamp, state, _ in lamp_states(set(), set(), True)}
    assert hidden[LampId.HIDDEN_TEXT] is LampState.ON


@pytest.mark.parametrize("rule", sorted(RED_RULE_LAMPS))
def test_each_red_rule_turns_its_lamps_red(fixtures: Path, rule: str) -> None:
    """The positive fixture of each red rule turns exactly the lamps of that rule red, and never another one"""

    result = analyze_fixture(fixtures / "rules" / rule / "positive")
    fired = {alert.rule for alert in result.verdict.alerts if alert.color is VerdictColor.RED}
    assert rule in fired
    expected: set[LampId] = set()
    for name in fired:
        expected |= RED_RULE_LAMPS[name]
    for server in result.servers:
        danger = {lamp for lamp, state in states(server.lamps).items() if state is LampState.DANGER}
        assert danger == expected
        assert RED_RULE_LAMPS[rule] <= danger
        for lamp in server.lamps:
            if lamp.id in RED_RULE_LAMPS[rule]:
                assert rule in lamp.rules
            if lamp.state is not LampState.DANGER:
                assert lamp.rules == []


def test_orange_rules_never_turn_a_lamp_red(fixtures: Path) -> None:
    """A report with orange alerts only has no lamp in danger, on the server or on any tool"""

    for rule in ("O01", "O02", "O04", "O05", "O07", "O08"):
        result = analyze_fixture(fixtures / "rules" / rule / "positive")
        assert result.verdict.color is VerdictColor.ORANGE
        for server in result.servers:
            lamps = server.lamps + [lamp for item in server.tools for lamp in item.lamps]
            assert all(lamp.state is not LampState.DANGER for lamp in lamps), rule
        assert lamps_for_rule(rule) == []


def test_a_filesystem_report_reads_and_writes_without_danger(fixtures: Path) -> None:
    """A server that reads and writes notes lights the two file lamps, nothing else, and nothing in danger"""

    result = analyze_fixture(fixtures / "python_filesystem")
    assert result.verdict.color is VerdictColor.ORANGE
    lamps = states(result.servers[0].lamps)
    assert lamps[LampId.FILES_READ] is LampState.ON
    assert lamps[LampId.FILES_WRITE] is LampState.ON
    assert [lamp for lamp, state in lamps.items() if state is not LampState.OFF] == [LampId.FILES_READ, LampId.FILES_WRITE]
    levels = {item.name: item.level for item in result.servers[0].tools}
    assert levels == {"read_note": ToolLevel.NONE, "write_note": ToolLevel.WARN, "count_words": ToolLevel.NONE}


def test_a_tool_without_findings_has_six_lamps_off_and_no_level(fixtures: Path) -> None:
    """A tool whose code reaches nothing has its six lamps off and level none"""

    result = analyze_fixture(fixtures / "python_filesystem")
    counter = next(item for item in result.servers[0].tools if item.name == "count_words")
    assert [lamp.id for lamp in counter.lamps] == list(LAMP_ORDER)
    assert all(lamp.state is LampState.OFF for lamp in counter.lamps)
    assert counter.level is ToolLevel.NONE


def test_a_red_alert_gives_its_tool_the_danger_level(fixtures: Path) -> None:
    """The tool that holds the hidden copy is in danger, and its internet lamp is red"""

    result = analyze_fixture(fixtures / "postmark_like")
    attached = {alert.tool for alert in result.verdict.alerts if alert.color is VerdictColor.RED}
    for item in result.servers[0].tools:
        if item.name in attached:
            assert item.level is ToolLevel.DANGER
            assert states(item.lamps)[LampId.INTERNET] is LampState.DANGER
        else:
            assert item.level is not ToolLevel.DANGER


def test_levels_follow_the_worst_attached_rule() -> None:
    """A red rule gives danger, an orange one warn, none gives none"""

    assert level_for(True, True) is ToolLevel.DANGER
    assert level_for(False, True) is ToolLevel.WARN
    assert level_for(False, False) is ToolLevel.NONE


def test_tests_and_examples_light_no_lamp() -> None:
    """Findings outside server code count neither for the verdict nor for the lamps"""

    result = result_with([tool("run", [finding(Capability.PROCESS_EXEC, location=LocationKind.TEST_OR_EXAMPLE)])])
    assert all(lamp.state is LampState.OFF for lamp in result.servers[0].lamps)
    assert all(lamp.state is LampState.OFF for lamp in result.servers[0].tools[0].lamps)


def test_internet_domains_only_when_every_call_has_a_fixed_host() -> None:
    """Fixed hosts give the sorted list; a call without a fixed host, or no network at all, gives None"""

    fixed = result_with([tool("weather", [finding(Capability.NETWORK, "api.example.com")])])
    assert fixed.servers[0].internet_domains == ["api.example.com"]
    assert fixed.verdict.color is VerdictColor.GREEN
    mixed = result_with(
        [tool("fetch", [finding(Capability.NETWORK, "b.example.com"), finding(Capability.NETWORK, None)])],
        [finding(Capability.NETWORK, "a.example.com")],
    )
    assert internet_domains(mixed.servers[0]) is None
    offline = result_with([tool("add", [])])
    assert offline.servers[0].internet_domains is None


def test_every_server_and_tool_carries_its_lamps(fixtures: Path) -> None:
    """After the verdict, the result carries the lamps everywhere; a result without lamps is incomplete"""

    result = analyze_fixture(fixtures / "python_filesystem")
    assert has_lamps(result)
    result.servers[0].tools[0].lamps = []
    assert not has_lamps(result)


def test_lamps_must_be_the_six_in_table_order() -> None:
    """The model refuses a missing, unknown, duplicated or misplaced lamp, and accepts no lamp at all"""

    good = [{"id": lamp.value, "state": "off"} for lamp in LAMP_ORDER]
    base = {"path": ".", "language": "python"}
    assert ServerAnalysis.model_validate({**base, "lamps": good}).lamps[0].id is LampId.FILES_READ
    assert ServerAnalysis.model_validate(base).lamps == []
    for lamps in (good[:5], list(reversed(good)), good[:5] + good[:1], good[:5] + [{"id": "camera", "state": "on"}]):
        with pytest.raises(ValidationError):
            ServerAnalysis.model_validate({**base, "lamps": lamps})
    with pytest.raises(ValidationError):
        ServerAnalysis.model_validate({**base, "lamps": [{**good[0], "state": "blinking"}, *good[1:]]})
