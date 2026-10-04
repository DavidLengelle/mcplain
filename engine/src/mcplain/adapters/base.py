"""Common interface of the language adapters and assembly of their results"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from mcplain.adapters.common import (
    SourceText,
    TextValue,
    codepoint_label,
    contains,
    extract_urls,
    hidden_tag_text,
    scan_invisible,
    source_offset,
)
from mcplain.capabilities import Capability
from mcplain.config import DEFAULT_LIMITS, Limits
from mcplain.models import (
    DeclarationKind,
    DomainRef,
    Finding,
    InstallScript,
    InvisibleCategory,
    InvisibleUnicode,
    LocationKind,
    ParseError,
    SensitivePathRef,
    ServerAnalysis,
    SkippedFile,
    Tool,
    ToolParameter,
)
from mcplain.paths import iter_files, location_kind

TOO_LARGE_REASON = "too_large"


@dataclass
class RawFinding:
    """Class that holds a capability seen at a byte offset"""

    capability: Capability
    offset: int
    function: str | None = None
    detail: str | None = None


@dataclass
class RawTool:
    """Class that holds a tool declaration before positions are resolved"""

    name: str
    description: TextValue
    offset: int
    declaration: DeclarationKind
    name_is_dynamic: bool = False
    parameters: list[ToolParameter] = field(default_factory=list)
    parameters_are_dynamic: bool = False
    bodies: list[tuple[int, int]] = field(default_factory=list)
    text_ranges: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class RawString:
    """Class that holds one decoded string literal"""

    value: TextValue
    offset: int
    sensitive: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class FileReport:
    """Class that holds everything an adapter found in one file"""

    path: str
    source: SourceText
    findings: list[RawFinding] = field(default_factory=list)
    tools: list[RawTool] = field(default_factory=list)
    strings: list[RawString] = field(default_factory=list)
    error_offset: int | None = None


@dataclass
class _ToolSlot:
    """Class that pairs a raw tool with the model being filled"""

    raw: RawTool
    model: Tool
    seen: set[tuple[Capability, int]] = field(default_factory=set)


class Adapter(ABC):
    """Class that turns a server folder into a ServerAnalysis"""

    language: str = ""

    def __init__(self, limits: Limits = DEFAULT_LIMITS) -> None:
        """Keep the limits used while reading files"""

        self.limits = limits

    @abstractmethod
    def accepts(self, path: Path) -> bool:
        """Tell whether a file is source code for this adapter"""

    @abstractmethod
    def analyze_file(self, relative_path: str, source: SourceText) -> FileReport:
        """Analyze one decoded source file"""

    @abstractmethod
    def install_scripts(self, server_dir: Path) -> list[InstallScript]:
        """Return the code this server runs at install time"""

    def language_for(self, analyzed: list[str]) -> str:
        """Return the language name to report for the analyzed files"""

        return self.language

    def analyze(self, server_dir: Path) -> ServerAnalysis:
        """Analyze every source file of a server folder"""

        analysis = ServerAnalysis(path=".", language=self.language)
        analyzed: list[str] = []
        server_seen: set[tuple[Capability, str, int]] = set()
        for path in iter_files(server_dir):
            if not self.accepts(path):
                continue
            relative = path.relative_to(server_dir).as_posix()
            size = path.stat().st_size
            if size > self.limits.max_source_file_bytes:
                analysis.skipped_files.append(SkippedFile(file=relative, reason=TOO_LARGE_REASON, size=size))
                continue
            text = path.read_bytes().decode("utf-8", errors="replace")
            source = SourceText(text, self.limits)
            report = self.analyze_file(relative, source)
            analyzed.append(relative)
            if source.is_minified(relative):
                analysis.minified_files.append(relative)
            self._merge(analysis, report, server_seen)
        analysis.files_analyzed = len(analyzed)
        analysis.language = self.language_for(analyzed)
        for script in self.install_scripts(server_dir):
            analysis.install_scripts.append(script)
            analysis.findings.append(
                Finding(
                    capability=Capability.INSTALL_SCRIPT,
                    file=script.file,
                    line=script.line,
                    column=1,
                    snippet=script.command[: self.limits.max_snippet_chars],
                    location_kind=LocationKind.SERVER_CODE,
                    detail=script.kind,
                )
            )
            for url, domain in extract_urls(script.command):
                analysis.domains.append(
                    DomainRef(
                        domain=domain,
                        url=url,
                        file=script.file,
                        line=script.line,
                        location_kind=LocationKind.SERVER_CODE,
                    )
                )
        for tool in analysis.tools:
            tool.findings.sort(key=lambda finding: (finding.line, finding.column))
        analysis.findings.sort(key=lambda finding: (finding.file, finding.line, finding.column))
        return analysis

    def _merge(
        self,
        analysis: ServerAnalysis,
        report: FileReport,
        server_seen: set[tuple[Capability, str, int]],
    ) -> None:
        """Resolve positions of one file report and attach results to tools or server"""

        source = report.source
        location = location_kind(report.path)
        if report.error_offset is not None:
            line, column = source.position(report.error_offset)
            analysis.parse_errors.append(ParseError(file=report.path, line=line, column=column))
        slots = []
        for raw in report.tools:
            line, _ = source.position(raw.offset)
            model = Tool(
                name=raw.name,
                name_is_dynamic=raw.name_is_dynamic,
                description=raw.description.value,
                description_is_dynamic=raw.description.dynamic,
                parameters=raw.parameters,
                parameters_are_dynamic=raw.parameters_are_dynamic,
                file=report.path,
                line=line,
                declaration=raw.declaration,
                location_kind=location,
            )
            slots.append(_ToolSlot(raw, model))
            analysis.tools.append(model)
        for raw_finding in report.findings:
            line, column = source.position(raw_finding.offset)
            finding = Finding(
                capability=raw_finding.capability,
                file=report.path,
                line=line,
                column=column,
                snippet=source.snippet(raw_finding.offset),
                function=raw_finding.function,
                location_kind=location,
                detail=raw_finding.detail,
            )
            owner = _owner(slots, raw_finding.offset)
            if owner is not None:
                key = (finding.capability, line)
                if key not in owner.seen:
                    owner.seen.add(key)
                    owner.model.findings.append(finding)
                continue
            server_key = (finding.capability, report.path, line)
            if server_key not in server_seen:
                server_seen.add(server_key)
                analysis.findings.append(finding)
        for raw_string in report.strings:
            self._merge_string(analysis, report, raw_string, slots, location)

    def _merge_string(
        self,
        analysis: ServerAnalysis,
        report: FileReport,
        raw_string: RawString,
        slots: list[_ToolSlot],
        location: LocationKind,
    ) -> None:
        """Record URLs, sensitive paths and invisible characters of one string"""

        source = report.source
        owner = _owner(slots, raw_string.offset)
        tool_name = None
        in_description = False
        if owner is not None:
            tool_name = owner.model.name
            in_description = contains(owner.raw.text_ranges, raw_string.offset)
        line, _ = source.position(raw_string.offset)
        for url, domain in extract_urls(raw_string.value.value):
            analysis.domains.append(
                DomainRef(domain=domain, url=url, file=report.path, line=line, location_kind=location, tool=tool_name)
            )
        for category, match in raw_string.sensitive:
            analysis.sensitive_paths.append(
                SensitivePathRef(
                    category=category,
                    match=match,
                    file=report.path,
                    line=line,
                    location_kind=location,
                    tool=tool_name,
                )
            )
        for run in scan_invisible(raw_string.value.value):
            if run.category is InvisibleCategory.CONTROL and not in_description:
                continue
            run_line, run_column = source.position(source_offset(raw_string.value, run.index))
            hidden = None
            if run.category is InvisibleCategory.TAG:
                hidden = hidden_tag_text(run.characters)
            analysis.invisible_unicode.append(
                InvisibleUnicode(
                    file=report.path,
                    line=run_line,
                    column=run_column,
                    category=run.category,
                    codepoints=[codepoint_label(character) for character in run.characters],
                    hidden_text=hidden,
                    in_description=in_description,
                    tool=tool_name,
                    location_kind=location,
                )
            )


def _owner(slots: list[_ToolSlot], offset: int) -> _ToolSlot | None:
    """Return the tool whose body or description most tightly contains an offset"""

    best = None
    best_size = 0
    for slot in slots:
        for start, end in slot.raw.bodies + slot.raw.text_ranges:
            if start <= offset < end:
                size = end - start
                if best is None or size < best_size:
                    best = slot
                    best_size = size
    return best
