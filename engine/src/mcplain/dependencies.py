"""Direct dependencies declared in package metadata, read as plain data"""

import re
from typing import Any

from mcplain.inputs import NPM_NAME_PATTERN
from mcplain.manifests import requirement_name, string_list, table

NPM_ECOSYSTEM = "npm"
PYPI_ECOSYSTEM = "PyPI"
EXTRA_MARKER = re.compile(r"\bextra\s*==")


def npm_dependency_names(manifest: dict[str, Any] | None) -> list[str]:
    """Return the names listed in the dependencies of an npm manifest"""

    dependencies = table(manifest, "dependencies")
    return sorted(name for name in dependencies if NPM_NAME_PATTERN.match(name))


def requirement_names(requirements: list[str]) -> list[str]:
    """Return the normalized names of PEP 508 requirements, without those of extras"""

    names = set()
    for requirement in requirements:
        if EXTRA_MARKER.search(requirement):
            continue
        name = requirement_name(requirement)
        if name is not None:
            names.add(name)
    return sorted(names)


def pypi_dependency_names(info: dict[str, Any] | None) -> list[str]:
    """Return the names required by the Requires-Dist field of PyPI metadata"""

    return requirement_names(string_list((info or {}).get("requires_dist")))


def pyproject_dependency_names(pyproject: dict[str, Any] | None) -> list[str]:
    """Return the names listed in the project dependencies of a pyproject.toml document"""

    return requirement_names(string_list(table(pyproject, "project").get("dependencies")))
