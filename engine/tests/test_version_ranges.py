"""Tests for declared version ranges: a range excludes a version only when it surely does"""

import pytest

from mcplain.dependencies import npm_dependency_ranges, requirement_ranges
from mcplain.version_ranges import npm_range_excludes, pypi_range_excludes, range_excludes


@pytest.mark.parametrize(
    ("declared", "version", "excluded"),
    [
        ("^5.3.0", "5.6.1", False),
        ("^5.3.0", "6.0.0", True),
        ("^5.3.0", "5.2.9", True),
        ("^0.2.3", "0.3.0", True),
        ("^0.0.3", "0.0.4", True),
        ("~1.2.3", "1.3.0", True),
        ("~1.2.3", "1.2.9", False),
        ("1.x", "2.0.0", True),
        ("1.x", "1.9.9", False),
        ("5.6.1", "5.6.1", False),
        ("5.6.0", "5.6.1", True),
        (">=1.2.3 <2", "2.0.0", True),
        (">= 1.2.3 < 2", "1.5.0", False),
        ("1.2.3 - 2.3", "2.3.9", False),
        ("1.2.3 - 2.3", "2.4.0", True),
        ("^1.0.0 || ^3.0.0", "2.0.0", True),
        ("^1.0.0 || ^3.0.0", "3.1.0", False),
        (">1.2", "1.2.9", True),
        (">1.2", "1.3.0", False),
        ("<=1.2", "1.3.0", True),
        ("*", "9.9.9", False),
        ("latest", "1.0.0", False),
        ("npm:other@1", "9.0.0", False),
        ("^1.0.0", "not-a-version", False),
    ],
)
def test_npm_ranges(declared: str, version: str, excluded: bool) -> None:
    """Caret, tilde, x, hyphen and || ranges; tags, aliases and odd versions never exclude"""

    assert npm_range_excludes(declared, version) is excluded


@pytest.mark.parametrize(
    ("declared", "version", "excluded"),
    [
        (">=2.0", "1.9", True),
        (">=2.0", "2.0.1", False),
        (">= 1.10.0", "1.9", True),
        ("~=1.4.2", "1.4.9", False),
        ("~=1.4.2", "1.5.0", True),
        ("~=1.4", "2.0", True),
        ("==1.2.*", "1.3.0", True),
        ("==1.2.*", "1.2.7", False),
        ("!=1.2.3", "1.2.3", True),
        (">=1,<2", "2.0", True),
        ("", "3.0", False),
        (">=1.0a1", "5", False),
        ("<2", "1.0rc1", False),
    ],
)
def test_pypi_specifiers(declared: str, version: str, excluded: bool) -> None:
    """PEP 440 specifiers on final releases; prereleases and odd specifiers never exclude"""

    assert pypi_range_excludes(declared, version) is excluded


def test_an_unknown_ecosystem_or_range_never_excludes() -> None:
    """In doubt, the version stays possible"""

    assert range_excludes("crates.io", "^1", "2.0.0") is False
    assert range_excludes("npm", None, "2.0.0") is False


def test_declared_ranges_are_read_from_metadata() -> None:
    """npm dependencies and PEP 508 requirements, without extras and URL requirements"""

    assert npm_dependency_ranges({"dependencies": {"colorful-strings": "^5.3.0", "odd": 3}}) == {
        "colorful-strings": "^5.3.0"
    }
    requirements = [
        "httpx>=0.27,<1",
        "Tidy_Helpers[cli] >= 1.10.0",
        "old (>=1.0)",
        "bare",
        "pinned @ https://example.invalid/pinned.whl",
        "marked>=2; python_version<'3.13'",
        "tests ; extra == 'dev'",
    ]
    assert requirement_ranges(requirements) == {
        "httpx": ">=0.27,<1",
        "tidy-helpers": ">= 1.10.0",
        "old": ">=1.0",
        "bare": "",
        "marked": ">=2",
    }
