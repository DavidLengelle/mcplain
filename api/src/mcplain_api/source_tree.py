"""Fingerprint of the Python code built into an image, comparable with a git commit without git in the image"""

import hashlib
import sys
from pathlib import Path

SOURCE_FOLDERS: tuple[str, ...] = ("api/src", "engine/src")
SKIPPED_PARTS: frozenset[str] = frozenset({"__pycache__"})


def blob_sha1(content: bytes) -> str:
    """Return the identifier git gives to a file content"""

    return hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()


def digest(entries: dict[str, str]) -> str:
    """Return one fingerprint for a list of paths and their git identifiers"""

    lines = "".join(f"{entries[path]} {path}\n" for path in sorted(entries))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def folder_entries(root: Path) -> dict[str, str]:
    """Return the git identifier of every file of the source folders below root"""

    entries: dict[str, str] = {}
    for folder in SOURCE_FOLDERS:
        for path in (root / folder).rglob("*"):
            if path.is_file() and not SKIPPED_PARTS & set(path.parts):
                entries[path.relative_to(root).as_posix()] = blob_sha1(path.read_bytes())
    return entries


def main() -> int:
    """Print the fingerprint of the source folders below the folder given as argument"""

    print(digest(folder_entries(Path(sys.argv[1]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
