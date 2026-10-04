"""Choice between the published package and the GitHub code of a server"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from mcplain.inputs import NPM_NAME_PATTERN, PYPI_NAME_PATTERN, normalize_pypi_name
from mcplain.manifests import load_json_object, load_setup_cfg, load_toml, table

GITHUB_HOSTS: frozenset[str] = frozenset({"github.com", "www.github.com"})
SHORTHAND_PATTERN = re.compile(r"^(?:github:)?([A-Za-z0-9-]+)/([A-Za-z0-9._-]+)$")
SCP_PATTERN = re.compile(r"^[\w.-]+@([\w.-]+):(.+)$")
URL_PREFIXES: tuple[str, ...] = ("git+",)
TREE_MARKERS: frozenset[str] = frozenset({"tree", "blob"})
NPM_REGISTRY = "npm"
PYPI_REGISTRY = "pypi"


@dataclass(frozen=True)
class RepositoryLink:
    """Class that holds a GitHub repository reference found in package metadata"""

    owner: str
    repo: str
    directory: str | None
    tree_path: str | None


@dataclass(frozen=True)
class PackageCandidate:
    """Class that names the package a server folder publishes"""

    registry: str
    name: str


@dataclass(frozen=True)
class MatchOutcome:
    """Class that tells whether a package belongs to the repository, and why"""

    matched: bool
    reason: str


def clean_directory(value: str | None) -> str:
    """Normalize a folder path for comparison"""

    if not value:
        return ""
    text = value.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.strip("/")


def parse_repository_url(value: str, directory: str | None = None) -> RepositoryLink | None:
    """Read a repository URL or shorthand and return the GitHub link it names"""

    text = value.strip()
    shorthand = SHORTHAND_PATTERN.match(text)
    if shorthand:
        owner = shorthand.group(1)
        repo = _strip_git(shorthand.group(2))
        return RepositoryLink(owner, repo, clean_directory(directory) or None, None)
    for prefix in URL_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
    scp = SCP_PATTERN.match(text)
    if scp and "://" not in text:
        host = scp.group(1).lower()
        path = scp.group(2)
    else:
        try:
            parts = urlsplit(text)
        except ValueError:
            return None
        host = (parts.hostname or "").lower()
        path = parts.path
    if host not in GITHUB_HOSTS:
        return None
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        return None
    owner = segments[0]
    repo = _strip_git(segments[1])
    tree_path = None
    if len(segments) > 3 and segments[2] in TREE_MARKERS:
        tree_path = "/".join(segments[3:])
    return RepositoryLink(owner, repo, clean_directory(directory) or None, tree_path)


def _strip_git(repo: str) -> str:
    """Remove a trailing .git from a repository name"""

    if repo.endswith(".git"):
        return repo[: -len(".git")]
    return repo


def npm_links(manifest: dict[str, Any]) -> list[RepositoryLink]:
    """Return the repository links declared in an npm package manifest"""

    repository = manifest.get("repository")
    link = None
    if isinstance(repository, str):
        link = parse_repository_url(repository)
    elif isinstance(repository, dict) and isinstance(repository.get("url"), str):
        directory = repository.get("directory")
        if not isinstance(directory, str):
            directory = None
        link = parse_repository_url(repository["url"], directory)
    if link is None:
        return []
    return [link]


def pypi_links(info: dict[str, Any]) -> list[RepositoryLink]:
    """Return the GitHub links found in PyPI project metadata"""

    urls: list[str] = []
    project_urls = info.get("project_urls")
    if isinstance(project_urls, dict):
        urls.extend(value for value in project_urls.values() if isinstance(value, str))
    for key in ("home_page", "download_url"):
        value = info.get(key)
        if isinstance(value, str):
            urls.append(value)
    links = []
    for url in urls:
        link = parse_repository_url(url)
        if link is not None:
            links.append(link)
    return links


def match_links(links: list[RepositoryLink], owner: str, repo: str, subdir: str | None) -> MatchOutcome:
    """Check that package metadata points to the same repository and folder"""

    if not links:
        return MatchOutcome(False, "source.package_without_repository")
    same = [link for link in links if link.owner.lower() == owner.lower() and link.repo.lower() == repo.lower()]
    if not same:
        return MatchOutcome(False, "source.package_repository_mismatch")
    wanted = clean_directory(subdir)
    located = [link for link in same if link.directory is not None or link.tree_path is not None]
    if not located:
        return MatchOutcome(True, "source.published_matches_repository")
    for link in located:
        if _directory_matches(link, wanted):
            return MatchOutcome(True, "source.published_matches_directory")
    return MatchOutcome(False, "source.package_directory_mismatch")


def _directory_matches(link: RepositoryLink, wanted: str) -> bool:
    """Tell whether a link points to the wanted folder"""

    if link.directory is not None:
        return clean_directory(link.directory) == wanted
    tree_path = clean_directory(link.tree_path)
    if not wanted:
        return "/" not in tree_path
    return tree_path.endswith("/" + wanted)


def published_candidate(server_dir: Path) -> tuple[PackageCandidate | None, str]:
    """Return the package a server folder publishes, or the reason there is none"""

    manifest = load_json_object(server_dir / "package.json")
    if manifest is not None:
        if manifest.get("private") is True:
            return None, "source.package_private"
        name = manifest.get("name")
        if isinstance(name, str) and NPM_NAME_PATTERN.match(name):
            return PackageCandidate(NPM_REGISTRY, name), ""
    name = _python_project_name(server_dir)
    if name is not None:
        return PackageCandidate(PYPI_REGISTRY, normalize_pypi_name(name)), ""
    return None, "source.no_package_manifest"


def _python_project_name(server_dir: Path) -> str | None:
    """Read the project name from pyproject.toml or setup.cfg"""

    pyproject = load_toml(server_dir / "pyproject.toml")
    for name in (table(pyproject, "project").get("name"), table(pyproject, "tool", "poetry").get("name")):
        if isinstance(name, str) and PYPI_NAME_PATTERN.match(name):
            return name
    setup_cfg = load_setup_cfg(server_dir / "setup.cfg")
    if setup_cfg is not None:
        name = setup_cfg.get("metadata", "name", fallback=None)
        if name and PYPI_NAME_PATTERN.match(name):
            return name
    return None
