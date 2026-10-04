"""Text helpers shared by the language adapters"""

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from tree_sitter import Language, Node, Query, QueryCursor

from mcplain.config import Limits
from mcplain.models import InvisibleCategory

INVISIBLE_RANGES: tuple[tuple[int, int, InvisibleCategory], ...] = (
    (0x00AD, 0x00AD, InvisibleCategory.ZERO_WIDTH),
    (0x034F, 0x034F, InvisibleCategory.ZERO_WIDTH),
    (0x115F, 0x1160, InvisibleCategory.ZERO_WIDTH),
    (0x17B4, 0x17B5, InvisibleCategory.ZERO_WIDTH),
    (0x180E, 0x180E, InvisibleCategory.ZERO_WIDTH),
    (0x200B, 0x200D, InvisibleCategory.ZERO_WIDTH),
    (0x2060, 0x2064, InvisibleCategory.ZERO_WIDTH),
    (0x3164, 0x3164, InvisibleCategory.ZERO_WIDTH),
    (0xFEFF, 0xFEFF, InvisibleCategory.ZERO_WIDTH),
    (0xFFA0, 0xFFA0, InvisibleCategory.ZERO_WIDTH),
    (0x061C, 0x061C, InvisibleCategory.BIDI_CONTROL),
    (0x200E, 0x200F, InvisibleCategory.BIDI_CONTROL),
    (0x202A, 0x202E, InvisibleCategory.BIDI_CONTROL),
    (0x2066, 0x2069, InvisibleCategory.BIDI_CONTROL),
    (0xE0000, 0xE007F, InvisibleCategory.TAG),
    (0xE0100, 0xE01EF, InvisibleCategory.VARIATION_SELECTOR),
    (0x0000, 0x0008, InvisibleCategory.CONTROL),
    (0x000B, 0x000C, InvisibleCategory.CONTROL),
    (0x000E, 0x001F, InvisibleCategory.CONTROL),
    (0x007F, 0x009F, InvisibleCategory.CONTROL),
)
INVISIBLE_PATTERN = re.compile(
    "[" + "".join(f"\\U{low:08x}-\\U{high:08x}" for low, high, _ in INVISIBLE_RANGES) + "]+"
)
TAG_BASE = 0xE0000
PRINTABLE_ASCII = range(0x20, 0x7F)
URL_PATTERN = re.compile(r"https?://[^\s\"'<>`\\{}|^\x00-\x1f]+", re.IGNORECASE)
URL_TRAILING = ".,;:)]!?"
HOST_PATTERN = re.compile(r"^[a-z0-9.-]+$|^\[[0-9a-f:.]+\]$")
MAX_URL_LENGTH = 300
DYNAMIC_PLACEHOLDER = "{}"

_QUERIES: dict[tuple[int, tuple[str, ...]], Query] = {}


@dataclass
class Piece:
    """Class that maps a slice of a decoded string back to the source"""

    text: str
    start: int
    raw: bool


@dataclass
class TextValue:
    """Class that holds a statically known string and where it came from"""

    value: str = ""
    dynamic: bool = False
    pieces: list[Piece] = field(default_factory=list)
    ranges: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class InvisibleRun:
    """Class that holds a run of invisible characters of one category"""

    index: int
    category: InvisibleCategory
    characters: str


def dynamic_text() -> TextValue:
    """Return the value used for a string that cannot be known statically"""

    return TextValue(value="", dynamic=True)


def join_texts(parts: list[TextValue]) -> TextValue:
    """Concatenate several text values"""

    result = TextValue()
    for part in parts:
        result.value += part.value
        result.dynamic = result.dynamic or part.dynamic
        result.pieces.extend(part.pieces)
        result.ranges.extend(part.ranges)
    return result


def mark_dynamic(text: TextValue) -> TextValue:
    """Return the same text flagged as computed"""

    return TextValue(text.value, True, list(text.pieces), list(text.ranges))


def text_from_pieces(pieces: list[Piece], dynamic: bool, node: Node) -> TextValue:
    """Build a text value from decoded pieces of one literal node"""

    return TextValue(
        value="".join(piece.text for piece in pieces),
        dynamic=dynamic,
        pieces=pieces,
        ranges=[(node.start_byte, node.end_byte)],
    )


def source_offset(text: TextValue, index: int) -> int:
    """Return the source byte offset of one character of a decoded string"""

    position = 0
    for piece in text.pieces:
        if index < position + len(piece.text):
            if piece.raw:
                return piece.start + len(piece.text[: index - position].encode("utf-8"))
            return piece.start
        position += len(piece.text)
    if text.pieces:
        return text.pieces[-1].start
    return 0


