"""Language-independent data flow engine: labels travel from sources to sinks, inside and across functions

The adapters lower each function into a small intermediate form (expressions and statements below).
The engine then evaluates it. A value is a set of labels; a label says where the value came from.
When a labelled value reaches a sink, the engine records a hit.

Across functions, each function gets a summary: which of its parameters reach which sink, which
parameters and sources reach its return value. A call maps the caller's labels onto that summary.
The call depth is limited like the call graph.

When in doubt, the engine drops the label (a missed flow) rather than inventing one: unknown library
calls return an unlabelled value, a reassigned variable loses its old labels, closures are not followed.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field, replace

from mcplain.adapters.callgraph import CallGraph, Step
from mcplain.adapters.report import RawCall
from mcplain.capabilities import PathKind, path_kinds
from mcplain.flows import WRITTEN_FILE_SOURCES, FlowSinkKind, FlowSourceKind


class Expr:
    """Class for every expression of the intermediate form"""


@dataclass(frozen=True)
class Empty(Expr):
    """Class for a value that carries no label"""


EMPTY = Empty()


@dataclass(frozen=True)
class Literal(Expr):
    """Class for a string literal, with the sensitive path categories it mentions"""

    text: str
    offset: int
    categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class Name(Expr):
    """Class for a variable, a parameter or an attribute chain like self.client"""

    name: str


@dataclass(frozen=True)
class Source(Expr):
    """Class for a fresh source of labels"""

    kind: FlowSourceKind
    detail: str
    offset: int


@dataclass(frozen=True)
class Union(Expr):
    """Class for a value that mixes the labels of its parts"""

    parts: tuple[Expr, ...]


@dataclass(frozen=True)
class Compose(Expr):
    """Class for a string built from parts in order; a labelled part after other text is pasted"""

    parts: tuple[Expr, ...]


@dataclass(frozen=True)
class Member(Expr):
    """Class for an attribute, a key or an element of a value"""

    value: Expr
    name: str | None


@dataclass(frozen=True)
class Call(Expr):
    """Class for a call to a function of the package, resolved through the call graph"""

    target: RawCall
    arguments: tuple[Expr, ...]
    keywords: tuple[tuple[str, Expr], ...]
    receiver: Expr | None
    offset: int


@dataclass(frozen=True)
class SinkSpec:
    """Class for a sink used by an operation, fed by some of its inputs"""

    kind: FlowSinkKind
    role: str
    inputs: tuple[int, ...]
    detail: str
    offset: int
    target: tuple[str, ...] = ()


@dataclass(frozen=True)
class Result:
    """Class that says how an operation computes its value from its inputs"""

    kind: str
    inputs: tuple[int, ...] = ()
    source: FlowSourceKind | None = None
    detail: str = ""


NO_RESULT = Result("none")


@dataclass(frozen=True)
class Callback:
    """Class for an inline function evaluated where it is written, with its parameters bound"""

    parameters: tuple[str, ...]
    bindings: tuple[int | None, ...]
    body: tuple["Stmt", ...]
    resolver: str | None = None
    returns: bool = False
    source: FlowSourceKind | None = None
    detail: str = ""


@dataclass(frozen=True)
class Operation(Expr):
    """Class for a library call or an operator: inputs evaluated once, then sinks, updates and result"""

    inputs: tuple[Expr, ...]
    offset: int
    sinks: tuple[SinkSpec, ...] = ()
    result: Result = NO_RESULT
    updates: tuple[tuple[str, tuple[int, ...]], ...] = ()
    callbacks: tuple[Callback, ...] = ()


@dataclass(frozen=True)
class Comprehension(Expr):
    """Class for a comprehension: loop variables bound to iterables, then the element expression"""

    bindings: tuple[tuple[tuple[str, ...], Expr], ...]
    body: Expr


@dataclass(frozen=True)
class Assigned(Expr):
    """Class for an assignment used as a value"""

    targets: tuple[tuple[str, bool], ...]
    value: Expr


@dataclass(frozen=True)
class Resolve(Expr):
    """Class for a call to the resolve function of a Promise executor, which gives its result"""

    value: Expr


class Stmt:
    """Class for every statement of the intermediate form"""


@dataclass(frozen=True)
class Assign(Stmt):
    """Class for an assignment; a weak target keeps its old labels"""

    targets: tuple[tuple[str, bool], ...]
    value: Expr


@dataclass(frozen=True)
class Evaluate(Stmt):
    """Class for an expression evaluated for its effects"""

    value: Expr


@dataclass(frozen=True)
class Return(Stmt):
    """Class for a return statement"""

    value: Expr


@dataclass(frozen=True)
class Branch(Stmt):
    """Class for alternative blocks; when not complete, the code may also skip all of them"""

    arms: tuple[tuple[Stmt, ...], ...]
    complete: bool


@dataclass(frozen=True)
class Loop(Stmt):
    """Class for a loop body, which may run or not"""

    body: tuple[Stmt, ...]


@dataclass(frozen=True)
class FlowFunction:
    """Class for one function in the intermediate form, or the module-level code of a file"""

    file: str
    start: int
    end: int
    name: str | None
    parameters: tuple[str, ...]
    body: tuple[Stmt, ...]
    method: bool = False
    module: bool = False


@dataclass(frozen=True)
class Label:
    """Class that says where a value came from; steps list the functions crossed and are not compared"""

    kind: FlowSourceKind | None
    detail: str
    file: str
    offset: int
    parameter: int = -1
    whole: bool = False
    pasted: bool = False
    decoded: bool = False
    written: bool = False
    kinds: frozenset[PathKind] = frozenset()
    steps: tuple[Step, ...] = field(default=(), compare=False)


@dataclass(frozen=True)
class Hit:
    """Class for a labelled value that reached a sink"""

    label: Label
    sink: SinkSpec
    file: str
    function: str | None
    root: int


@dataclass
class Summary:
    """Class that holds what a function does with its parameters and sources"""

    returns: frozenset[Label] = frozenset()
    hits: list[Hit] = field(default_factory=list)


LITERAL_PATH_PREFIX = "$path:"
MAX_LITERAL_PATH = 260


def looks_like_path(text: str) -> bool:
    """Tell whether a literal looks like a file path, so that a file written there can be followed"""

    return 0 < len(text) <= MAX_LITERAL_PATH and ("/" in text or "\\" in text) and not any(
        character.isspace() for character in text
    )


def literal_path(text: str) -> str:
    """Return the variable name the engine uses for a file written at a literal path"""

    return LITERAL_PATH_PREFIX + text


Labels = frozenset[Label]
NO_LABELS: Labels = frozenset()
FUNCTION_KEY = tuple[str, int]


@dataclass
class _Frame:
    """Class that holds the state of one function being evaluated"""

    function: FlowFunction
    depth: int
    hits: list[Hit] = field(default_factory=list)
    returns: set[Label] = field(default_factory=set)
    root: int | None = None
    resolved: set[Label] | None = None


class FlowEngine:
    """Class that evaluates the intermediate form of a package and summarizes its functions"""

    def __init__(self, functions: list[FlowFunction], graph: CallGraph, max_depth: int) -> None:
        """Index the functions by file and start offset"""

        self.functions: dict[FUNCTION_KEY, FlowFunction] = {}
        self.modules: dict[str, FlowFunction] = {}
        for function in functions:
            if function.module:
                self.modules[function.file] = function
            else:
                self.functions[(function.file, function.start)] = function
        self.graph = graph
        self.max_depth = max_depth
        self._summaries: dict[tuple[FUNCTION_KEY, int], Summary] = {}
        self._active: set[FUNCTION_KEY] = set()
        self._globals: dict[str, dict[str, Labels]] = {}
        self._module_hits: dict[str, list[Hit]] = {}

    def module_hits(self, file: str) -> list[Hit]:
        """Return the hits of the module-level code of a file"""

        self._module_env(file)
        return self._module_hits.get(file, [])

    def _module_env(self, file: str) -> dict[str, Labels]:
        """Evaluate the module-level code of a file once and keep its variables"""

        if file in self._globals:
            return self._globals[file]
        self._globals[file] = {}
        module = self.modules.get(file)
        if module is None:
            return self._globals[file]
        frame = _Frame(module, 0)
        env: dict[str, Labels] = {}
        self._block(module.body, env, frame)
        self._globals[file] = env
        self._module_hits[file] = frame.hits
        return env

    def summary(self, key: FUNCTION_KEY, depth: int = 0) -> Summary | None:
        """Return the summary of a function, computed once per depth"""

        function = self.functions.get(key)
        if function is None:
            return None
        memo = (key, depth)
        if memo in self._summaries:
            return self._summaries[memo]
        if key in self._active:
            return None
        self._active.add(key)
        try:
            bindings = [
                frozenset({Label(None, name, function.file, function.start, parameter=index, whole=True)})
                for index, name in enumerate(function.parameters)
            ]
            summary = self.evaluate(function, bindings, depth)
        finally:
            self._active.discard(key)
        self._summaries[memo] = summary
        return summary

    def evaluate(self, function: FlowFunction, bindings: list[Labels], depth: int) -> Summary:
        """Evaluate a function with given labels for its parameters"""

        self._module_env(function.file)
        frame = _Frame(function, depth)
        env: dict[str, Labels] = {}
        for name, labels in zip(function.parameters, bindings):
            env[name] = labels
        self._block(function.body, env, frame)
        return Summary(frozenset(frame.returns), frame.hits)

    def _block(self, statements: tuple[Stmt, ...], env: dict[str, Labels], frame: _Frame) -> None:
        """Run statements in order"""

        for statement in statements:
            self._statement(statement, env, frame)

    def _statement(self, statement: Stmt, env: dict[str, Labels], frame: _Frame) -> None:
        """Run one statement"""

        if isinstance(statement, Assign):
            self._assign(statement.targets, self._expr(statement.value, env, frame), env)
        elif isinstance(statement, Evaluate):
            self._expr(statement.value, env, frame)
        elif isinstance(statement, Return):
            frame.returns.update(self._expr(statement.value, env, frame))
        elif isinstance(statement, Branch):
            states = []
            for arm in statement.arms:
                arm_env = dict(env)
                self._block(arm, arm_env, frame)
                states.append(arm_env)
            if not statement.complete or not states:
                states.append(dict(env))
            env.clear()
            env.update(_merge(states))
        elif isinstance(statement, Loop):
            body_env = dict(env)
            self._block(statement.body, body_env, frame)
            merged = _merge([env, body_env])
            env.clear()
            env.update(merged)

    def _assign(self, targets: tuple[tuple[str, bool], ...], labels: Labels, env: dict[str, Labels]) -> None:
        """Bind labels to targets, replacing or adding to their old labels"""

        for name, weak in targets:
            if weak:
                env[name] = env.get(name, NO_LABELS) | labels
            else:
                env[name] = labels

    def _lookup(self, name: str, env: dict[str, Labels], frame: _Frame) -> Labels:
        """Return the labels of a variable, then of a module-level variable of the same file"""

        if name in env:
            return env[name]
        if frame.function.module:
            return NO_LABELS
        return self._globals.get(frame.function.file, {}).get(name, NO_LABELS)

    def _expr(self, expr: Expr, env: dict[str, Labels], frame: _Frame) -> Labels:
        """Return the labels of an expression and record the hits it causes"""

        if isinstance(expr, Name):
            return self._lookup(expr.name, env, frame)
        if isinstance(expr, Literal):
            return frozenset(
                Label(
                    FlowSourceKind.SENSITIVE_PATH,
                    category,
                    frame.function.file,
                    expr.offset,
                    kinds=path_kinds(category),
                )
                for category in expr.categories
            )
        if isinstance(expr, Source):
            return frozenset({Label(expr.kind, expr.detail, frame.function.file, expr.offset)})
        if isinstance(expr, Union):
            return _union(self._expr(part, env, frame) for part in expr.parts)
        if isinstance(expr, Compose):
            return self._compose(expr.parts, [self._expr(part, env, frame) for part in expr.parts])
        if isinstance(expr, Member):
            labels = self._expr(expr.value, env, frame)
            if expr.name is None:
                return labels
            return frozenset(_refine(label, expr.name) for label in labels)
        if isinstance(expr, Call):
            return self._call(expr, env, frame)
        if isinstance(expr, Operation):
            return self._operation(expr, env, frame)
        if isinstance(expr, Comprehension):
            inner = dict(env)
            for targets, iterable in expr.bindings:
                labels = self._expr(iterable, inner, frame)
                for target in targets:
                    inner[target] = labels
            return self._expr(expr.body, inner, frame)
        if isinstance(expr, Assigned):
            labels = self._expr(expr.value, env, frame)
            self._assign(expr.targets, labels, env)
            return labels
        if isinstance(expr, Resolve):
            target = frame.returns
            if frame.resolved is not None:
                target = frame.resolved
            target.update(self._expr(expr.value, env, frame))
            return NO_LABELS
        return NO_LABELS

    def _compose(self, parts: tuple[Expr, ...], values: list[Labels]) -> Labels:
        """Join the labels of string parts, marking as pasted those that come after other text"""

        result: set[Label] = set()
        before = False
        for part, labels in zip(parts, values):
            if before:
                result.update(replace(label, pasted=True) for label in labels)
            else:
                result.update(labels)
            if isinstance(part, Literal):
                before = before or bool(part.text)
            elif not isinstance(part, Empty) and not labels:
                before = True
        return frozenset(result)

    def _operation(self, operation: Operation, env: dict[str, Labels], frame: _Frame) -> Labels:
        """Evaluate a library call or an operator"""

        values = [self._expr(item, env, frame) for item in operation.inputs]
        callback_labels: set[Label] = set()
        for callback in operation.callbacks:
            returned = self._callback(callback, values, operation.offset, env, frame)
            if callback.returns:
                callback_labels.update(returned)
        for sink in operation.sinks:
            labels = _union(values[index] for index in sink.inputs if index < len(values))
            self._sink(sink, labels, env, frame)
        for name, indexes in operation.updates:
            env[name] = env.get(name, NO_LABELS) | _union(values[index] for index in indexes if index < len(values))
        return frozenset(callback_labels) | self._result(operation, values, frame)

    def _result(self, operation: Operation, values: list[Labels], frame: _Frame) -> Labels:
        """Compute the value of an operation from its evaluated inputs"""

        result = operation.result
        labels = _union(values[index] for index in result.inputs if index < len(values))
        if result.kind == "union":
            return labels
        if result.kind == "compose":
            parts = tuple(operation.inputs[index] for index in result.inputs if index < len(values))
            return self._compose(parts, [values[index] for index in result.inputs if index < len(values)])
        if result.kind == "read":
            return frozenset(
                Label(FlowSourceKind.SENSITIVE_FILE, label.detail, frame.function.file, operation.offset, kinds=label.kinds)
                for label in labels
                if label.kind is FlowSourceKind.SENSITIVE_PATH
            )
        if result.kind == "decode":
            return frozenset(replace(label, decoded=True) for label in labels)
        if result.kind == "source" and result.source is not None:
            return frozenset({Label(result.source, result.detail, frame.function.file, operation.offset)})
        return NO_LABELS

    def _callback(
        self, callback: Callback, values: list[Labels], offset: int, env: dict[str, Labels], frame: _Frame
    ) -> Labels:
        """Run an inline function with its parameters bound, in the scope where it is written"""

        for name, binding in zip(callback.parameters, callback.bindings):
            if binding is not None and binding < len(values):
                env[name] = values[binding]
            elif callback.source is not None and binding is None and name == callback.parameters[0]:
                env[name] = frozenset({Label(callback.source, callback.detail, frame.function.file, offset)})
            else:
                env[name] = NO_LABELS
        resolved = frame.resolved
        if callback.resolver is not None:
            resolved = set()
        inner = _Frame(frame.function, frame.depth, frame.hits, set(), frame.root, resolved)
        self._block(callback.body, env, inner)
        if callback.resolver is not None and resolved is not None:
            return frozenset(inner.returns | resolved)
        return frozenset(inner.returns)

    def _sink(self, sink: SinkSpec, labels: Labels, env: dict[str, Labels], frame: _Frame) -> None:
        """Record the hits of labels that reach a sink, and mark files written from tracked content"""

        root = frame.root if frame.root is not None else sink.offset
        for label in labels:
            if label.written:
                if sink.kind in (FlowSinkKind.RUN_FILE, FlowSinkKind.CODE) or (
                    sink.kind is FlowSinkKind.PROCESS and sink.role != "arguments"
                ):
                    run = replace(sink, kind=FlowSinkKind.RUN_FILE)
                    frame.hits.append(Hit(label, run, frame.function.file, frame.function.name, root))
                continue
            frame.hits.append(Hit(label, sink, frame.function.file, frame.function.name, root))
        if sink.kind is FlowSinkKind.FILE_WRITE and sink.target:
            written = {
                replace(label, written=True)
                for label in labels
                if label.kind in WRITTEN_FILE_SOURCES and not label.written
            }
            for name in sink.target:
                env[name] = env.get(name, NO_LABELS) | frozenset(written)

    def _call(self, call: Call, env: dict[str, Labels], frame: _Frame) -> Labels:
        """Map the caller's labels onto the summary of a called package function"""

        arguments = [self._expr(argument, env, frame) for argument in call.arguments]
        keywords = {name: self._expr(value, env, frame) for name, value in call.keywords}
        receiver = NO_LABELS
        if call.receiver is not None:
            receiver = self._expr(call.receiver, env, frame)
        target = self.graph.resolve(frame.function.file, call.target)
        if target is None or frame.depth + 1 > self.max_depth:
            return NO_LABELS
        function = self.graph.function(*target)
        key = (target[0], function.start)
        callee = self.functions.get(key)
        summary = self.summary(key, frame.depth + 1)
        if callee is None or summary is None:
            return NO_LABELS
        bound = self._bind(callee, call, arguments, keywords, receiver)
        step = Step(function.name, frame.function.file, call.offset)
        for hit in summary.hits:
            if hit.label.parameter < 0:
                continue
            for label in bound.get(hit.label.parameter, NO_LABELS):
                frame.hits.append(Hit(_through(label, hit.label, step), hit.sink, hit.file, hit.function, call.offset))
        result: set[Label] = set()
        for label in summary.returns:
            if label.parameter >= 0:
                result.update(_through(item, label, step) for item in bound.get(label.parameter, NO_LABELS))
            else:
                result.add(replace(label, steps=(step, *label.steps)))
        return frozenset(result)

    def _bind(
        self,
        callee: FlowFunction,
        call: Call,
        arguments: list[Labels],
        keywords: dict[str, Labels],
        receiver: Labels,
    ) -> dict[int, Labels]:
        """Match the arguments of a call with the parameters of the called function"""

        bound: dict[int, Labels] = {}
        shift = 0
        if callee.method and call.receiver is not None:
            bound[0] = receiver
            shift = 1
        for index, labels in enumerate(arguments):
            if index + shift < len(callee.parameters):
                bound[index + shift] = labels
        for name, labels in keywords.items():
            if name in callee.parameters:
                bound[callee.parameters.index(name)] = labels
        return bound

    def iter_functions(self) -> Iterator[FlowFunction]:
        """Yield every function of the package"""

        yield from self.functions.values()


def _union(groups: Iterator[Labels] | list[Labels]) -> Labels:
    """Return the union of label sets"""

    result: set[Label] = set()
    for group in groups:
        result.update(group)
    return frozenset(result)


def _merge(states: list[dict[str, Labels]]) -> dict[str, Labels]:
    """Merge variable states coming from several paths"""

    merged: dict[str, Labels] = {}
    for state in states:
        for name, labels in state.items():
            merged[name] = merged.get(name, NO_LABELS) | labels
    return merged


def _refine(label: Label, name: str) -> Label:
    """Name the field read from a whole tool arguments object"""

    if not label.whole:
        return label
    return replace(label, detail=name, whole=False)


def _through(label: Label, inner: Label, step: Step) -> Label:
    """Carry a caller label through a callee label met at a sink or a return"""

    detail = label.detail
    whole = label.whole
    if label.whole and not inner.whole:
        detail = inner.detail
        whole = False
    return replace(
        label,
        detail=detail,
        whole=whole,
        pasted=label.pasted or inner.pasted,
        decoded=label.decoded or inner.decoded,
        written=label.written or inner.written,
        steps=(*label.steps, step, *inner.steps),
    )
