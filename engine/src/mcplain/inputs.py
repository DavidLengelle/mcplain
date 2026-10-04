"""Strict parsing of what the user pastes into an InputSpec"""

import re
import unicodedata
from collections.abc import Callable
from urllib.parse import urlsplit

from mcplain.errors import InputError
from mcplain.models import InputKind, InputSpec

MAX_INPUT_LENGTH = 2048
GITHUB_HOSTS: frozenset[str] = frozenset({"github.com", "www.github.com"})
OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9._+@=,~-]{1,255}$")
NPM_NAME_PATTERN = re.compile(r"^(?:@[a-z0-9-][a-z0-9._-]*/)?[a-z0-9-][a-z0-9._-]*$")
NPM_MAX_NAME_LENGTH = 214
NPM_RESERVED_NAMES: frozenset[str] = frozenset({"node_modules", "favicon.ico"})
NPM_SEMVER_PATTERN = re.compile(
    r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
NPM_TAG_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")
NPX_YES_FLAGS: frozenset[str] = frozenset({"-y", "--yes"})
PYPI_NAME_PATTERN = re.compile(r"^(?:[A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$", re.IGNORECASE)
PYPI_VERSION_PATTERN = re.compile(
    r"^(?:\d+!)?\d+(?:\.\d+)*(?:(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?"
    r"(?:\+[a-z0-9]+(?:\.[a-z0-9]+)*)?$",
    re.IGNORECASE,
)
PYPI_RANGE_CHARACTERS = "<>~!=;,* "
SCP_LIKE_PATTERN = re.compile(r"^[\w.-]+@[\w.-]+:")


def parse_input(text: str) -> InputSpec:
    """Turn the pasted text into a validated InputSpec or raise InputError"""

    stripped = text.strip()
    if not stripped:
        raise InputError("input.empty")
    if len(stripped) > MAX_INPUT_LENGTH:
        raise InputError("input.too_long", limit=MAX_INPUT_LENGTH)
    for character in stripped:
        if character in " \t":
            continue
        if unicodedata.category(character) in ("Cc", "Cf", "Zl", "Zp"):
            raise InputError("input.control_characters")
    tokens = stripped.split()
    head = tokens[0]
    if head == "npx":
        return _parse_npx(tokens[1:])
    if head == "uvx":
        return _parse_uvx(tokens[1:])
    _reject_foreign_scheme(head)
    if len(tokens) > 1:
        raise InputError("input.unexpected_arguments", arguments=" ".join(tokens[1:]))
    return _parse_url(head)


def parse_selection(text: str) -> str:
    """Validate a relative server path given with --select"""

    value = text.strip().strip("/")
    if value.startswith("./"):
        value = value[2:]
    if not value or "\\" in value or "%" in value or text.strip().startswith("/"):
        raise InputError("input.invalid_selection", path=text)
    segments = value.split("/")
    for segment in segments:
        if segment in ("", ".", ".."):
            raise InputError("input.invalid_selection", path=text)
        if not SEGMENT_PATTERN.match(segment):
            raise InputError("input.invalid_selection", path=text)
    return "/".join(segments)


def add_subdir(spec: InputSpec, extra: str) -> InputSpec:
    """Return a GitHub spec that also points inside an extra subfolder"""

    if spec.tree_path is not None:
        return spec.model_copy(update={"tree_path": f"{spec.tree_path}/{extra}"})
    subdir = extra
    if spec.subdir:
        subdir = f"{spec.subdir}/{extra}"
    return spec.model_copy(update={"kind": InputKind.GITHUB_SUBDIR, "subdir": subdir})


def resolve_tree_reference(spec: InputSpec, ref_exists: Callable[[str], bool]) -> InputSpec:
    """Split an ambiguous tree path into reference and subfolder by trying prefixes"""

    if spec.tree_path is None:
        return spec
    parts = spec.tree_path.split("/")
    for size in range(1, len(parts) + 1):
        candidate = "/".join(parts[:size])
        if not ref_exists(candidate):
            continue
        rest = "/".join(parts[size:])
        if rest:
            return spec.model_copy(
                update={
                    "kind": InputKind.GITHUB_SUBDIR,
                    "ref": candidate,
                    "subdir": rest,
                    "tree_path": None,
                }
            )
        return spec.model_copy(
            update={"kind": InputKind.GITHUB_REPO, "ref": candidate, "subdir": None, "tree_path": None}
        )
    raise InputError("input.reference_not_found", reference=spec.tree_path)


def normalize_pypi_name(name: str) -> str:
    """Return the PEP 503 normalized form of a PyPI project name"""

    return re.sub(r"[-_.]+", "-", name).lower()


def _reject_foreign_scheme(value: str) -> None:
    """Refuse git transports and non-HTTPS schemes with a clear message"""

    if value.lower().startswith("ext::"):
        raise InputError("input.unsupported_scheme", scheme="ext")
    if "://" not in value and SCP_LIKE_PATTERN.match(value):
        raise InputError("input.unsupported_scheme", scheme="ssh")
    scheme = value.split("://", 1)[0].lower()
    if "://" in value and scheme != "https":
        raise InputError("input.unsupported_scheme", scheme=scheme)


def _parse_url(value: str) -> InputSpec:
    """Parse a GitHub URL into an InputSpec"""

    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as error:
        raise InputError("input.unrecognized") from error
    if not parts.scheme or "://" not in value:
        raise InputError("input.unrecognized")
    if parts.scheme.lower() != "https":
        raise InputError("input.unsupported_scheme", scheme=parts.scheme.lower())
    if parts.username is not None or parts.password is not None:
        raise InputError("input.credentials_in_url")
    host = (parts.hostname or "").lower()
    if host not in GITHUB_HOSTS or port not in (None, 443):
        raise InputError("input.unsupported_host", host=host)
    if parts.query:
        raise InputError("input.unexpected_url_parts")
    path = parts.path
    if "%" in path or "\\" in path:
        raise InputError("input.invalid_path")
    segments = path.strip("/").split("/")
    if any(segment in (".", "..") for segment in segments):
        raise InputError("input.path_traversal")
    if "" in segments:
        if segments == [""]:
            raise InputError("input.missing_repository")
        raise InputError("input.invalid_path")
    if len(segments) < 2:
        raise InputError("input.missing_repository")
    owner, repo = segments[0], segments[1]
    if len(segments) == 2 and repo.endswith(".git"):
        repo = repo[: -len(".git")]
    _validate_owner_repo(owner, repo)
    if len(segments) == 2:
        return InputSpec(kind=InputKind.GITHUB_REPO, owner=owner, repo=repo)
    if segments[2] != "tree":
        raise InputError("input.unsupported_github_path", part=segments[2])
    tree_parts = segments[3:]
    if not tree_parts:
        raise InputError("input.missing_reference")
    for segment in tree_parts:
        if not SEGMENT_PATTERN.match(segment) or segment.endswith(".lock"):
            raise InputError("input.invalid_reference", reference=segment)
    if len(tree_parts) == 1:
        return InputSpec(kind=InputKind.GITHUB_REPO, owner=owner, repo=repo, ref=tree_parts[0])
    return InputSpec(
        kind=InputKind.GITHUB_SUBDIR,
        owner=owner,
        repo=repo,
        ref=tree_parts[0],
        subdir="/".join(tree_parts[1:]),
        tree_path="/".join(tree_parts),
    )


def _validate_owner_repo(owner: str, repo: str) -> None:
    """Check GitHub owner and repository names"""

    if not OWNER_PATTERN.match(owner):
        raise InputError("input.invalid_owner", owner=owner)
    if not REPO_PATTERN.match(repo):
        raise InputError("input.invalid_repository", repository=repo)


def _parse_npx(arguments: list[str]) -> InputSpec:
    """Parse the arguments of an npx command"""

    rest = list(arguments)
    if rest and rest[0] in NPX_YES_FLAGS:
        rest = rest[1:]
    if not rest:
        raise InputError("input.missing_package")
    if len(rest) > 1:
        raise InputError("input.unexpected_arguments", arguments=" ".join(rest[1:]))
    token = rest[0]
    if token.startswith("-"):
        raise InputError("input.unexpected_arguments", arguments=token)
    if ":" in token or token.startswith((".", "/", "~")):
        raise InputError("input.npm_not_registry", value=token)
    name, version = _split_npm_spec(token)
    if (
        len(name) > NPM_MAX_NAME_LENGTH
        or name in NPM_RESERVED_NAMES
        or not NPM_NAME_PATTERN.match(name)
    ):
        raise InputError("input.invalid_npm_name", name=name)
    if version is not None:
        version = _validate_npm_version(version)
    return InputSpec(kind=InputKind.NPM, package=name, version=version)


def _split_npm_spec(token: str) -> tuple[str, str | None]:
    """Split an npm package spec into name and optional version"""

    start = 0
    if token.startswith("@"):
        start = 1
    index = token.find("@", start)
    if index == -1:
        return token, None
    version = token[index + 1:]
    if not version:
        raise InputError("input.invalid_npm_version", version=version)
    return token[:index], version


def _validate_npm_version(version: str) -> str:
    """Accept an exact semver version or a dist-tag"""

    if NPM_SEMVER_PATTERN.match(version):
        return version.removeprefix("v")
    if NPM_TAG_PATTERN.match(version):
        return version
    if any(character in version for character in "^~<>=| *"):
        raise InputError("input.version_range_unsupported", version=version)
    raise InputError("input.invalid_npm_version", version=version)


def _parse_uvx(arguments: list[str]) -> InputSpec:
    """Parse the arguments of a uvx command"""

    if not arguments:
        raise InputError("input.missing_package")
    if len(arguments) > 1:
        raise InputError("input.unexpected_arguments", arguments=" ".join(arguments[1:]))
    token = arguments[0]
    if token.startswith("-"):
        raise InputError("input.unexpected_arguments", arguments=token)
    if "[" in token or "]" in token:
        raise InputError("input.pypi_extras_unsupported")
    version: str | None = None
    if "==" in token:
        name, version = token.split("==", 1)
    elif "@" in token:
        name, version = token.split("@", 1)
        if version == "latest":
            version = None
    else:
        name = token
    if any(character in name for character in PYPI_RANGE_CHARACTERS):
        raise InputError("input.version_range_unsupported", version=token)
    if not PYPI_NAME_PATTERN.match(name):
        raise InputError("input.invalid_pypi_name", name=name)
    if version is not None and not PYPI_VERSION_PATTERN.match(version):
        raise InputError("input.invalid_pypi_version", version=version)
    return InputSpec(kind=InputKind.PYPI, package=normalize_pypi_name(name), version=version)
