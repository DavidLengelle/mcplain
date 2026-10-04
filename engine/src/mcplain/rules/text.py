"""Texts the AI reads (tool names, titles, descriptions, parameter descriptions) and the invisible characters in them"""

from dataclasses import dataclass

from mcplain.adapters.common import hidden_tag_text
from mcplain.models import Tool

TAG_FIRST = 0xE0000
TAG_LAST = 0xE007F
TAG_CANCEL = 0xE007F
TAG_PRINTABLE = range(0xE0020, 0xE007F)
BLACK_FLAG = 0x1F3F4
VARIATION_FIRST = 0xE0100
VARIATION_LAST = 0xE01EF
OPERATOR_FIRST = 0x2061
OPERATOR_LAST = 0x2064
ZERO_WIDTH: frozenset[int] = frozenset({0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF})
JOINERS: frozenset[int] = frozenset({0x200C, 0x200D})
ZERO_WIDTH_JOINER = 0x200D
BYTE_ORDER_MARK = 0xFEFF
BIDI_CONTROLS: frozenset[int] = frozenset(range(0x202A, 0x202F)) | frozenset(range(0x2066, 0x206A))
EMOJI_RANGES: tuple[tuple[int, int], ...] = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2300, 0x23FF),
    (0x2B00, 0x2BFF),
    (0x2190, 0x21FF),
    (0xFE0F, 0xFE0F),
    (0x1F3FB, 0x1F3FF),
)
JOINING_SCRIPT_RANGES: tuple[tuple[int, int], ...] = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFE),
    (0x0900, 0x0DFF),
)


@dataclass(frozen=True)
class ToolText:
    """Class that holds one text of a tool that the AI reads"""

    tool: Tool
    field: str
    text: str
    parameter: str | None = None


@dataclass(frozen=True)
class HiddenCharacters:
    """Class that holds a run of invisible characters: what it is, where it starts, and the text it hides"""

    kind: str
    index: int
    hidden: str | None = None


def tool_texts(tool: Tool) -> list[ToolText]:
    """Return the name, title, description and parameter descriptions of a tool"""

    texts = [ToolText(tool, "name", tool.name), ToolText(tool, "description", tool.description)]
    if tool.title:
        texts.append(ToolText(tool, "title", tool.title))
    for parameter in tool.parameters:
        if parameter.description:
            texts.append(ToolText(tool, "parameter", parameter.description, parameter.name))
    return texts


def _in(ranges: tuple[tuple[int, int], ...], character: str) -> bool:
    """Tell whether a character falls in one of the ranges"""

    codepoint = ord(character)
    return any(low <= codepoint <= high for low, high in ranges)


def _justified(text: str, index: int) -> bool:
    """Tell whether a single zero-width character is normal where it stands"""

    codepoint = ord(text[index])
    before = text[index - 1 : index]
    after = text[index + 1 : index + 2]
    if codepoint == BYTE_ORDER_MARK and index == 0:
        return True
    if codepoint == ZERO_WIDTH_JOINER and before and after and _in(EMOJI_RANGES, before) and _in(EMOJI_RANGES, after):
        return True
    if codepoint in JOINERS and before and after:
        return _in(JOINING_SCRIPT_RANGES, before) and _in(JOINING_SCRIPT_RANGES, after)
    return False


def _valid_flag(text: str, start: int, end: int) -> bool:
    """Tell whether a run of tag characters is a flag sequence like the Scottish flag"""

    run = text[start:end]
    if start == 0 or ord(text[start - 1]) != BLACK_FLAG or len(run) < 2 or ord(run[-1]) != TAG_CANCEL:
        return False
    return all(ord(character) in TAG_PRINTABLE for character in run[:-1])


def hidden_characters(text: str) -> tuple[list[HiddenCharacters], list[HiddenCharacters]]:
    """Return the invisible runs that hide text (red), and the lone ones that context does not explain (orange)"""

    red: list[HiddenCharacters] = []
    lone: list[HiddenCharacters] = []
    index = 0
    while index < len(text):
        codepoint = ord(text[index])
        end = index + 1
        if TAG_FIRST <= codepoint <= TAG_LAST:
            while end < len(text) and TAG_FIRST <= ord(text[end]) <= TAG_LAST:
                end += 1
            if not _valid_flag(text, index, end):
                red.append(HiddenCharacters("tag", index, hidden_tag_text(text[index:end])))
        elif VARIATION_FIRST <= codepoint <= VARIATION_LAST:
            while end < len(text) and VARIATION_FIRST <= ord(text[end]) <= VARIATION_LAST:
                end += 1
            red.append(HiddenCharacters("variation_selector", index))
        elif OPERATOR_FIRST <= codepoint <= OPERATOR_LAST:
            red.append(HiddenCharacters("invisible_operator", index))
        elif codepoint in BIDI_CONTROLS:
            red.append(HiddenCharacters("bidi_control", index))
        elif codepoint in ZERO_WIDTH:
            while end < len(text) and ord(text[end]) in ZERO_WIDTH:
                end += 1
            if end - index >= 2:
                red.append(HiddenCharacters("zero_width_run", index))
            elif not _justified(text, index):
                lone.append(HiddenCharacters("lone_zero_width", index))
        index = end
    return red, lone
