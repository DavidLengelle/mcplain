"""Approximate call graph of one package, resolved by names, used to attribute findings to tools"""

from bisect import bisect_left
from collections import deque
from dataclasses import dataclass

from mcplain.adapters.report import FileReport, RawCall, RawFunction

MAX_EXPORT_HOPS = 3


@dataclass(frozen=True)
class Region:
    """Class that holds a byte range of one file"""

    file: str
    start: int
    end: int


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


class CallGraph:
    """Class that resolves calls by name and walks them from tool bodies"""

    def __init__(self, reports: dict[str, FileReport], max_depth: int) -> None:
        """Index functions, findings and calls of every file by name and offset"""

        self.reports = reports
        self.max_depth = max_depth
        self._names: dict[str, dict[str, list[int]]] = {}
        self._finding_order: dict[str, list[int]] = {}
        self._finding_offsets: dict[str, list[int]] = {}
        self._calls: dict[str, list[RawCall]] = {}
        self._call_offsets: dict[str, list[int]] = {}
        for path, report in reports.items():
            names: dict[str, list[int]] = {}
            for index, function in enumerate(report.functions):
                names.setdefault(function.name, []).append(index)
            self._names[path] = names
            order = sorted(range(len(report.findings)), key=lambda index: report.findings[index].offset)
            self._finding_order[path] = order
            self._finding_offsets[path] = [report.findings[index].offset for index in order]
            calls = sorted(report.calls, key=lambda call: call.offset)
            self._calls[path] = calls
            self._call_offsets[path] = [call.offset for call in calls]

    def function(self, file: str, index: int) -> RawFunction:
        """Return one indexed function"""

        return self.reports[file].functions[index]

    def resolve(self, file: str, call: RawCall) -> tuple[str, int] | None:
        """Find the function a call refers to, in the same file or in an imported file"""

        if call.file is None:
            return self._local(file, call.name, call.offset)
        return self._exported(call.file, call.name, 0)

    def _local(self, file: str, name: str, offset: int) -> tuple[str, int] | None:
        """Find the innermost visible function with a name in one file"""

        report = self.reports.get(file)
        if report is None:
            return None
        best = None
        best_size = 0
        for index in self._names[file].get(name, []):
            function = report.functions[index]
            if not function.scope_start <= offset < function.scope_end:
                continue
            size = function.scope_end - function.scope_start
            if best is None or size < best_size:
                best = index
                best_size = size
        if best is None:
            return None
        return file, best

    def _exported(self, file: str, name: str, hops: int) -> tuple[str, int] | None:
        """Find a module-level function of a file, following re-exports"""

        report = self.reports.get(file)
        if report is None:
            return None
        for index in self._names[file].get(name, []):
            if report.functions[index].module_level:
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

    def _findings_in(self, region: Region) -> list[int]:
        """Return the indexes of the findings inside a region"""

        offsets = self._finding_offsets.get(region.file, [])
        order = self._finding_order.get(region.file, [])
        start = bisect_left(offsets, region.start)
        end = bisect_left(offsets, region.end)
        return order[start:end]

    def _calls_in(self, region: Region) -> list[RawCall]:
        """Return the calls inside a region"""

        offsets = self._call_offsets.get(region.file, [])
        start = bisect_left(offsets, region.start)
        end = bisect_left(offsets, region.end)
        return self._calls.get(region.file, [])[start:end]

    def walk(self, roots: list[Region], excluded: list[Region] | None = None) -> list[Reach]:
        """Return every finding reachable from the roots, nearest first, without looping"""

        skipped = excluded or []
        reached: list[Reach] = []
        seen: set[tuple[str, int]] = set()
        visited: set[tuple[str, int]] = set()
        queue: deque[tuple[tuple[str, int], tuple[Step, ...]]] = deque()
        for root in roots:
            for index in self._findings_in(root):
                offset = self.reports[root.file].findings[index].offset
                if (root.file, index) not in seen and not _inside(skipped, root.file, offset):
                    seen.add((root.file, index))
                    reached.append(Reach(root.file, index, ()))
            for call in self._calls_in(root):
                if _inside(skipped, root.file, call.offset):
                    continue
                self._enqueue(root.file, call, (), visited, queue)
        while queue:
            target, chain = queue.popleft()
            file, index = target
            function = self.function(file, index)
            region = Region(file, function.start, function.end)
            for finding_index in self._findings_in(region):
                if (file, finding_index) not in seen:
                    seen.add((file, finding_index))
                    reached.append(Reach(file, finding_index, chain))
            if len(chain) >= self.max_depth:
                continue
            for call in self._calls_in(region):
                self._enqueue(file, call, chain, visited, queue)
        return reached

    def _enqueue(
        self,
        file: str,
        call: RawCall,
        chain: tuple[Step, ...],
        visited: set[tuple[str, int]],
        queue: deque[tuple[tuple[str, int], tuple[Step, ...]]],
    ) -> None:
        """Queue the function a call refers to, once"""

        target = self.resolve(file, call)
        if target is None or target in visited:
            return
        visited.add(target)
        function = self.function(*target)
        queue.append((target, (*chain, Step(function.name, target[0], function.start))))


def _inside(regions: list[Region], file: str, offset: int) -> bool:
    """Tell whether an offset of a file falls inside one of the regions"""

    return any(region.file == file and region.start <= offset < region.end for region in regions)
