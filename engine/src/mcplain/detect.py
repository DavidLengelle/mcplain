"""Detection of MCP servers, their language and compiled code in a local folder"""

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

from mcplain.config import DEFAULT_LIMITS, Limits
from mcplain.errors import DetectionError
from mcplain.manifests import (
    load_json_object,
    load_setup_cfg,
    load_toml,
    read_text,
    requirement_name,
    string_list,
    table,
)
from mcplain.models import AnalysisStatus, LocationKind, ServerCandidate
from mcplain.paths import is_test_folder, iter_files, location_kind

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"python", "javascript", "typescript"})
PYTHON_SDKS: tuple[str, ...] = ("mcp", "fastmcp")
NPM_SDKS: tuple[str, ...] = (
    "@modelcontextprotocol/sdk",
    "@modelcontextprotocol/server",
    "fastmcp",
    "mcp-framework",
)
GO_SDKS: tuple[str, ...] = (
    "github.com/modelcontextprotocol/go-sdk",
    "github.com/mark3labs/mcp-go",
    "github.com/metoro-io/mcp-golang",
    "github.com/ThinkInAIXYZ/go-mcp",
)
RUST_SDKS: tuple[str, ...] = ("rmcp", "rust-mcp-sdk")
JVM_SDK_MARKERS: tuple[str, ...] = (
    "io.modelcontextprotocol.sdk",
    "io.modelcontextprotocol:kotlin-sdk",
    "spring-ai-starter-mcp",
    "spring-ai-mcp",
)
DOTNET_SDK_PATTERN = re.compile(r"Include\s*=\s*\"(ModelContextProtocol(?:\.[A-Za-z]+)?)\"", re.IGNORECASE)
RUBY_SDK_PATTERN = re.compile(r"^\s*gem\s+[\"'](mcp|fast-mcp)[\"']", re.MULTILINE)
PHP_SDKS: tuple[str, ...] = ("mcp/sdk", "php-mcp/server", "logiscape/mcp-sdk-php")
SWIFT_SDK_MARKERS: tuple[str, ...] = ("modelcontextprotocol/swift-sdk",)

PYTHON_IMPORT_PATTERN = re.compile(r"^\s*(?:from|import)\s+(mcp|fastmcp)\b", re.MULTILINE)
JAVASCRIPT_IMPORT_PATTERN = re.compile(
    r"(?:from\s*|require\(\s*|import\(\s*)[\"'](@modelcontextprotocol/(?:sdk|server)|fastmcp|mcp-framework)"
    r"(?:/[^\"']*)?[\"']"
)
IMPORT_SCAN_BYTES = 256 * 1024
IMPORT_SCAN_MAX_FILES = 2000

LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".zig": "zig",
    ".ex": "elixir",
    ".dart": "dart",
    ".scala": "scala",
}
DECLARATION_SUFFIXES: tuple[str, ...] = (".d.ts", ".d.mts", ".d.cts")
MARKDOWN_EXTENSIONS: frozenset[str] = frozenset({".md", ".markdown", ".mdx", ".rst"})
COMPILED_EXTENSIONS: frozenset[str] = frozenset(
    {".so", ".pyd", ".node", ".dll", ".dylib", ".exe", ".wasm", ".pyc", ".pyo"}
)
BINARY_MAGICS: tuple[bytes, ...] = (
    b"\x7fELF",
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\x00asm",
)
PE_MAGIC = b"MZ"
PE_SIGNATURE = b"PE\x00\x00"
PE_HEADER_READ = 1024
PE_OFFSET_POSITION = 60
PLATFORM_PACKAGE_PATTERN = re.compile(
    r"(?:^|[-_/@.])(?:linux|darwin|macos|win32|windows|freebsd|openbsd|android|sunos|aix)"
    r"[-_.](?:x64|x86_64|amd64|arm64|aarch64|ia32|x86|arm|armv7|riscv64|ppc64|ppc64le|s390x|universal)",
    re.IGNORECASE,
)
NATIVE_BUILD_MARKERS: tuple[str, ...] = (
    "maturin",
    "setuptools_rust",
    "setuptools-rust",
    "scikit_build_core",
    "scikit-build-core",
    "mesonpy",
    "meson-python",
    "cython",
)
MANIFEST_NAMES: frozenset[str] = frozenset(
    {
        "package.json",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "Gemfile",
        "composer.json",
        "Package.swift",
    }
)
REQUIREMENTS_PATTERN = "requirements*.txt"
CSPROJ_SUFFIX = ".csproj"
METADATA_NAMES: frozenset[str] = frozenset({"METADATA", "PKG-INFO"})
QUOTED_STRING_PATTERN = re.compile(r"[\"']([^\"'\n]{1,200})[\"']")
METADATA_FIELD_PATTERN = re.compile(r"^(Requires-Dist|Name):\s*(.+)$", re.MULTILINE)
GO_MODULE_PATTERN = re.compile(r"^module\s+(\S+)", re.MULTILINE)
JVM_LANGUAGE = "jvm"


