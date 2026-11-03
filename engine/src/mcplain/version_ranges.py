"""Declared version ranges of dependencies, read as data; anything not understood counts as possibly inside"""

import re

NPM_ECOSYSTEM = "npm"
PYPI_ECOSYSTEM = "PyPI"
NPM_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")
NPM_PARTIAL = re.compile(r"^v?(\d+|[xX*])(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
NPM_COMPARATOR = re.compile(r"^(\^|~>?|>=|<=|>|<|=)?\s*(.+)$")
NPM_HYPHEN = re.compile(r"^(\S+)\s+-\s+(\S+)$")
PEP440_RELEASE = re.compile(r"^v?(\d+(?:\.\d+)*)$")
PEP440_SPECIFIER = re.compile(r"^(===|==|!=|~=|>=|<=|>|<)\s*(\S+)$")
WILDCARDS: frozenset[str] = frozenset({"x", "X", "*"})
ANY_RANGES: frozenset[str] = frozenset({"", "*", "x", "X"})

Version = tuple[int, ...]
Bound = tuple[str, Version]


def npm_version(text: str) -> tuple[Version, bool] | None:
    """Return the numbers of an exact npm version and whether it is a prerelease, or None"""

    match = NPM_VERSION.match(text.strip())
    if match is None:
        return None
    numbers = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return numbers, match.group(4) is not None


def _partial(text: str) -> list[int] | None:
    """Return the numbers given in a partial npm version like 1.2 or 1.x, or None"""

    match = NPM_PARTIAL.match(text)
    if match is None:
        return None
    numbers = []
    for part in match.groups():
        if part is None or part in WILDCARDS:
            break
        numbers.append(int(part))
    return numbers


def _next(numbers: list[int]) -> Version:
    """Return the first version above every version that starts with these numbers"""

    bumped = numbers[:-1] + [numbers[-1] + 1]
    return tuple(bumped + [0] * (3 - len(bumped)))


def _filled(numbers: list[int]) -> Version:
    """Complete partial numbers with zeros"""

    return tuple(numbers + [0] * (3 - len(numbers)))


def _caret(numbers: list[int]) -> list[Bound]:
    """Return the bounds of ^numbers"""

    if not numbers:
        return []
    lower = [(">=", _filled(numbers))]
    for index, number in enumerate(numbers):
        if number != 0 or index == len(numbers) - 1:
            return lower + [("<", _next(numbers[: index + 1]))]
    return lower


def _comparator(text: str) -> list[Bound] | None:
    """Return the bounds of one npm comparator, or None when it is not understood"""

    match = NPM_COMPARATOR.match(text)
    if match is None:
        return None
    operator = match.group(1) or ""
    numbers = _partial(match.group(2))
    if numbers is None:
        return None
    if operator == "^":
        return _caret(numbers)
    if operator.startswith("~"):
        if not numbers:
            return []
        kept = numbers[:2]
        if len(numbers) == 1:
            kept = numbers
        return [(">=", _filled(numbers)), ("<", _next(kept))]
    if operator in ("", "="):
        if not numbers:
            return []
        if len(numbers) == 3:
            return [("==", tuple(numbers))]
        return [(">=", _filled(numbers)), ("<", _next(numbers))]
    if not numbers:
        return None
    if len(numbers) < 3 and operator == ">":
        return [(">=", _next(numbers))]
    if len(numbers) < 3 and operator == "<=":
        return [("<", _next(numbers))]
    return [(operator, _filled(numbers))]


def _npm_set(text: str) -> list[Bound] | None:
    """Return the bounds of one comparator set, joined by spaces, or None"""

    hyphen = NPM_HYPHEN.match(text)
    if hyphen is not None:
        low = _comparator(">=" + hyphen.group(1))
        high = _partial(hyphen.group(2))
        if low is None or high is None:
            return None
        if len(high) == 3:
            return low + [("<=", tuple(high))]
        if not high:
            return low
        return low + [("<", _next(high))]
    bounds: list[Bound] = []
    tokens = re.sub(r"(\^|~>?|>=|<=|>|<|=)\s+", r"\1", text).split()
    for token in tokens:
        part = _comparator(token)
        if part is None:
            return None
        bounds.extend(part)
    return bounds


def _within(version: Version, bounds: list[Bound]) -> bool:
    """Tell whether a version meets every bound"""

    checks = {
        "==": version.__eq__,
        "!=": version.__ne__,
        ">=": version.__ge__,
        "<=": version.__le__,
        ">": version.__gt__,
        "<": version.__lt__,
    }
    return all(checks[operator](limit) for operator, limit in bounds)


def npm_range_excludes(declared: str, version: str) -> bool:
    """Tell whether an npm range surely leaves a version out; unknown ranges or versions never exclude"""

    parsed = npm_version(version)
    text = declared.strip()
    if parsed is None or text in ANY_RANGES:
        return False
    numbers, _ = parsed
    sets = [_npm_set(part.strip()) for part in text.split("||")]
    if any(bounds is None for bounds in sets):
        return False
    return not any(_within(numbers, bounds) for bounds in sets if bounds is not None)


def _release(text: str) -> Version | None:
    """Return the numbers of a final PEP 440 release, or None for anything else"""

    match = PEP440_RELEASE.match(text.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _padded(left: Version, right: Version) -> tuple[Version, Version]:
    """Give two releases the same length, as PEP 440 compares them"""

    size = max(len(left), len(right))
    return left + (0,) * (size - len(left)), right + (0,) * (size - len(right))


def _pep440_matches(operator: str, target: str, version: Version) -> bool | None:
    """Tell whether a release meets one specifier, or None when it is not understood"""

    if operator in ("==", "!=") and target.endswith(".*"):
        prefix = _release(target[:-2])
        if prefix is None:
            return None
        inside = version[: len(prefix)] == prefix
        return inside == (operator == "==")
    limit = _release(target)
    if limit is None or operator == "===":
        return None
    left, right = _padded(version, limit)
    if operator == "~=":
        if len(limit) < 2:
            return None
        prefix = limit[:-1]
        return left >= right and left[: len(prefix)] == prefix
    checks = {
        "==": left == right,
        "!=": left != right,
        ">=": left >= right,
        "<=": left <= right,
        ">": left > right,
        "<": left < right,
    }
    return checks[operator]


def pypi_range_excludes(declared: str, version: str) -> bool:
    """Tell whether PEP 440 specifiers surely leave a release out; anything not understood never excludes"""

    parsed = _release(version)
    text = declared.strip()
    if parsed is None or not text:
        return False
    for specifier in text.split(","):
        match = PEP440_SPECIFIER.match(specifier.strip())
        if match is None:
            return False
        answer = _pep440_matches(match.group(1), match.group(2), parsed)
        if answer is None:
            return False
        if not answer:
            return True
    return False


def range_excludes(ecosystem: str, declared: str | None, version: str) -> bool:
    """Tell whether the declared range of a dependency surely leaves a version out"""

    if declared is None:
        return False
    if ecosystem == NPM_ECOSYSTEM:
        return npm_range_excludes(declared, version)
    if ecosystem == PYPI_ECOSYSTEM:
        return pypi_range_excludes(declared, version)
    return False
