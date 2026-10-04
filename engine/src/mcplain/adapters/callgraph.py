"""Approximate call graph of one package, resolved by names, used to attribute findings to tools"""

from bisect import bisect_left
from collections import deque
from dataclasses import dataclass, field

from mcplain.adapters.report import FileReport, RawCall, RawFunction
from mcplain.models import TrackingGap

MAX_EXPORT_HOPS = 3
COMMON_METHOD_NAMES: frozenset[str] = frozenset(
    {
        "add",
        "append",
        "apply",
        "bind",
        "call",
        "catch",
        "clear",
        "close",
        "concat",
        "copy",
        "count",
        "decode",
        "delete",
        "emit",
        "encode",
        "endswith",
        "entries",
        "every",
        "extend",
        "filter",
        "finally",
        "find",
        "flush",
        "forEach",
        "format",
        "get",
        "has",
        "includes",
        "index",
        "indexOf",
        "insert",
        "items",
        "join",
        "json",
        "keys",
        "lower",
        "map",
        "match",
        "on",
        "once",
        "open",
        "pop",
        "push",
        "read",
        "reduce",
        "remove",
        "replace",
        "reverse",
        "run",
        "send",
        "set",
        "setdefault",
        "shift",
        "slice",
        "some",
        "sort",
        "split",
        "start",
        "startswith",
        "stop",
        "strip",
        "test",
        "text",
        "then",
        "toString",
        "trim",
        "update",
        "upper",
        "values",
        "write",
    }
)


@dataclass(frozen=True)
class Region:
    """Class that holds a byte range of one file, optionally without the functions nested in it"""

    file: str
    start: int
    end: int
    own_body: bool = False


@dataclass(frozen=True)
class Step:
    """Class that holds one function crossed on the way to a finding"""

    function: str
    file: str
    offset: int


@dataclass(frozen=True)
class Reach:
    """Class that holds a finding reached from a root, with the functions crossed"""

    file: str
    index: int
    chain: tuple[Step, ...]


@dataclass
class Walk:
    """Class that holds what a walk reached and why it may have missed something"""

    reaches: list[Reach] = field(default_factory=list)
    gaps: set[TrackingGap] = field(default_factory=set)


