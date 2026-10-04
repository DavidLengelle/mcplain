"""Assembly of data flows: run the engine, attribute each flow to a tool or to code outside the tools"""

from dataclasses import dataclass, field

from mcplain.adapters.callgraph import CallGraph, Region, Step
from mcplain.adapters.dataflow import FlowEngine, FlowFunction, Hit, Label, Summary
from mcplain.adapters.report import FileReport
from mcplain.config import Limits
from mcplain.flows import RELEVANT_FLOWS, FlowSourceKind
from mcplain.models import CallStep, Flow, FlowPoint, LocationKind, OutsideKind

PYTHON_SUFFIX = ".py"
RECEIVER_NAMES: frozenset[str] = frozenset({"self", "cls"})


@dataclass(frozen=True)
class ToolScope:
    """Class that describes where a tool's code starts and which parameters the AI fills"""

    name: str | None
    regions: list[Region]
    parameters: tuple[str, ...] | None = None
    excluded: list[Region] = field(default_factory=list)
    skipped_keys: frozenset[str] = frozenset()


FlowKey = tuple[object, ...]


class FlowAssembler:
    """Class that turns the engine hits of a package into attributed flows"""

    def __init__(
        self,
        reports: dict[str, FileReport],
        locations: dict[str, LocationKind],
        graph: CallGraph,
        limits: Limits,
    ) -> None:
        """Index the lowered functions of every file and prepare the engine"""

        self.reports = reports
        self.locations = locations
        self.graph = graph
        functions = [function for report in reports.values() for function in report.flow_functions]
        self.engine = FlowEngine(functions, graph, limits.max_call_depth)
        self.by_file: dict[str, list[FlowFunction]] = {}
        for function in functions:
            if not function.module:
                self.by_file.setdefault(function.file, []).append(function)

    def build(
        self,
        scopes: list[ToolScope],
        startup_roots: list[Region],
        install_roots: list[Region],
    ) -> list[Flow]:
        """Return every relevant flow, attributed to its tool, to shared code, or to code outside the tools"""

        flows: list[Flow] = []
        attributed: set[FlowKey] = set()
        seen: set[tuple[FlowKey, str | None, bool]] = set()
        for scope in scopes:
            for key, flow in self._scope_flows(scope):
                marker = (key, flow.tool, flow.shared_by_tools)
                attributed.add(key)
                if marker not in seen:
                    seen.add(marker)
                    flows.append(flow)
        install = self.graph.reach(install_roots)
        startup = self.graph.reach(startup_roots)
        for function, hit in self._all_hits():
            key = _key(hit.label, hit)
            if key in attributed:
                continue
            attributed.add(key)
            outside = self._outside_kind(function, hit, install, startup)
            flow = self._flow(hit.label, hit, (), None, False, outside)
            if flow is not None:
                flows.append(flow)
        return flows

    def _all_hits(self) -> list[tuple[FlowFunction | None, Hit]]:
        """Return the hits of module-level code and of every function, without parameter labels"""

        hits: list[tuple[FlowFunction | None, Hit]] = []
        for file in self.reports:
            hits.extend((None, hit) for hit in self.engine.module_hits(file))
        for functions in self.by_file.values():
            for function in functions:
                summary = self.engine.summary((function.file, function.start))
                if summary is None:
                    continue
                hits.extend((function, hit) for hit in summary.hits if hit.label.parameter < 0)
        return hits

    def _outside_kind(
        self,
        function: FlowFunction | None,
        hit: Hit,
        install: list[tuple[Region, tuple[Step, ...]]],
        startup: list[tuple[Region, tuple[Step, ...]]],
    ) -> OutsideKind:
        """Tell when code outside the tools runs, from the regions reached at install time and at startup"""

        start = hit.sink.offset
        if function is not None:
            start = function.start
        for region, _ in install:
            if region.file == hit.file and region.start <= start < region.end:
                return OutsideKind.INSTALL
        if function is None:
            return OutsideKind.STARTUP
        for region, _ in startup:
            if region.file == function.file and region.start <= function.start < region.end:
                if not region.own_body or function.start == region.start:
                    return OutsideKind.STARTUP
        return OutsideKind.NEVER_CALLED

    def _scope_flows(self, scope: ToolScope) -> list[tuple[FlowKey, Flow]]:
        """Return the flows a tool or a shared handler reaches, with its parameters as sources"""

        found: list[tuple[FlowKey, Flow]] = []
        shared = scope.name is None
        for region, chain in self.graph.reach(scope.regions, scope.excluded, scope.skipped_keys):
            root = self._function_at(region)
            enclosing = root or self._enclosing(region)
            for function in self._functions_inside(region):
                summary = self.engine.summary((function.file, function.start))
                if summary is None:
                    continue
                inside_root = function is enclosing
                for hit in summary.hits:
                    if inside_root and not self._kept(region, root, hit, scope):
                        continue
                    label = hit.label
                    if label.parameter >= 0:
                        if not (inside_root and not chain):
                            continue
                        parameter = self._tool_parameter(function, label, scope)
                        if parameter is None:
                            continue
                        label = parameter
                    flow = self._flow(label, hit, chain, scope.name, shared, None)
                    if flow is not None:
                        found.append((_key(label, hit), flow))
        return found

    def _kept(self, region: Region, root: FlowFunction | None, hit: Hit, scope: ToolScope) -> bool:
        """Keep a hit of the enclosing function only when it starts inside the region and not in an excluded branch"""

        if root is None and not region.start <= hit.root < region.end:
            return False
        return not any(
            branch.file == region.file and branch.start <= hit.root < branch.end for branch in scope.excluded
        )

    def _functions_inside(self, region: Region) -> list[FlowFunction]:
        """Return the lowered functions inside a region, and the function that encloses a branch region"""

        functions = [
            function
            for function in self.by_file.get(region.file, [])
            if region.start <= function.start and function.end <= region.end
        ]
        if self._function_at(region) is None:
            enclosing = self._enclosing(region)
            if enclosing is not None:
                functions.insert(0, enclosing)
        return functions

    def _function_at(self, region: Region) -> FlowFunction | None:
        """Return the lowered function that starts where a region starts"""

        for function in self.by_file.get(region.file, []):
            if function.start == region.start:
                return function
        return None

    def _enclosing(self, region: Region) -> FlowFunction | None:
        """Return the innermost lowered function that contains a region"""

        best = None
        for function in self.by_file.get(region.file, []):
            if function.start <= region.start and region.end <= function.end:
                if best is None or function.end - function.start < best.end - best.start:
                    best = function
        return best

    def _tool_parameter(self, function: FlowFunction, label: Label, scope: ToolScope) -> Label | None:
        """Turn a parameter label of a tool's root function into a tool parameter source"""

        index = label.parameter
        if index >= len(function.parameters):
            return None
        name = function.parameters[index]
        whole = True
        if function.file.endswith(PYTHON_SUFFIX):
            if name in RECEIVER_NAMES:
                return None
            if scope.parameters is not None:
                if name not in scope.parameters:
                    return None
                whole = False
        elif index != 0:
            return None
        detail = name
        if whole and not label.whole:
            detail = label.detail
            whole = False
        return Label(
            FlowSourceKind.TOOL_PARAMETER,
            detail,
            function.file,
            function.start,
            whole=whole,
            pasted=label.pasted,
            decoded=label.decoded,
            written=label.written,
            steps=label.steps,
        )

    def _flow(
        self,
        label: Label,
        hit: Hit,
        prefix: tuple[Step, ...],
        tool: str | None,
        shared: bool,
        outside: OutsideKind | None,
    ) -> Flow | None:
        """Build the model of one relevant flow"""

        if label.kind is None or (label.kind, hit.sink.kind) not in RELEVANT_FLOWS:
            return None
        sink_report = self.reports.get(hit.file)
        source_report = self.reports.get(label.file)
        if sink_report is None or source_report is None:
            return None
        steps = [
            CallStep(function=step.function, file=step.file, line=self.reports[step.file].source.position(step.offset)[0])
            for step in (*prefix, *label.steps)
            if step.file in self.reports
        ]
        return Flow(
            source=label.kind,
            source_detail=label.detail,
            path_kinds=sorted(label.kinds),
            source_point=self._point(source_report, label.offset),
            sink=hit.sink.kind,
            sink_role=hit.sink.role,
            sink_detail=hit.sink.detail,
            sink_point=self._point(sink_report, hit.sink.offset),
            steps=steps,
            pasted=label.pasted,
            decoded=label.decoded,
            written_file=label.written,
            tool=tool,
            shared_by_tools=shared,
            outside=outside,
            location_kind=self.locations.get(hit.file, LocationKind.SERVER_CODE),
        )

    def _point(self, report: FileReport, offset: int) -> FlowPoint:
        """Locate one end of a flow"""

        line, _ = report.source.position(offset)
        function = None
        size = 0
        for item in report.functions:
            if item.start <= offset < item.end and (function is None or item.end - item.start < size):
                function = item.name
                size = item.end - item.start
        return FlowPoint(file=report.path, line=line, function=function, snippet=report.source.snippet(offset))

    def summary(self, function: FlowFunction) -> Summary | None:
        """Return the summary of one lowered function"""

        return self.engine.summary((function.file, function.start))


def _key(label: Label, hit: Hit) -> FlowKey:
    """Identify a flow by its source, its sink and how the value was shaped on the way"""

    return (
        label.kind,
        label.detail,
        label.file,
        label.offset,
        hit.sink.kind,
        hit.sink.role,
        hit.file,
        hit.sink.offset,
        label.pasted,
        label.decoded,
        label.written,
    )
