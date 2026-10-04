"""Direct dependencies declared by a downloaded package, read as plain data"""

import re
from pathlib import Path

from mcplain.inputs import NPM_NAME_PATTERN
from mcplain.manifests import load_json_object, load_toml, read_text, requirement_name, string_list, table

NPM_ECOSYSTEM = "npm"
PYPI_ECOSYSTEM = "PyPI"
ECOSYSTEMS: dict[str, str] = {"python": PYPI_ECOSYSTEM, "javascript": NPM_ECOSYSTEM, "typescript": NPM_ECOSYSTEM}
REQUIRES_DIST = "Requires-Dist:"
EXTRA_MARKER = re.compile(r"\bextra\s*==")
METADATA_FILES: tuple[str, ...] = ("METADATA", "PKG-INFO")


def npm_dependencies(folder: Path) -> list[str]:
    """Return the names listed in the dependencies of package.json"""

    dependencies = table(load_json_object(folder / "package.json"), "dependencies")
    return sorted(name for name in dependencies if NPM_NAME_PATTERN.match(name))


def python_dependencies(folder: Path) -> list[str]:
    """Return the names required by the wheel metadata, PKG-INFO or pyproject.toml, without extras"""

    requirements: list[str] = []
    candidates = [path / "METADATA" for path in folder.glob("*.dist-info")]
    candidates.extend(folder / name for name in METADATA_FILES)
    for path in candidates:
        for line in (read_text(path) or "").splitlines():
            if line.startswith(REQUIRES_DIST):
                requirements.append(line[len(REQUIRES_DIST):].strip())
    requirements.extend(string_list(table(load_toml(folder / "pyproject.toml"), "project").get("dependencies")))
    names = set()
    for requirement in requirements:
        if EXTRA_MARKER.search(requirement):
            continue
        name = requirement_name(requirement)
        if name is not None:
            names.add(name)
    return sorted(names)


def direct_dependencies(folder: Path, language: str) -> tuple[str | None, list[str]]:
    """Return the ecosystem of a server folder and the names of its direct dependencies"""

    ecosystem = ECOSYSTEMS.get(language)
    if ecosystem == NPM_ECOSYSTEM:
        return ecosystem, npm_dependencies(folder)
    if ecosystem == PYPI_ECOSYSTEM:
        return ecosystem, python_dependencies(folder)
    return None, []