class CallGraph:
    """Class that resolves calls by name and walks them from tool bodies"""

    def __init__(self, reports: dict[str, FileReport], max_depth: int) -> None:
        """Index functions, findings, calls and gaps of every file by name and offset"""

        self.reports = reports
        self.max_depth = max_depth
        self._names: dict[str, dict[str, list[int]]] = {}
        self._finding_order: dict[str, list[int]] = {}
        self._finding_offsets: dict[str, list[int]] = {}
        self._calls: dict[str, list[RawCall]] = {}
        self._call_offsets: dict[str, list[int]] = {}
        self._method_calls: dict[str, list[RawCall]] = {}
        self._method_offsets: dict[str, list[int]] = {}
        self._gap_offsets: dict[str, list[tuple[int, TrackingGap]]] = {}
        self._ranges: dict[str, list[tuple[int, int]]] = {}
        self.method_names: set[str] = set()
        for path, report in reports.items():
            names: dict[str, list[int]] = {}
            for index, function in enumerate(report.functions):
                names.setdefault(function.name, []).append(index)
                if "." in function.name:
                    self.method_names.add(function.name.rsplit(".", 1)[1])
            self._names[path] = names
            order = sorted(range(len(report.findings)), key=lambda index: report.findings[index].offset)
            self._finding_order[path] = order
            self._finding_offsets[path] = [report.findings[index].offset for index in order]
            calls = sorted(report.calls, key=lambda call: call.offset)
            self._calls[path] = calls
            self._call_offsets[path] = [call.offset for call in calls]
            method_calls = sorted(report.method_calls, key=lambda call: call.offset)
            self._method_calls[path] = method_calls
            self._method_offsets[path] = [call.offset for call in method_calls]
            self._gap_offsets[path] = sorted((gap.offset, gap.gap) for gap in report.gaps)
            self._ranges[path] = sorted(set(report.function_ranges))
        self.method_names -= COMMON_METHOD_NAMES

    def function(self, file: str, index: int) -> RawFunction:
        """Return one indexed function"""

        return self.reports[file].functions[index]

    def resolve(self, file: str, call: RawCall) -> tuple[str, int] | None:
        """Find the function a call refers to, in the same file or in an imported file"""

        if call.file is None:
            return self._local(file, call.name, call.offset)[0]
        return self._exported(call.file, call.name, 0)

    def ambiguous(self, file: str, call: RawCall) -> bool:
        """Tell whether several functions with the same name could answer a call"""

        if call.file is None:
            return self._local(file, call.name, call.offset)[1]
        report = self.reports.get(call.file)
        if report is None:
            return False
        candidates = [
            index
            for index in self._names[call.file].get(call.name, [])
            if report.functions[index].module_level and not report.functions[index].overload
        ]
        return len(candidates) > 1

    def _local(self, file: str, name: str, offset: int) -> tuple[tuple[str, int] | None, bool]:
        """Find the innermost visible function with a name in one file, and tell if it is ambiguous"""

        report = self.reports.get(file)
        if report is None:
            return None, False
        best = None
        best_size = 0
        twins = 0
        for index in self._names[file].get(name, []):
            function = report.functions[index]
            if function.overload or not function.scope_start <= offset < function.scope_end:
                continue
            size = function.scope_end - function.scope_start
            if best is None or size < best_size:
                best = index
                best_size = size
                twins = 1
            elif size == best_size:
                twins += 1
        if best is None:
            return None, False
        return (file, best), twins > 1

    def _exported(self, file: str, name: str, hops: int) -> tuple[str, int] | None:
        """Find a module-level function of a file, following re-exports"""

        report = self.reports.get(file)
        if report is None:
            return None
        for index in self._names[file].get(name, []):
            if report.functions[index].module_level and not report.functions[index].overload:
                return file, index
        if hops >= MAX_EXPORT_HOPS:
            return None
        if name == "default" and report.default_export is not None:
            return self._exported(file, report.default_export, hops + 1)
        if name in report.reexports:
            target_file, target_name = report.reexports[name]
            return self._exported(target_file, target_name, hops + 1)
        for star in report.star_exports:
            found = self._exported(star, name, hops + 1)
            if found is not None:
                return found
        return None

    def _nested(self, region: Region) -> list[tuple[int, int]]:
        """Return the function ranges strictly inside a region, when only its own body counts"""

        if not region.own_body:
            return []
        return [
            (start, end)
            for start, end in self._ranges.get(region.file, [])
            if region.start <= start and end <= region.end and (start, end) != (region.start, region.end)
        ]

    def _between(self, offsets: list[int], region: Region) -> tuple[int, int]:
        """Return the slice of sorted offsets that fall inside a region"""

        return bisect_left(offsets, region.start), bisect_left(offsets, region.end)

    def _findings_in(self, region: Region, nested: list[tuple[int, int]]) -> list[int]:
        """Return the indexes of the findings inside a region"""

        offsets = self._finding_offsets.get(region.file, [])
        order = self._finding_order.get(region.file, [])
        start, end = self._between(offsets, region)
        return [index for index, offset in zip(order[start:end], offsets[start:end]) if not _within(nested, offset)]

    def _calls_in(self, region: Region, nested: list[tuple[int, int]]) -> list[RawCall]:
        """Return the calls inside a region"""

        start, end = self._between(self._call_offsets.get(region.file, []), region)
        return [call for call in self._calls.get(region.file, [])[start:end] if not _within(nested, call.offset)]

    def region_gaps(self, region: Region, skipped: list[Region] | None = None) -> set[TrackingGap]:
        """Return why calls inside one region could not be followed"""

        nested = self._nested(region)
        excluded = skipped or []
        gaps: set[TrackingGap] = set()
        for offset, gap in self._gap_offsets.get(region.file, []):
            if region.start <= offset < region.end and not _within(nested, offset):
                if not _inside(excluded, region.file, offset):
                    gaps.add(gap)
        start, end = self._between(self._method_offsets.get(region.file, []), region)
        for call in self._method_calls.get(region.file, [])[start:end]:
            if call.name in self.method_names and not _within(nested, call.offset):
                if not _inside(excluded, region.file, call.offset):
                    gaps.add(TrackingGap.UNKNOWN_TYPE)
        for call in self._calls_in(region, nested):
            if _inside(excluded, region.file, call.offset):
                continue
            if self.resolve(region.file, call) is None:
                method = call.name.rsplit(".", 1)[-1]
                if "." in call.name and method in self.method_names:
                    gaps.add(TrackingGap.UNKNOWN_TYPE)
            elif self.ambiguous(region.file, call):
                gaps.add(TrackingGap.AMBIGUOUS)
        return gaps

    def walk(
        self,
        roots: list[Region],
        excluded: list[Region] | None = None,
        skipped_keys: frozenset[str] = frozenset(),
    ) -> Walk:
        """Return every finding reachable from the roots, nearest first, and the gaps met on the way"""

        skipped = excluded or []
        result = Walk()
        seen: set[tuple[str, int]] = set()
        visited: set[tuple[str, int]] = set()
        queue: deque[tuple[tuple[str, int], tuple[Step, ...], bool]] = deque()
        for root in roots:
            nested = self._nested(root)
            result.gaps |= self.region_gaps(root, skipped)
            for index in self._findings_in(root, nested):
                offset = self.reports[root.file].findings[index].offset
                if (root.file, index) not in seen and not _inside(skipped, root.file, offset):
                    seen.add((root.file, index))
                    result.reaches.append(Reach(root.file, index, ()))
            for call in self._calls_in(root, nested):
                if _inside(skipped, root.file, call.offset) or call.key in skipped_keys:
                    continue
                self._enqueue(root.file, call, (), visited, queue, root.own_body)
        while queue:
            target, chain, own_body = queue.popleft()
            file, index = target
            function = self.function(file, index)
            region = Region(file, function.start, function.end, own_body)
            nested = self._nested(region)
            result.gaps |= self.region_gaps(region)
            for finding_index in self._findings_in(region, nested):
                if (file, finding_index) not in seen:
                    seen.add((file, finding_index))
                    result.reaches.append(Reach(file, finding_index, chain))
            calls = self._calls_in(region, nested)
            if len(chain) >= self.max_depth:
                if any(self._unvisited(file, call, visited) for call in calls):
                    result.gaps.add(TrackingGap.MAX_DEPTH)
                continue
            for call in calls:
                self._enqueue(file, call, chain, visited, queue, own_body)
        return result

    def _unvisited(self, file: str, call: RawCall, visited: set[tuple[str, int]]) -> bool:
        """Tell whether a call leads to a function not reached yet"""

        target = self.resolve(file, call)
        return target is not None and target not in visited

    def _enqueue(
        self,
        file: str,
        call: RawCall,
        chain: tuple[Step, ...],
        visited: set[tuple[str, int]],
        queue: deque[tuple[tuple[str, int], tuple[Step, ...], bool]],
        own_body: bool,
    ) -> None:
        """Queue the function a call refers to, once"""

        target = self.resolve(file, call)
        if target is None or target in visited:
            return
        visited.add(target)
        function = self.function(*target)
        queue.append((target, (*chain, Step(function.name, target[0], function.start)), own_body))


def _inside(regions: list[Region], file: str, offset: int) -> bool:
    """Tell whether an offset of a file falls inside one of the regions"""

    return any(region.file == file and region.start <= offset < region.end for region in regions)


def _within(ranges: list[tuple[int, int]], offset: int) -> bool:
    """Tell whether an offset falls inside one of the ranges"""

    return any(start <= offset < end for start, end in ranges)