@dataclass
class ManifestInfo:
    """Class that holds what one project file says about its folder"""

    folder: str
    file: str
    language: str
    sdk: str | None = None
    name: str | None = None
    platform_binaries: bool = False
    native_build: bool = False


@dataclass
class FileInfo:
    """Class that holds the language and role of one file"""

    path: str
    language: str | None
    is_test: bool
    is_markdown: bool


@dataclass
class Inventory:
    """Class that summarizes the files below the inspected folder"""

    manifests: list[ManifestInfo] = field(default_factory=list)
    files: list[FileInfo] = field(default_factory=list)
    compiled_files: list[str] = field(default_factory=list)


@dataclass
class Detection:
    """Class that holds the outcome of server detection"""

    status: AnalysisStatus
    server: ServerCandidate | None = None
    candidates: list[ServerCandidate] = field(default_factory=list)
    truncated: bool = False
    language: str | None = None
    compiled_files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    binary_signals: bool = False


def detect(root: Path, subdir: str | None = None, limits: Limits = DEFAULT_LIMITS) -> Detection:
    """Find the MCP server to analyze below root, optionally inside subdir"""

    base = root
    if subdir:
        base = root.joinpath(*subdir.split("/"))
        if not base.is_dir() or not base.resolve().is_relative_to(root.resolve()):
            raise DetectionError("analyze.subdir_not_found", path=subdir)
    inventory = build_inventory(root, base)
    candidates = _manifest_candidates(inventory)
    notes: list[str] = []
    if not candidates:
        candidates = _import_candidates(root, base, inventory)
        if candidates:
            notes.append("note.detected_from_imports")
    primary = [candidate for candidate in candidates if not is_test_folder(candidate.path)]
    if primary:
        candidates = primary
    candidates.sort(key=lambda candidate: candidate.path)
    if not candidates:
        return _without_server(inventory)
    if len(candidates) > 1:
        truncated = len(candidates) > limits.max_listed_servers
        return Detection(
            status=AnalysisStatus.MULTIPLE_SERVERS,
            candidates=candidates[: limits.max_listed_servers],
            truncated=truncated,
        )
    server = candidates[0]
    if server.language not in SUPPORTED_LANGUAGES:
        return Detection(
            status=AnalysisStatus.UNSUPPORTED_LANGUAGE,
            server=server,
            candidates=candidates,
            language=server.language,
        )
    return _check_compiled(server, inventory, notes)


def build_inventory(root: Path, base: Path) -> Inventory:
    """List manifests, code files and compiled files below base"""

    inventory = Inventory()
    for path in iter_files(base):
        relative = path.relative_to(root).as_posix()
        name = path.name
        suffix = path.suffix.lower()
        language = None
        if not name.endswith(DECLARATION_SUFFIXES):
            language = LANGUAGE_BY_EXTENSION.get(suffix)
        inventory.files.append(
            FileInfo(
                path=relative,
                language=language,
                is_test=location_kind(relative) is not LocationKind.SERVER_CODE,
                is_markdown=suffix in MARKDOWN_EXTENSIONS,
            )
        )
        manifest = _read_manifest(root, base, path)
        if manifest is not None:
            inventory.manifests.append(manifest)
        if suffix in COMPILED_EXTENSIONS or _has_binary_signature(path):
            inventory.compiled_files.append(relative)
    return inventory


def _folder_of(root: Path, folder: Path) -> str:
    """Return a folder path relative to root, with . for root itself"""

    relative = folder.relative_to(root).as_posix()
    if relative in ("", "."):
        return "."
    return relative


