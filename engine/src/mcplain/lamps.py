"""Lamps: the only table that says which capabilities light each of the six lamps and which red rules turn it red"""

from dataclasses import dataclass
from enum import StrEnum

from mcplain.capabilities import Capability


class LampId(StrEnum):
    """Class that lists the six lamps, with identifiers that never change"""

    FILES_READ = "files_read"
    FILES_WRITE = "files_write"
    INTERNET = "internet"
    COMMANDS = "commands"
    SECRETS = "secrets"
    HIDDEN_TEXT = "hidden_text"


class LampState(StrEnum):
    """Class that lists the states of a lamp: off, on (white, for information) or danger (red)"""

    OFF = "off"
    ON = "on"
    DANGER = "danger"


class ToolLevel(StrEnum):
    """Class that lists the level of a tool, from the rules attached to it"""

    NONE = "none"
    WARN = "warn"
    DANGER = "danger"


@dataclass(frozen=True)
class LampSpec:
    """Class that describes one lamp: what lights it, and which red rules turn it red"""

    lamp: LampId
    capabilities: frozenset[Capability]
    red_rules: frozenset[str]
    lit_by_invisible_characters: bool = False


LAMPS: tuple[LampSpec, ...] = (
    LampSpec(LampId.FILES_READ, frozenset({Capability.FS_READ}), frozenset()),
    LampSpec(LampId.FILES_WRITE, frozenset({Capability.FS_WRITE}), frozenset({"R08"})),
    LampSpec(LampId.INTERNET, frozenset({Capability.NETWORK}), frozenset({"R04", "R05", "R07", "R10"})),
    LampSpec(
        LampId.COMMANDS,
        frozenset({Capability.PROCESS_EXEC, Capability.DYNAMIC_CODE, Capability.INSTALL_SCRIPT}),
        frozenset({"R07", "R09", "R10"}),
    ),
    LampSpec(
        LampId.SECRETS,
        frozenset({Capability.ENV_READ_SECRET, Capability.SENSITIVE_PATH}),
        frozenset({"R03", "R04"}),
    ),
    LampSpec(LampId.HIDDEN_TEXT, frozenset(), frozenset({"R01", "R02", "R06", "R12"}), lit_by_invisible_characters=True),
)

LAMP_ORDER: tuple[LampId, ...] = tuple(spec.lamp for spec in LAMPS)


def lamp_states(
    capabilities: set[Capability],
    red_rules: set[str],
    invisible_characters: bool,
) -> list[tuple[LampId, LampState, list[str]]]:
    """Return each lamp in table order with its state and the red rules that turned it red"""

    states = []
    for spec in LAMPS:
        state = LampState.OFF
        if spec.capabilities & capabilities or (spec.lit_by_invisible_characters and invisible_characters):
            state = LampState.ON
        rules = sorted(spec.red_rules & red_rules)
        if rules:
            state = LampState.DANGER
        states.append((spec.lamp, state, rules))
    return states


def lamps_for_rule(rule: str) -> list[LampId]:
    """Return the lamps that a red rule turns red, in table order"""

    return [spec.lamp for spec in LAMPS if rule in spec.red_rules]


def level_for(red: bool, orange: bool) -> ToolLevel:
    """Return the level of a tool from the colors of the rules attached to it"""

    if red:
        return ToolLevel.DANGER
    if orange:
        return ToolLevel.WARN
    return ToolLevel.NONE
