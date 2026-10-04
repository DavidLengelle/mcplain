"""Walking source trees and classifying files by their role"""

import os
import re
from collections.abc import Iterator
from fnmatch import fnmatchcase
from pathlib import Path

from mcplain.models import LocationKind

IGNORED_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        "bower_components",
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".next",
        ".turbo",
        ".cache",
    }
)
TEST_DIRS: frozenset[str] = frozenset(
    {"tests", "test", "__tests__", "__mocks__", "examples", "example", "docs", "doc", "e2e", "spec"}
)
TEST_FILE_PATTERNS: tuple[str, ...] = ("test_*.py", "*_test.py", "conftest.py", "*.test.*", "*.spec.*")
BUILD_DIRS: frozenset[str] = frozenset({"scripts", "script", "tools", ".github", ".husky"})
BUILD_NAME_PATTERN = re.compile(
    r"build|release|publish|deploy|bump|changelog|version|bundle|compile|lint|format|codegen|generate",
    re.IGNORECASE,
)
BUILD_FILE_PATTERNS: tuple[str, ...] = (
    "webpack.config.*",
    "rollup.config.*",
    "vite.config.*",
    "vitest.config.*",
    "jest.config.*",
    "esbuild.*",
    "tsup.config.*",
    "gulpfile.*",
    "Gruntfile.*",
    "babel.config.*",
    "eslint.config.*",
    ".eslintrc.*",
    "prettier.config.*",
    ".prettierrc.*",
    "noxfile.py",
    "fabfile.py",
    "hatch_build.py",
)


def iter_files(root: Path) -> Iterator[Path]:
    """Yield regular files below root in a stable order, skipping ignored folders and links"""

    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if name not in IGNORED_DIRS and not os.path.islink(os.path.join(current, name))
        )
        for name in sorted(files):
            path = Path(current, name)
            if path.is_symlink() or not path.is_file():
                continue
            yield path


def location_kind(relative_path: str) -> LocationKind:
    """Tell whether a file is server code, a test or example, or a build script"""

    parts = relative_path.split("/")
    name = parts[-1]
    folders = [part.lower() for part in parts[:-1]]
    if any(folder in TEST_DIRS for folder in folders):
        return LocationKind.TEST_OR_EXAMPLE
    if any(fnmatchcase(name, pattern) for pattern in TEST_FILE_PATTERNS):
        return LocationKind.TEST_OR_EXAMPLE
    if folders and folders[0] == ".github":
        return LocationKind.BUILD_SCRIPT
    if any(fnmatchcase(name, pattern) for pattern in BUILD_FILE_PATTERNS):
        return LocationKind.BUILD_SCRIPT
    if any(folder in BUILD_DIRS for folder in folders) and BUILD_NAME_PATTERN.search(name):
        return LocationKind.BUILD_SCRIPT
    return LocationKind.SERVER_CODE


def is_test_folder(relative_path: str) -> bool:
    """Tell whether a folder path sits inside a test, example or docs folder"""

    return any(part.lower() in TEST_DIRS for part in relative_path.split("/") if part)
