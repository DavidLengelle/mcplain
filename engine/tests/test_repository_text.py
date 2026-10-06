"""Guards on the files tracked by git: no raw invisible character, no agent instruction file outside the root"""

from pathlib import Path, PurePosixPath

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
EXCLUDED_PREFIXES: tuple[str, ...] = ("engine/tests/fixtures/",)
INVISIBLE_RANGES: tuple[tuple[int, int], ...] = (
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x2064),
    (0x2066, 0x2069),
    (0xFEFF, 0xFEFF),
    (0xE0000, 0xE007F),
)
AGENT_FILES: frozenset[str] = frozenset({"CLAUDE.md", "AGENTS.md"})
ALLOWED_AGENT_FILES: frozenset[str] = frozenset({"CLAUDE.md"})
INDEX_SIGNATURE = b"DIRC"
ENTRY_FIXED_BYTES = 40
FLAGS_BYTES = 2
EXTENDED_FLAG = 0x4000
REGULAR_FILE_TYPE = 0o100000
FILE_TYPE_MASK = 0o170000
SHA1_BYTES = 20
SHA256_BYTES = 32


def _git_dir(root: Path) -> Path | None:
    """Return the git folder of a working tree, following a .git file that points elsewhere"""

    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git
    if dot_git.is_file():
        text = dot_git.read_text(encoding="utf-8").strip()
        if text.startswith("gitdir:"):
            return (root / text.removeprefix("gitdir:").strip()).resolve()
    return None


def _hash_bytes(git_dir: Path) -> int:
    """Return the size of an object name, 32 bytes in a SHA-256 repository"""

    config = git_dir / "config"
    if config.is_file() and "objectformat = sha256" in config.read_text(encoding="utf-8").lower():
        return SHA256_BYTES
    return SHA1_BYTES


def _varint(data: bytes, position: int) -> tuple[int, int]:
    """Read the variable-length number used by index version 4"""

    byte = data[position]
    position += 1
    value = byte & 0x7F
    while byte & 0x80:
        byte = data[position]
        position += 1
        value = ((value + 1) << 7) | (byte & 0x7F)
    return value, position


def parse_index(data: bytes, hash_bytes: int = SHA1_BYTES) -> list[str]:
    """Return the regular files listed in a git index, versions 2, 3 and 4"""

    if data[:4] != INDEX_SIGNATURE:
        raise ValueError("not a git index")
    version = int.from_bytes(data[4:8], "big")
    count = int.from_bytes(data[8:12], "big")
    position = 12
    previous = b""
    paths: list[str] = []
    for _ in range(count):
        start = position
        mode = int.from_bytes(data[start + 24 : start + 28], "big")
        position = start + ENTRY_FIXED_BYTES + hash_bytes
        flags = int.from_bytes(data[position : position + FLAGS_BYTES], "big")
        position += FLAGS_BYTES
        if version >= 3 and flags & EXTENDED_FLAG:
            position += FLAGS_BYTES
        if version >= 4:
            removed, position = _varint(data, position)
            end = data.index(b"\x00", position)
            name = previous[: len(previous) - removed] + data[position:end]
            position = end + 1
        else:
            end = data.index(b"\x00", position)
            name = data[position:end]
            position = start + ((end - start) // 8 + 1) * 8
        previous = name
        if mode & FILE_TYPE_MASK == REGULAR_FILE_TYPE:
            paths.append(name.decode("utf-8", errors="replace"))
    return list(dict.fromkeys(paths))


def tracked_files(root: Path) -> list[str] | None:
    """Return the files tracked by git in a working tree, or None outside a git working tree"""

    git_dir = _git_dir(root)
    if git_dir is None or not (git_dir / "index").is_file():
        return None
    return parse_index((git_dir / "index").read_bytes(), _hash_bytes(git_dir))


def is_invisible(character: str) -> bool:
    """Tell whether a character is one of the invisible characters that must never be written raw"""

    codepoint = ord(character)
    return any(low <= codepoint <= high for low, high in INVISIBLE_RANGES)


def invisible_characters(text: str) -> list[tuple[int, str]]:
    """Return the line number and the code (U+202E) of every raw invisible character of a text"""

    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for character in line:
            if is_invisible(character):
                found.append((number, f"U+{ord(character):04X}"))
    return found


def _text(path: Path) -> str | None:
    """Return the content of a text file, or None for a binary or missing file"""

    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _tracked_or_skip() -> list[str]:
    """Return the tracked files of this repository, or skip outside a git working tree"""

    files = tracked_files(REPOSITORY)
    if files is None:
        pytest.skip("not a git working tree")
    return files


def test_invisible_characters_are_reported_by_code_only() -> None:
    """A raw invisible character is reported with its line and its code, never as itself"""

    text = "plain\nab" + chr(0x202E) + "c\n" + chr(0xE0041) + chr(0xFEFF) + "\nno" + chr(0x2065)
    assert invisible_characters(text) == [(2, "U+202E"), (3, "U+E0041"), (3, "U+FEFF")]
    assert invisible_characters("\\u202e and \\U000e0041 are escapes") == []
    assert all(is_invisible(chr(low)) and is_invisible(chr(high)) for low, high in INVISIBLE_RANGES)


def test_parse_index_reads_versions_2_and_4() -> None:
    """The index reader finds the same paths in the padded and in the prefix-compressed formats"""

    def entry(name: bytes, mode: int) -> bytes:
        """Build the fixed part of one index entry"""

        fields = bytes(24) + mode.to_bytes(4, "big") + bytes(12) + bytes(SHA1_BYTES)
        return fields + len(name).to_bytes(FLAGS_BYTES, "big")

    names = [b"a/one.py", b"a/two.py", b"link"]
    modes = [0o100644, 0o100755, 0o120000]
    version_2 = bytearray(INDEX_SIGNATURE + (2).to_bytes(4, "big") + (3).to_bytes(4, "big"))
    for name, mode in zip(names, modes, strict=True):
        record = entry(name, mode) + name + b"\x00"
        version_2 += record + bytes((8 - len(record) % 8) % 8)
    version_4 = bytearray(INDEX_SIGNATURE + (4).to_bytes(4, "big") + (3).to_bytes(4, "big"))
    version_4 += entry(names[0], modes[0]) + bytes([0]) + names[0] + b"\x00"
    version_4 += entry(names[1], modes[1]) + bytes([6]) + b"two.py\x00"
    version_4 += entry(names[2], modes[2]) + bytes([8]) + b"link\x00"
    assert parse_index(bytes(version_2)) == ["a/one.py", "a/two.py"]
    assert parse_index(bytes(version_4)) == ["a/one.py", "a/two.py"]


def test_no_raw_invisible_character_in_tracked_files() -> None:
    """Tracked text files write invisible characters as escapes; only the analyzed fixtures may hold them raw"""

    files = _tracked_or_skip()
    problems = []
    for name in files:
        if name.startswith(EXCLUDED_PREFIXES):
            continue
        text = _text(REPOSITORY / name)
        if text is None:
            continue
        problems.extend(f"{name}:{line}: {code}" for line, code in invisible_characters(text))
    assert files
    assert problems == []


def test_no_agent_instruction_file_outside_the_root() -> None:
    """Only the root CLAUDE.md is tracked; files like web/AGENTS.md come from third-party tools"""

    files = _tracked_or_skip()
    found = [name for name in files if PurePosixPath(name).name in AGENT_FILES and name not in ALLOWED_AGENT_FILES]
    assert found == []