def invisible_category(character: str) -> InvisibleCategory | None:
    """Return the invisible family of one character"""

    codepoint = ord(character)
    for low, high, category in INVISIBLE_RANGES:
        if low <= codepoint <= high:
            return category
    return None


def scan_invisible(value: str) -> list[InvisibleRun]:
    """Find runs of invisible characters, split by category"""

    runs: list[InvisibleRun] = []
    for match in INVISIBLE_PATTERN.finditer(value):
        start = match.start()
        current: InvisibleRun | None = None
        for offset, character in enumerate(match.group(0)):
            category = invisible_category(character)
            if category is None:
                continue
            if current is None or current.category is not category:
                current = InvisibleRun(start + offset, category, "")
                runs.append(current)
            current.characters += character
    return runs


def codepoint_label(character: str) -> str:
    """Return the U+XXXX label of a character"""

    return f"U+{ord(character):04X}"


def hidden_tag_text(characters: str) -> str | None:
    """Decode the ASCII text hidden in Unicode tag characters"""

    decoded = []
    for character in characters:
        value = ord(character) - TAG_BASE
        if value in PRINTABLE_ASCII:
            decoded.append(chr(value))
    if decoded:
        return "".join(decoded)
    return None


def extract_urls(value: str) -> list[tuple[str, str]]:
    """Return every literal http(s) URL in a string with its domain"""

    found = []
    for match in URL_PATTERN.finditer(value):
        url = match.group(0).rstrip(URL_TRAILING)
        try:
            host = urlsplit(url).hostname
        except ValueError:
            continue
        if not host or not HOST_PATTERN.match(host):
            continue
        found.append((url[:MAX_URL_LENGTH], host))
    return found


class SourceText:
    """Class that turns byte offsets into lines, columns and snippets"""

    def __init__(self, text: str, limits: Limits) -> None:
        """Encode the text once and index the line starts"""

        self.text = text
        self.data = text.encode("utf-8")
        self.limits = limits
        self._line_starts = [0] + [match.end() for match in re.finditer(b"\n", self.data)]

    def position(self, offset: int) -> tuple[int, int]:
        """Return the 1-based line and column of a byte offset"""

        index = bisect_right(self._line_starts, offset) - 1
        start = self._line_starts[index]
        column = len(self.data[start:offset].decode("utf-8", errors="replace")) + 1
        return index + 1, column

    def line_text(self, line: int) -> str:
        """Return the text of a 1-based line"""

        start = self._line_starts[line - 1]
        end = len(self.data)
        if line < len(self._line_starts):
            end = self._line_starts[line]
        return self.data[start:end].decode("utf-8", errors="replace").rstrip("\r\n")

    def snippet(self, offset: int) -> str:
        """Return the source line around an offset, cut to the snippet limit"""

        line, column = self.position(offset)
        text = self.line_text(line)
        limit = self.limits.max_snippet_chars
        stripped = text.strip()
        if len(stripped) <= limit:
            return stripped
        start = max(0, column - 1 - limit // 4)
        return text[start:start + limit]

    def is_minified(self, relative_path: str) -> bool:
        """Tell whether the file looks minified"""

        name = relative_path.rsplit("/", 1)[-1]
        if ".min." in name:
            return True
        longest = max((len(line) for line in self.text.splitlines()), default=0)
        return longest > self.limits.minified_line_length


def collect_nodes(language: Language, root: Node, types: tuple[str, ...]) -> dict[str, list[Node]]:
    """Collect every node of the given types, in source order"""

    key = (id(language), types)
    query = _QUERIES.get(key)
    if query is None:
        query = Query(language, " ".join(f"({name}) @{name}" for name in types))
        _QUERIES[key] = query
    captures = QueryCursor(query).captures(root)
    return {
        name: sorted(captures.get(name, []), key=lambda node: node.start_byte)
        for name in types
    }


def first_error(root: Node) -> Node | None:
    """Return the first syntax error node of a tree"""

    if not root.has_error:
        return None
    node = root
    while True:
        if node.is_error or node.is_missing:
            return node
        following = None
        for child in node.children:
            if child.has_error or child.is_missing:
                following = child
                break
        if following is None:
            return node
        node = following


def node_text(node: Node) -> str:
    """Return the source text of a node"""

    raw = node.text or b""
    return raw.decode("utf-8", errors="replace")


def contains(ranges: list[tuple[int, int]], offset: int) -> bool:
    """Tell whether an offset falls inside one of the ranges"""

    return any(start <= offset < end for start, end in ranges)