def _read_manifest(root: Path, base: Path, path: Path) -> ManifestInfo | None:
    """Parse a project file if the path is one"""

    name = path.name
    folder = _folder_of(root, path.parent)
    file = path.relative_to(root).as_posix()
    if name in METADATA_NAMES:
        if name == "METADATA" and path.parent.name.endswith(".dist-info") and path.parent.parent == base:
            return _metadata_manifest(_folder_of(root, base), file, path)
        if name == "PKG-INFO" and path.parent == base:
            return _metadata_manifest(folder, file, path)
        return None
    if fnmatchcase(name, REQUIREMENTS_PATTERN):
        return _requirements_manifest(folder, file, path)
    if name.endswith(CSPROJ_SUFFIX):
        return _pattern_manifest(folder, file, path, "csharp", DOTNET_SDK_PATTERN)
    readers: dict[str, Callable[[str, str, Path], ManifestInfo]] = {
        "package.json": _package_json_manifest,
        "pyproject.toml": _pyproject_manifest,
        "setup.py": _setup_py_manifest,
        "setup.cfg": _setup_cfg_manifest,
        "go.mod": _go_manifest,
        "Cargo.toml": _cargo_manifest,
        "pom.xml": _jvm_manifest,
        "build.gradle": _jvm_manifest,
        "build.gradle.kts": _jvm_manifest,
        "Gemfile": _gemfile_manifest,
        "composer.json": _composer_manifest,
        "Package.swift": _swift_manifest,
    }
    reader = readers.get(name)
    if reader is None:
        return None
    return reader(folder, file, path)


def _first_sdk(names: list[str], sdks: tuple[str, ...]) -> str | None:
    """Return the first known SDK found in a list of dependency names"""

    for sdk in sdks:
        if sdk in names:
            return sdk
    return None


def _package_json_manifest(folder: str, file: str, path: Path) -> ManifestInfo:
    """Read dependencies from package.json"""

    data = load_json_object(path) or {}
    names: list[str] = []
    for key in ("dependencies", "peerDependencies", "optionalDependencies"):
        names.extend(table(data, key).keys())
    optional = list(table(data, "optionalDependencies").keys())
    package_name = data.get("name")
    if not isinstance(package_name, str):
        package_name = None
    return ManifestInfo(
        folder=folder,
        file=file,
        language="javascript",
        sdk=_first_sdk(names, NPM_SDKS),
        name=package_name,
        platform_binaries=any(PLATFORM_PACKAGE_PATTERN.search(name) for name in optional),
    )


def _python_names(requirements: list[str]) -> list[str]:
    """Return the normalized names of PEP 508 requirements"""

    names = []
    for requirement in requirements:
        name = requirement_name(requirement)
        if name is not None:
            names.append(name)
    return names


def _pyproject_manifest(folder: str, file: str, path: Path) -> ManifestInfo:
    """Read dependencies and build backend from pyproject.toml"""

    data = load_toml(path)
    project = table(data, "project")
    requirements = string_list(project.get("dependencies"))
    for extra in table(data, "project", "optional-dependencies").values():
        requirements.extend(string_list(extra))
    names = _python_names(requirements)
    names.extend(requirement_name(key) or key for key in table(data, "tool", "poetry", "dependencies"))
    build_system = table(data, "build-system")
    build_text = " ".join([str(build_system.get("build-backend", "")), *string_list(build_system.get("requires"))])
    project_name = project.get("name")
    if not isinstance(project_name, str):
        project_name = table(data, "tool", "poetry").get("name")
    if not isinstance(project_name, str):
        project_name = None
    return ManifestInfo(
        folder=folder,
        file=file,
        language="python",
        sdk=_first_sdk(names, PYTHON_SDKS),
        name=project_name,
        native_build=any(marker in build_text.lower() for marker in NATIVE_BUILD_MARKERS),
    )


def _setup_py_manifest(folder: str, file: str, path: Path) -> ManifestInfo:
    """Read requirement strings from setup.py as text, without running it"""

    text = read_text(path) or ""
    names = _python_names(QUOTED_STRING_PATTERN.findall(text))
    exact = [name for name in names if name in PYTHON_SDKS]
    return ManifestInfo(
        folder=folder,
        file=file,
        language="python",
        sdk=_first_sdk(exact, PYTHON_SDKS),
        native_build="ext_modules" in text,
    )


def _setup_cfg_manifest(folder: str, file: str, path: Path) -> ManifestInfo:
    """Read install_requires from setup.cfg"""

    parser = load_setup_cfg(path)
    requirements: list[str] = []
    name = None
    if parser is not None:
        raw = parser.get("options", "install_requires", fallback="")
        requirements = [line for line in raw.splitlines() if line.strip()]
        name = parser.get("metadata", "name", fallback=None)
    return ManifestInfo(
        folder=folder,
        file=file,
        language="python",
        sdk=_first_sdk(_python_names(requirements), PYTHON_SDKS),
        name=name,
    )


