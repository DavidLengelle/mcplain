"""Common interface of the language adapters and assembly of their results"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from mcplain.adapters.callgraph import CallGraph, Region, Step
from mcplain.adapters.common import (
    SourceText,
    codepoint_label,
    contains,
    extract_urls,
    hidden_tag_text,
    scan_invisible,
    source_offset,
)
from mcplain.adapters.flow_report import FlowAssembler, ToolScope
from mcplain.adapters.report import FileReport, PackageContext, RawCall, RawHandler, RawString, RawTool
from mcplain.capabilities import Capability, path_kinds
from mcplain.config import DEFAULT_LIMITS, Limits
from mcplain.models import (
    CallStep,
    CopyRecipient,
    DeclarationKind,
    DomainRef,
    Finding,
    InstallScript,
    InvisibleCategory,
    InvisibleUnicode,
    LocationKind,
    OutsideKind,
    ParseError,
    SensitivePathRef,
    ServerAnalysis,
    SkippedFile,
    TextMatch,
    TextMatchKind,
    Tool,
    TrackingGap,
)
from mcplain.paths import iter_files, location_kind
from mcplain.patterns import PIPE_TO_SHELL, analyzer_talk, excerpt

TOO_LARGE_REASON = "too_large"
RAW_BIDI_PATTERN = re.compile("[\u202a-\u202e\u2066-\u2069]+")
FUNCTION_DECLARATIONS: frozenset[DeclarationKind] = frozenset(
    {DeclarationKind.DECORATOR, DeclarationKind.ADD_TOOL, DeclarationKind.FROM_FUNCTION}
)


@dataclass
class _ToolSlot:
    """Class that pairs a raw tool with its file and the model being filled"""

    file: str
    raw: RawTool
    model: Tool
    regions: list[Region] = field(default_factory=list)
    seen: set[tuple[Capability, str, int]] = field(default_factory=set)
    gaps: set[TrackingGap] = field(default_factory=set)


@dataclass(frozen=True)
class _Starts:
    """Class that lists the entry functions and the files run at install time"""

    entries: list[tuple[str, str]]
    installs: set[str]


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
    def analyze_file(self, relative_path: str, source: SourceText, context: PackageContext) -> FileReport:
        """Analyze one decoded source file"""

    @abstractmethod
    def install_scripts(self, server_dir: Path) -> list[InstallScript]:
        """Return the code this server runs at install time"""

    def index_modules(self, paths: list[str]) -> dict[str, str]:
        """Map importable module names to files, when the language needs it"""

        return {}

    def entry_points(self, server_dir: Path, context: PackageContext) -> set[str]:
        """Return the files the package declares as entry points"""

        return set()

    def entry_functions(self, server_dir: Path, context: PackageContext) -> list[tuple[str, str]]:
        """Return the functions the package declares as entry points, as file and function name"""

        return []

    def install_entries(self, server_dir: Path, context: PackageContext) -> set[str]:
        """Return the source files that install-time scripts run"""

        return set()

    def language_for(self, analyzed: list[str]) -> str:
        """Return the language name to report for the analyzed files"""

        return self.language

    def analyze(self, server_dir: Path) -> ServerAnalysis:
        """Analyze every source file of a server folder"""

        analysis = ServerAnalysis(path=".", language=self.language)
        sources: list[tuple[str, Path]] = []
        for path in iter_files(server_dir):
            if not self.accepts(path):
                continue
            relative = path.relative_to(server_dir).as_posix()
            size = path.stat().st_size
            if size > self.limits.max_source_file_bytes:
                analysis.skipped_files.append(SkippedFile(file=relative, reason=TOO_LARGE_REASON, size=size))
                continue
            sources.append((relative, path))
        paths = [relative for relative, _ in sources]
        context = PackageContext(files=frozenset(paths), modules=self.index_modules(paths))
        reports: dict[str, FileReport] = {}
        for relative, path in sources:
            source = SourceText(path.read_bytes().decode("utf-8", errors="replace"), self.limits)
            reports[relative] = self.analyze_file(relative, source, context)
            if source.is_minified(relative):
                analysis.minified_files.append(relative)
        analysis.files_analyzed = len(reports)
        analysis.language = self.language_for(paths)
        installs = self.install_entries(server_dir, context) & set(reports)
        locations = self._locations(server_dir, context, reports, installs)
        entries = [
            (path, name) for path, name in self.entry_functions(server_dir, context) if path in reports
        ]
        self._assemble(analysis, reports, locations, _Starts(entries, installs))
        self._add_install_scripts(analysis, server_dir)
        for tool in analysis.tools:
            tool.findings.sort(key=lambda finding: (len(finding.call_chain), finding.file, finding.line))
        analysis.findings.sort(key=lambda finding: (finding.file, finding.line, finding.column))
        return analysis

    def _locations(
        self,
        server_dir: Path,
        context: PackageContext,
        reports: dict[str, FileReport],
        installs: set[str],
    ) -> dict[str, LocationKind]:
        """Classify files, then mark as server code every entry point and every file the server code imports"""

        locations = {path: location_kind(path) for path in reports}
        entries = (self.entry_points(server_dir, context) | installs) & set(reports)
        pending = [path for path, kind in locations.items() if kind is LocationKind.SERVER_CODE]
        pending.extend(sorted(entries))
        visited: set[str] = set()
        while pending:
            path = pending.pop()
            if path in visited or path not in reports:
                continue
            visited.add(path)
            locations[path] = LocationKind.SERVER_CODE
            pending.extend(reports[path].imported_files)
        return locations

    def _add_install_scripts(self, analysis: ServerAnalysis, server_dir: Path) -> None:
        """Record install-time code as findings and as URL sources"""

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
                    outside=OutsideKind.INSTALL,
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

    def _assemble(
        self,
        analysis: ServerAnalysis,
        reports: dict[str, FileReport],
        locations: dict[str, LocationKind],
        starts: _Starts,
    ) -> None:
        """Attach findings to tools through the call graph and keep the rest at server level"""

        graph = CallGraph(reports, self.limits.max_call_depth)
        built: dict[tuple[str, int], Finding] = {}
        slots: list[_ToolSlot] = []
        for path, report in reports.items():
            if report.error_offset is not None:
                line, column = report.source.position(report.error_offset)
                analysis.parse_errors.append(ParseError(file=path, line=line, column=column))
            for raw in report.tools:
                line, _ = report.source.position(raw.offset)
                model = Tool(
                    name=raw.name,
                    name_is_dynamic=raw.name_is_dynamic,
                    description=raw.description.value,
                    description_is_dynamic=raw.description.dynamic,
                    parameters=raw.parameters,
                    parameters_are_dynamic=raw.parameters_are_dynamic,
                    file=path,
                    line=line,
                    declaration=raw.declaration,
                    location_kind=locations[path],
                    annotations=raw.annotations,
                    annotations_are_dynamic=raw.annotations_are_dynamic,
                )
                if raw.title is not None:
                    model.title = raw.title.value
                    model.title_is_dynamic = raw.title.dynamic
                slots.append(_ToolSlot(path, raw, model))
                analysis.tools.append(model)
        shared, shared_scopes = self._attach_handlers(graph, reports, slots)
        reached: set[tuple[str, int]] = set()
        scopes: list[ToolScope] = []
        for slot in slots:
            roots = [Region(slot.file, start, end) for start, end in slot.raw.bodies] + slot.regions
            for entry in slot.raw.entries:
                target = graph.resolve(slot.file, entry)
                if target is not None:
                    function = graph.function(*target)
                    roots.append(Region(target[0], function.start, function.end))
            scopes.append(ToolScope(slot.model.name, roots, _tool_parameters(slot)))
            walk = graph.walk(roots)
            slot.model.gaps = sorted(walk.gaps | slot.gaps)
            for reach in walk.reaches:
                finding = self._finding(reports, locations, built, reach.file, reach.index)
                key = (finding.capability, finding.file, finding.line)
                reached.add((reach.file, reach.index))
                if key in slot.seen:
                    continue
                slot.seen.add(key)
                chain = _call_steps(reports, reach.chain)
                slot.model.findings.append(finding.model_copy(update={"call_chain": chain}))
        startup_roots, install_roots = self._start_regions(graph, reports, locations, starts)
        outside = self._outside(graph, startup_roots, install_roots)
        assembler = FlowAssembler(reports, locations, graph, self.limits)
        analysis.flows = assembler.build(scopes + shared_scopes, startup_roots, install_roots)
        server_seen: set[tuple[Capability, str, int]] = set()
        for path, report in reports.items():
            for index in range(len(report.findings)):
                update: dict[str, object] = {}
                if (path, index) in shared:
                    update = {"shared_by_tools": True, "call_chain": shared[(path, index)]}
                elif (path, index) in reached:
                    continue
                elif locations[path] is LocationKind.SERVER_CODE:
                    update = {"outside": outside.get((path, index), OutsideKind.NEVER_CALLED)}
                finding = self._finding(reports, locations, built, path, index)
                key = (finding.capability, finding.file, finding.line)
                if key not in server_seen:
                    server_seen.add(key)
                    analysis.findings.append(finding.model_copy(update=update))
            file_slots = [slot for slot in slots if slot.file == path]
            for raw_string in report.strings:
                self._merge_string(analysis, report, raw_string, file_slots, locations[path])
            self._merge_texts(analysis, report, file_slots, locations[path])

    def _start_regions(
        self,
        graph: CallGraph,
        reports: dict[str, FileReport],
        locations: dict[str, LocationKind],
        starts: _Starts,
    ) -> tuple[list[Region], list[Region]]:
        """Return the code that runs at startup (module level, entry points) and at install time"""

        install_roots = [Region(path, 0, len(reports[path].source.data) + 1) for path in sorted(starts.installs)]
        startup_roots = [
            Region(path, 0, len(report.source.data) + 1, own_body=True)
            for path, report in reports.items()
            if locations[path] is LocationKind.SERVER_CODE and path not in starts.installs
        ]
        for path, name in starts.entries:
            target = graph.resolve(path, RawCall(0, name, path))
            if target is not None:
                function = graph.function(*target)
                startup_roots.append(Region(target[0], function.start, function.end, own_body=True))
        return startup_roots, install_roots

    def _outside(
        self, graph: CallGraph, startup_roots: list[Region], install_roots: list[Region]
    ) -> dict[tuple[str, int], OutsideKind]:
        """Tell which findings run at install time or at startup"""

        kinds: dict[tuple[str, int], OutsideKind] = {}
        for reach in graph.walk(install_roots).reaches:
            kinds.setdefault((reach.file, reach.index), OutsideKind.INSTALL)
        for reach in graph.walk(startup_roots).reaches:
            kinds.setdefault((reach.file, reach.index), OutsideKind.STARTUP)
        return kinds

    def _attach_handlers(
        self,
        graph: CallGraph,
        reports: dict[str, FileReport],
        slots: list[_ToolSlot],
    ) -> tuple[dict[tuple[str, int], list[CallStep]], list[ToolScope]]:
        """Give low-level tools.call handlers to their tools and return what is shared by all"""

        low_level = [slot for slot in slots if slot.raw.declaration is DeclarationKind.LOW_LEVEL]
        shared: dict[tuple[str, int], list[CallStep]] = {}
        scopes: list[ToolScope] = []
        if not low_level:
            return shared, scopes
        for path, report in reports.items():
            for handler in report.call_handlers:
                region = _handler_region(graph, path, handler)
                if region is None:
                    continue
                candidates = [slot for slot in low_level if slot.file == region.file] or low_level
                if len(candidates) == 1:
                    candidates[0].regions.append(region)
                    continue
                by_name: dict[str, _ToolSlot] = {}
                for slot in candidates:
                    by_name.setdefault(slot.model.name, slot)
                branches = []
                for block in reports[region.file].dispatch_blocks:
                    owner = by_name.get(block.literal)
                    if owner is None or not region.start <= block.start < region.end:
                        continue
                    branch = Region(region.file, block.start, block.end)
                    owner.regions.append(branch)
                    branches.append(branch)
                keys = self._attach_table_entries(graph, reports, region, by_name)
                scopes.append(ToolScope(None, [region], None, branches, keys))
                walk = graph.walk([region], branches, keys)
                for slot in candidates:
                    slot.gaps |= walk.gaps
                for reach in walk.reaches:
                    shared.setdefault((reach.file, reach.index), _call_steps(reports, reach.chain))
        return shared, scopes

    def _attach_table_entries(
        self,
        graph: CallGraph,
        reports: dict[str, FileReport],
        region: Region,
        by_name: dict[str, _ToolSlot],
    ) -> frozenset[str]:
        """Give each tool the handler a dispatch table holds under its name, and return the keys handled"""

        keys: set[str] = set()
        for call in reports[region.file].calls:
            if call.key is None or not region.start <= call.offset < region.end:
                continue
            owner = by_name.get(call.key)
            target = graph.resolve(region.file, call)
            if owner is None or target is None:
                continue
            function = graph.function(*target)
            owner.regions.append(Region(target[0], function.start, function.end))
            keys.add(call.key)
        return frozenset(keys)

    def _finding(
        self,
        reports: dict[str, FileReport],
        locations: dict[str, LocationKind],
        built: dict[tuple[str, int], Finding],
        path: str,
        index: int,
    ) -> Finding:
        """Build the model of one raw finding once"""

        key = (path, index)
        if key not in built:
            report = reports[path]
            raw = report.findings[index]
            line, column = report.source.position(raw.offset)
            built[key] = Finding(
                capability=raw.capability,
                file=path,
                line=line,
                column=column,
                snippet=report.source.snippet(raw.offset),
                function=raw.function,
                location_kind=locations[path],
                detail=raw.detail,
                url_kind=raw.url_kind,
                url_host=raw.url_host,
                sends=raw.sends,
            )
        return built[key]

    def _merge_texts(
        self,
        analysis: ServerAnalysis,
        report: FileReport,
        slots: list[_ToolSlot],
        location: LocationKind,
    ) -> None:
        """Record suspicious passages of strings and comments, cc and bcc addresses, and raw bidi controls"""

        source = report.source
        for raw_string in report.strings:
            value = raw_string.value.value
            line, _ = source.position(raw_string.offset)
            for kind, match in (
                (TextMatchKind.PIPE_TO_SHELL, PIPE_TO_SHELL.search(value)),
                (TextMatchKind.ANALYZER_TALK, analyzer_talk(value)),
            ):
                if match is not None:
                    analysis.text_matches.append(
                        TextMatch(
                            kind=kind,
                            file=report.path,
                            line=line,
                            quote=excerpt(value, match.start(), match.end()),
                            tool=_tool_name(slots, raw_string.offset),
                            location_kind=location,
                        )
                    )
        for offset, comment in report.comments:
            match = analyzer_talk(comment)
            if match is not None:
                analysis.text_matches.append(
                    TextMatch(
                        kind=TextMatchKind.ANALYZER_TALK,
                        file=report.path,
                        line=source.position(offset)[0],
                        quote=excerpt(comment, match.start(), match.end()),
                        in_comment=True,
                        tool=_tool_name(slots, offset),
                        location_kind=location,
                    )
                )
        for copy in report.copies:
            analysis.copy_recipients.append(
                CopyRecipient(
                    field=copy.field,
                    address=copy.address,
                    file=report.path,
                    line=source.position(copy.offset)[0],
                    quote=source.snippet(copy.offset),
                    tool=_tool_name(slots, copy.offset),
                    location_kind=location,
                )
            )
        for match in RAW_BIDI_PATTERN.finditer(source.text):
            offset = len(source.text[: match.start()].encode("utf-8"))
            line, column = source.position(offset)
            existing = [
                item
                for item in analysis.invisible_unicode
                if (item.file, item.line, item.column, item.category)
                == (report.path, line, column, InvisibleCategory.BIDI_CONTROL)
            ]
            for item in existing:
                item.in_source = True
            if existing:
                continue
            analysis.invisible_unicode.append(
                InvisibleUnicode(
                    file=report.path,
                    line=line,
                    column=column,
                    category=InvisibleCategory.BIDI_CONTROL,
                    codepoints=[codepoint_label(character) for character in match.group(0)],
                    in_source=True,
                    tool=_tool_name(slots, offset),
                    location_kind=location,
                )
            )

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
                    kinds=sorted(path_kinds(category)),
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


def _tool_name(slots: list[_ToolSlot], offset: int) -> str | None:
    """Return the name of the tool whose code or description holds an offset"""

    owner = _owner(slots, offset)
    if owner is None:
        return None
    return owner.model.name


def _tool_parameters(slot: _ToolSlot) -> tuple[str, ...] | None:
    """Return the parameters the AI fills for a tool declared from a function, when they are known"""

    if slot.raw.declaration not in FUNCTION_DECLARATIONS or slot.raw.parameters_are_dynamic:
        return None
    return tuple(parameter.name for parameter in slot.raw.parameters)


def _handler_region(graph: CallGraph, path: str, handler: RawHandler) -> Region | None:
    """Return the source range of a handler, following a reference through the call graph"""

    if handler.reference is None:
        return Region(path, handler.start, handler.end)
    target = graph.resolve(path, handler.reference)
    if target is None:
        return None
    function = graph.function(*target)
    return Region(target[0], function.start, function.end)


def _call_steps(reports: dict[str, FileReport], chain: tuple[Step, ...]) -> list[CallStep]:
    """Turn graph steps into call steps with line numbers"""

    return [
        CallStep(function=step.function, file=step.file, line=reports[step.file].source.position(step.offset)[0])
        for step in chain
    ]


def _owner(slots: list[_ToolSlot], offset: int) -> _ToolSlot | None:
    """Return the tool whose body or description most tightly contains an offset"""

    best = None
    best_size = 0
    for slot in slots:
        own_regions = [(region.start, region.end) for region in slot.regions if region.file == slot.file]
        for start, end in slot.raw.bodies + own_regions + slot.raw.text_ranges:
            if start <= offset < end:
                size = end - start
                if best is None or size < best_size:
                    best = slot
                    best_size = size
    return best