def _requirements_manifest(folder: str, file: str, path: Path) -> ManifestInfo:
    """Read a requirements file line by line"""

    lines = []
    for line in (read_text(path) or "").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped and not stripped.startswith("-"):
            lines.append(stripped)
    return ManifestInfo(
        folder=folder,
        file=file,
        language="python",
        sdk=_first_sdk(_python_names(lines), PYTHON_SDKS),
    )


def _metadata_manifest(folder: str, file: str, path: Path) -> ManifestInfo:
    """Read Requires-Dist and Name from wheel METADATA or sdist PKG-INFO"""

    requirements = []
    name = None
    for key, value in METADATA_FIELD_PATTERN.findall(read_text(path) or ""):
        if key == "Requires-Dist":
            requirements.append(value)
        elif name is None:
            name = value.strip()
    return ManifestInfo(
        folder=folder,
        file=file,
        language="python",
        sdk=_first_sdk(_python_names(requirements), PYTHON_SDKS),
        name=name,
    )


def _go_manifest(folder: str, file: str, path: Path) -> ManifestInfo:
    """Look for a Go MCP SDK in go.mod"""

    text = read_text(path) or ""
    sdk = None
    for module in GO_SDKS:
        if module in text:
            sdk = module
            break
    module_match = GO_MODULE_PATTERN.search(text)
    name = None
    if module_match:
        name = module_match.group(1)
    return ManifestInfo(folder=folder, file=file, language="go", sdk=sdk, name=name)


def _cargo_manifest(folder: str, file: str, path: Path) -> ManifestInfo:
    """Look for a Rust MCP SDK in Cargo.toml"""

    data = load_toml(path)
    names = list(table(data, "dependencies").keys()) + list(table(data, "workspace", "dependencies").keys())
    package_name = table(data, "package").get("name")
    if not isinstance(package_name, str):
        package_name = None
    return ManifestInfo(
        folder=folder,
        file=file,
        language="rust",
        sdk=_first_sdk(names, RUST_SDKS),
        name=package_name,
    )


def _jvm_manifest(folder: str, file: str, path: Path) -> ManifestInfo:
    """Look for a Java or Kotlin MCP SDK in Maven or Gradle files"""

    text = read_text(path) or ""
    sdk = None
    for marker in JVM_SDK_MARKERS:
        if marker in text:
            sdk = marker
            break
    return ManifestInfo(folder=folder, file=file, language=JVM_LANGUAGE, sdk=sdk)


def _pattern_manifest(folder: str, file: str, path: Path, language: str, pattern: re.Pattern[str]) -> ManifestInfo:
    """Look for an SDK with a regular expression"""

    match = pattern.search(read_text(path) or "")
    sdk = None
    if match:
        sdk = match.group(1)
    return ManifestInfo(folder=folder, file=file, language=language, sdk=sdk)


def _gemfile_manifest(folder: str, file: str, path: Path) -> ManifestInfo:
    """Look for a Ruby MCP SDK in a Gemfile"""

    return _pattern_manifest(folder, file, path, "ruby", RUBY_SDK_PATTERN)


def _composer_manifest(folder: str, file: str, path: Path) -> ManifestInfo:
    """Look for a PHP MCP SDK in composer.json"""

    data = load_json_object(path) or {}
    names = list(table(data, "require").keys())
    return ManifestInfo(folder=folder, file=file, language="php", sdk=_first_sdk(names, PHP_SDKS))


def _swift_manifest(folder: str, file: str, path: Path) -> ManifestInfo:
    """Look for the Swift MCP SDK in Package.swift"""

    text = read_text(path) or ""
    sdk = None
    for marker in SWIFT_SDK_MARKERS:
        if marker in text:
            sdk = marker
            break
    return ManifestInfo(folder=folder, file=file, language="swift", sdk=sdk)


def _has_binary_signature(path: Path) -> bool:
    """Tell whether a file starts like an ELF, Mach-O, PE or WebAssembly binary"""

    try:
        with path.open("rb") as handle:
            head = handle.read(PE_HEADER_READ)
    except OSError:
        return False
    if head.startswith(BINARY_MAGICS):
        return True
    if head.startswith(PE_MAGIC) and len(head) >= PE_OFFSET_POSITION + 4:
        offset = int.from_bytes(head[PE_OFFSET_POSITION:PE_OFFSET_POSITION + 4], "little")
        return head[offset:offset + len(PE_SIGNATURE)] == PE_SIGNATURE
    return False


def _inside(path: str, folder: str) -> bool:
    """Tell whether a root-relative path is inside a root-relative folder"""

    if folder == ".":
        return True
    return path == folder or path.startswith(folder + "/")


def _manifest_candidates(inventory: Inventory) -> list[ServerCandidate]:
    """Turn folders whose project file depends on an MCP SDK into candidates"""

    by_folder: dict[str, list[ManifestInfo]] = {}
    for manifest in inventory.manifests:
        by_folder.setdefault(manifest.folder, []).append(manifest)
    candidates = []
    for folder, manifests in by_folder.items():
        with_sdk = [manifest for manifest in manifests if manifest.sdk is not None]
        if not with_sdk:
            continue
        chosen = with_sdk[0]
        name = next((manifest.name for manifest in manifests if manifest.name), None)
        candidates.append(
            ServerCandidate(
                path=folder,
                language=_refine_language(chosen.language, folder, inventory),
                name=name,
                sdk=chosen.sdk,
                manifest=chosen.file,
            )
        )
    return candidates


def _refine_language(language: str, folder: str, inventory: Inventory) -> str:
    """Tell TypeScript from JavaScript and Kotlin from Java using the files present"""

    languages = {info.language for info in inventory.files if _inside(info.path, folder)}
    if language == "javascript" and "typescript" in languages:
        return "typescript"
    if language == JVM_LANGUAGE:
        if "kotlin" in languages:
            return "kotlin"
        return "java"
    return language


def _import_candidates(root: Path, base: Path, inventory: Inventory) -> list[ServerCandidate]:
    """Find a server with no project file by reading SDK imports as text"""

    scanned = 0
    for info in inventory.files:
        if info.is_test or info.language not in SUPPORTED_LANGUAGES:
            continue
        if scanned >= IMPORT_SCAN_MAX_FILES:
            break
        scanned += 1
        try:
            with root.joinpath(*info.path.split("/")).open("rb") as handle:
                text = handle.read(IMPORT_SCAN_BYTES).decode("utf-8", errors="replace")
        except OSError:
            continue
        pattern = JAVASCRIPT_IMPORT_PATTERN
        if info.language == "python":
            pattern = PYTHON_IMPORT_PATTERN
        match = pattern.search(text)
        if match:
            return [
                ServerCandidate(
                    path=_folder_of(root, base),
                    language=info.language,
                    sdk=match.group(1),
                )
            ]
    return []


def _without_server(inventory: Inventory) -> Detection:
    """Choose between not_a_server and unsupported_language when no server was found"""

    code = Counter(info.language for info in inventory.files if info.language and not info.is_test)
    markdown = sum(1 for info in inventory.files if info.is_markdown)
    if not inventory.manifests:
        total_code = sum(code.values())
        if total_code == 0 or markdown >= total_code:
            note = "note.no_project_file"
            if markdown:
                note = "note.mostly_documentation"
            return Detection(status=AnalysisStatus.NOT_A_SERVER, notes=[note])
    manifest_languages = Counter(
        _refine_language(manifest.language, manifest.folder, inventory) for manifest in inventory.manifests
    )
    dominant = None
    if manifest_languages:
        dominant = manifest_languages.most_common(1)[0][0]
    elif code:
        dominant = code.most_common(1)[0][0]
    if dominant is not None and dominant not in SUPPORTED_LANGUAGES:
        return Detection(status=AnalysisStatus.UNSUPPORTED_LANGUAGE, language=dominant)
    return Detection(status=AnalysisStatus.NOT_A_SERVER, notes=["note.no_mcp_sdk"])


def _check_compiled(server: ServerCandidate, inventory: Inventory, notes: list[str]) -> Detection:
    """Flag compiled code inside the chosen server folder"""

    compiled = [path for path in inventory.compiled_files if _inside(path, server.path)]
    sources = [
        info
        for info in inventory.files
        if _inside(info.path, server.path) and info.language in SUPPORTED_LANGUAGES and not info.is_test
    ]
    manifests = [manifest for manifest in inventory.manifests if manifest.folder == server.path]
    platform = any(manifest.platform_binaries for manifest in manifests)
    native = any(manifest.native_build for manifest in manifests)
    if platform:
        notes.append("note.platform_binary_dependencies")
    if native:
        notes.append("note.native_build_backend")
    binary_signals = bool(compiled) or platform
    status = AnalysisStatus.OK
    if binary_signals and not sources:
        status = AnalysisStatus.COMPILED
    elif binary_signals or native:
        notes.append("note.partially_compiled")
    return Detection(
        status=status,
        server=server,
        candidates=[server],
        compiled_files=compiled,
        notes=notes,
        binary_signals=binary_signals,
    )
