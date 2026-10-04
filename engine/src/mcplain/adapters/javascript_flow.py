"""Lowering of JavaScript and TypeScript syntax trees into the data flow intermediate form"""

from typing import TYPE_CHECKING

from tree_sitter import Node

from mcplain.adapters.common import node_text
from mcplain.adapters.dataflow import (
    EMPTY,
    Assign,
    Assigned,
    Branch,
    Call,
    Callback,
    Compose,
    Evaluate,
    Expr,
    FlowFunction,
    Literal,
    Loop,
    Member,
    Name,
    Operation,
    Resolve,
    Result,
    Return,
    SinkSpec,
    Source,
    Stmt,
    Union,
    literal_path,
    looks_like_path,
)
from mcplain.adapters.javascript_syntax import call_arguments, property_name, unwrap
from mcplain.capabilities import (
    JAVASCRIPT_ENV_GETTERS,
    JAVASCRIPT_ENV_OBJECTS,
    JAVASCRIPT_RULES,
    Capability,
    RuleKind,
    find_sensitive_paths,
    match_rule,
)
from mcplain.flows import (
    JAVASCRIPT_BUFFER_FROM,
    JAVASCRIPT_CHARACTER_FUNCTIONS,
    JAVASCRIPT_CODE_CALLS,
    JAVASCRIPT_COPY_CALLS,
    JAVASCRIPT_DECODERS,
    JAVASCRIPT_DECODING_ENCODINGS,
    JAVASCRIPT_ELEMENT_CALLBACKS,
    JAVASCRIPT_HANDLE_WRITE_METHODS,
    JAVASCRIPT_LOADERS,
    JAVASCRIPT_MUTATING_METHODS,
    JAVASCRIPT_PROCESS_CALLS,
    JAVASCRIPT_PROMISE,
    JAVASCRIPT_PROPAGATORS,
    JAVASCRIPT_READ_CALLS,
    JAVASCRIPT_REDUCERS,
    JAVASCRIPT_RESULT_CALLBACKS,
    JAVASCRIPT_RUN_FILE_CALLS,
    JAVASCRIPT_SHELL_CALLS,
    JAVASCRIPT_SHELL_METHODS,
    JAVASCRIPT_SHELL_OPTION,
    JAVASCRIPT_SHELL_OPTION_CALLS,
    JAVASCRIPT_STREAM_CALLS,
    JAVASCRIPT_TIMERS,
    JAVASCRIPT_TOOL_BUILDERS,
    JAVASCRIPT_VALUE_CALLBACKS,
    JAVASCRIPT_WRITE_CALLS,
    ROLE_ARGUMENTS,
    ROLE_CODE,
    ROLE_COMMAND,
    ROLE_CONTENT,
    ROLE_DATA,
    ROLE_DESCRIPTION,
    ROLE_PATH,
    ROLE_PROGRAM,
    FlowSinkKind,
    FlowSourceKind,
)

if TYPE_CHECKING:
    from mcplain.adapters.javascript import _JavaScriptFile

FUNCTION_NODES: tuple[str, ...] = (
    "function_declaration",
    "generator_function_declaration",
    "method_definition",
    "arrow_function",
    "function_expression",
    "generator_function",
)
INLINE_FUNCTIONS: frozenset[str] = frozenset({"arrow_function", "function_expression", "function", "generator_function"})
TEXT_NODES: frozenset[str] = frozenset({"string", "template_string"})
SKIPPED_STATEMENTS: frozenset[str] = frozenset(
    {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "abstract_class_declaration",
        "import_statement",
        "empty_statement",
        "comment",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
        "ambient_declaration",
        "module",
    }
)
DECLARATIONS: frozenset[str] = frozenset({"lexical_declaration", "variable_declaration"})
LEAF_NODES: frozenset[str] = frozenset(
    {
        "number",
        "true",
        "false",
        "null",
        "undefined",
        "regex",
        "arrow_function",
        "function_expression",
        "function",
        "generator_function",
        "class",
        "update_expression",
        "comment",
        "meta_property",
        "super",
    }
)
INNER_NODES: frozenset[str] = frozenset(
    {
        "await_expression",
        "parenthesized_expression",
        "as_expression",
        "satisfies_expression",
        "non_null_expression",
        "spread_element",
        "type_assertion",
    }
)
UNION_OPERATORS: frozenset[str] = frozenset({"||", "??", "&&", "-", "*", "/", "%", "**", "|", "&", "^", "<<", ">>"})
UNLABELLED_UNARY: frozenset[str] = frozenset({"typeof", "!", "void", "delete"})
PARAMETER_WRAPPERS: frozenset[str] = frozenset({"required_parameter", "optional_parameter"})
MIN_CODE_ARRAY = 4
URL_PREFIXES: tuple[str, ...] = ("http://", "https://")


class _Inputs:
    """Class that collects the inputs of an operation and remembers where each argument sits"""

    def __init__(self) -> None:
        """Start with no input"""

        self.items: list[Expr] = []
        self.positional: list[int] = []

    def add(self, expr: Expr) -> int:
        """Add one input and return its index"""

        self.items.append(expr)
        return len(self.items) - 1

    def argument(self, position: int) -> tuple[int, ...]:
        """Return the input of one argument"""

        if position < len(self.positional):
            return (self.positional[position],)
        return ()

    def arguments(self) -> tuple[int, ...]:
        """Return every argument input"""

        return tuple(self.positional)

    def rest(self, position: int) -> tuple[int, ...]:
        """Return the argument inputs from a position on"""

        return tuple(self.positional[position:])


class JavaScriptLowering:
    """Class that lowers the functions of one parsed JavaScript or TypeScript file"""

    def __init__(self, file: "_JavaScriptFile") -> None:
        """Keep the analyzed file and index what the lowering needs"""

        self.file = file
        self.path = file.report.path
        self.names = {function.start: function.name for function in file.report.functions}
        self.descriptions = {tool.description_range for tool in file.report.tools if tool.description_range}
        self.handles: dict[str, Node] = {}
        self.network: set[str] = set()
        self.resolvers: list[str] = []
        self.counter = 0

    def functions(self) -> list[FlowFunction]:
        """Lower the module-level code and every function of the file"""

        self._index_scope(self.file.root)
        result = [
            FlowFunction(
                self.path,
                0,
                len(self.file.source.data) + 1,
                None,
                (),
                self._block(self.file.root.named_children),
                module=True,
            )
        ]
        for node_type in FUNCTION_NODES:
            for node in self.file.nodes.get(node_type, []):
                result.append(self._function(node))
        return result

    def _function(self, node: Node) -> FlowFunction:
        """Lower one function, arrow function or method"""

        self._index_scope(node)
        parameters, prelude = self._parameters(node)
        name = self.names.get(node.start_byte)
        return FlowFunction(
            self.path, node.start_byte, node.end_byte, name, parameters, prelude + self._function_body(node)
        )

    def _function_body(self, node: Node) -> tuple[Stmt, ...]:
        """Lower the body of a function: a block, or the expression an arrow function returns"""

        body = node.child_by_field_name("body")
        if body is None:
            return ()
        if body.type == "statement_block":
            return self._block(body.named_children)
        return (Return(self.expr(body)),)

    def _parameters(self, node: Node) -> tuple[tuple[str, ...], tuple[Stmt, ...]]:
        """Return the parameter names of a function and the assignments that unpack destructured ones"""

        single = node.child_by_field_name("parameter")
        items: list[Node] = []
        if single is not None:
            items = [single]
        else:
            parameters = node.child_by_field_name("parameters")
            if parameters is not None:
                items = [child for child in parameters.named_children if child.type != "comment"]
        names: list[str] = []
        prelude: list[Stmt] = []
        for index, item in enumerate(items):
            pattern = item
            default = None
            if item.type in PARAMETER_WRAPPERS:
                pattern = item.child_by_field_name("pattern") or item
                default = item.child_by_field_name("value")
            elif item.type == "assignment_pattern":
                pattern = item.child_by_field_name("left") or item
                default = item.child_by_field_name("right")
            if pattern.type == "identifier" and default is None:
                names.append(node_text(pattern))
                continue
            name = f"$p{node.start_byte}_{index}"
            if pattern.type == "identifier":
                name = node_text(pattern)
            names.append(name)
            value: Expr = Name(name)
            if default is not None:
                value = Union((value, self.expr(default)))
            if pattern.type != "identifier" or default is not None:
                prelude.extend(self._pattern(pattern, value))
        return tuple(names), tuple(prelude)

    def _index_scope(self, scope: Node) -> None:
        """Remember write streams and network clients created in one scope"""

        self.handles = {}
        self.network = set()
        stack = list(scope.named_children)
        if scope.type in FUNCTION_NODES:
            body = scope.child_by_field_name("body")
            stack = []
            if body is not None:
                stack = [body]
        while stack:
            node = stack.pop()
            if node.type in FUNCTION_NODES or node.type in ("class_declaration", "class"):
                continue
            if node.type == "variable_declarator":
                name = node.child_by_field_name("name")
                value = node.child_by_field_name("value")
                if name is not None and value is not None and name.type == "identifier":
                    self._remember(node_text(name), value)
            elif node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left is not None and right is not None:
                    self._remember(node_text(left), right)
            stack.extend(node.named_children)

    def _remember(self, name: str, value: Node) -> None:
        """Remember that a variable holds a write stream or a network client"""

        current = unwrap(value)
        if current is not None and current.type == "await_expression" and current.named_children:
            current = unwrap(current.named_children[0])
        if current is None or current.type not in ("call_expression", "new_expression"):
            return
        callee = current.child_by_field_name("function") or current.child_by_field_name("constructor")
        resolved = self.file.resolve(callee)
        if resolved is None:
            return
        qualified, imported = resolved
        arguments = call_arguments(current)
        if qualified in JAVASCRIPT_STREAM_CALLS and arguments:
            self.handles[name] = arguments[0]
            return
        kind = RuleKind.GLOBAL
        if imported:
            kind = RuleKind.MODULE
        rule = match_rule(JAVASCRIPT_RULES, qualified, kind)
        if rule is not None and rule.capability is Capability.NETWORK:
            self.network.add(name)

    def _block(self, nodes: list[Node]) -> tuple[Stmt, ...]:
        """Lower a list of statements"""

        statements: list[Stmt] = []
        for node in nodes:
            statements.extend(self._statement(node))
        return tuple(statements)

    def _body(self, node: Node | None) -> tuple[Stmt, ...]:
        """Lower the body of a compound statement, a block or a single statement"""

        if node is None:
            return ()
        if node.type == "statement_block":
            return self._block(node.named_children)
        return self._block([node])

    def _statement(self, node: Node) -> list[Stmt]:
        """Lower one statement"""

        kind = node.type
        if kind in SKIPPED_STATEMENTS:
            return []
        if kind in DECLARATIONS:
            return self._declaration(node)
        if kind == "expression_statement":
            statements: list[Stmt] = []
            for child in node.named_children:
                statements.extend(self._expression_statement(child))
            return statements
        if kind == "return_statement":
            values = [child for child in node.named_children if child.type != "comment"]
            if not values:
                return []
            return [Return(self.expr(values[0]))]
        if kind == "if_statement":
            arms = [self._body(node.child_by_field_name("consequence"))]
            alternative = node.child_by_field_name("alternative")
            if alternative is not None:
                arms.append(self._block([child for child in alternative.named_children]))
            condition = Evaluate(self.expr(node.child_by_field_name("condition")))
            return [condition, Branch(tuple(arms), alternative is not None)]
        if kind == "for_statement":
            return self._for(node)
        if kind == "for_in_statement":
            return self._for_in(node)
        if kind == "while_statement":
            condition = Evaluate(self.expr(node.child_by_field_name("condition")))
            return [Loop((condition, *self._body(node.child_by_field_name("body"))))]
        if kind == "do_statement":
            body = self._body(node.child_by_field_name("body"))
            condition = Evaluate(self.expr(node.child_by_field_name("condition")))
            return [*body, Loop((condition, *body))]
        if kind == "try_statement":
            return self._try(node)
        if kind == "switch_statement":
            arms = []
            body = node.child_by_field_name("body")
            cases: list[Node] = []
            if body is not None:
                cases = list(body.named_children)
            for case in cases:
                arms.append(self._block(case.children_by_field_name("body")))
            return [Evaluate(self.expr(node.child_by_field_name("value"))), Branch(tuple(arms), False)]
        if kind == "statement_block":
            return list(self._block(node.named_children))
        if kind == "labeled_statement":
            return list(self._body(node.child_by_field_name("body")))
        if kind == "throw_statement":
            return [Evaluate(self.expr(child)) for child in node.named_children]
        if kind == "export_statement":
            declaration = node.child_by_field_name("declaration")
            if declaration is not None:
                return self._statement(declaration)
            value = node.child_by_field_name("value")
            if value is not None:
                return [Evaluate(self.expr(value))]
        return []

    def _declaration(self, node: Node) -> list[Stmt]:
        """Lower variable declarations, unpacking destructured names"""

        statements: list[Stmt] = []
        for declarator in node.named_children:
            if declarator.type != "variable_declarator":
                continue
            name = declarator.child_by_field_name("name")
            value = declarator.child_by_field_name("value")
            if name is None:
                continue
            expr = self.expr(value)
            if name.type == "identifier":
                statements.append(Assign(((node_text(name), False),), expr))
                continue
            temporary = self._temporary()
            statements.append(Assign(((temporary, False),), expr))
            statements.extend(self._pattern(name, Name(temporary)))
        return statements

    def _temporary(self) -> str:
        """Return a fresh variable name for an intermediate value"""

        self.counter += 1
        return f"$t{self.counter}"

    def _pattern(self, pattern: Node, value: Expr) -> list[Stmt]:
        """Unpack a destructuring pattern: each name takes the labels of its part of the value"""

        kind = pattern.type
        if kind in ("identifier", "shorthand_property_identifier_pattern"):
            return [Assign(((node_text(pattern), False),), value)]
        if kind == "object_pattern":
            statements: list[Stmt] = []
            for child in pattern.named_children:
                if child.type == "shorthand_property_identifier_pattern":
                    statements.append(Assign(((node_text(child), False),), Member(value, node_text(child))))
                elif child.type == "pair_pattern":
                    key = property_name(child.child_by_field_name("key"))
                    target = child.child_by_field_name("value")
                    if target is not None:
                        statements.extend(self._pattern(target, Member(value, key)))
                elif child.type == "object_assignment_pattern":
                    left = child.child_by_field_name("left")
                    if left is not None:
                        default = self.expr(child.child_by_field_name("right"))
                        member = Member(value, node_text(left))
                        statements.extend(self._pattern(left, Union((member, default))))
                elif child.type == "rest_pattern":
                    statements.extend(self._pattern_children(child, value))
            return statements
        if kind == "array_pattern":
            statements = []
            for child in pattern.named_children:
                statements.extend(self._pattern(child, Member(value, None)))
            return statements
        if kind == "assignment_pattern":
            left = pattern.child_by_field_name("left")
            if left is None:
                return []
            return self._pattern(left, Union((value, self.expr(pattern.child_by_field_name("right")))))
        if kind == "rest_pattern":
            return self._pattern_children(pattern, value)
        if kind in ("member_expression", "subscript_expression"):
            return [Assign(self._targets(pattern), value)]
        return []

    def _pattern_children(self, node: Node, value: Expr) -> list[Stmt]:
        """Unpack the inner pattern of a rest pattern"""

        statements: list[Stmt] = []
        for child in node.named_children:
            statements.extend(self._pattern(child, value))
        return statements

    def _expression_statement(self, node: Node) -> list[Stmt]:
        """Lower an assignment or an expression evaluated for its effects"""

        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None:
                return []
            if left.type in ("object_pattern", "array_pattern"):
                temporary = self._temporary()
                return [Assign(((temporary, False),), self.expr(right)), *self._pattern(left, Name(temporary))]
            return [Assign(self._targets(left), self.expr(right))]
        if node.type == "augmented_assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None:
                return []
            return [Assign(self._targets(left), Compose((self.expr(left), self.expr(right))))]
        return [Evaluate(self.expr(node))]

    def _targets(self, node: Node) -> tuple[tuple[str, bool], ...]:
        """Return the variables an assignment writes; containers and objects keep their old labels"""

        current = unwrap(node)
        if current is None:
            return ()
        if current.type == "identifier":
            return ((node_text(current), False),)
        if current.type == "member_expression":
            target = unwrap(current.child_by_field_name("object"))
            if target is None:
                return ()
            return ((node_text(current), False), (node_text(target), True))
        if current.type == "subscript_expression":
            target = unwrap(current.child_by_field_name("object"))
            if target is None:
                return ()
            return ((node_text(target), True),)
        return ()

    def _for(self, node: Node) -> list[Stmt]:
        """Lower a classic for loop"""

        statements: list[Stmt] = []
        initializer = node.child_by_field_name("initializer")
        if initializer is not None:
            statements.extend(self._statement(initializer))
        body = [
            Evaluate(self.expr(node.child_by_field_name("condition"))),
            *self._body(node.child_by_field_name("body")),
            Evaluate(self.expr(node.child_by_field_name("increment"))),
        ]
        statements.append(Loop(tuple(body)))
        return statements

    def _for_in(self, node: Node) -> list[Stmt]:
        """Lower for...of and for...in: the loop variable takes the labels of the iterated value"""

        temporary = self._temporary()
        statements: list[Stmt] = [Assign(((temporary, False),), self.expr(node.child_by_field_name("right")))]
        left = node.child_by_field_name("left")
        body: list[Stmt] = []
        if left is not None:
            body.extend(self._pattern(left, Member(Name(temporary), None)))
        body.extend(self._body(node.child_by_field_name("body")))
        statements.append(Loop(tuple(body)))
        return statements

    def _try(self, node: Node) -> list[Stmt]:
        """Lower a try statement: the catch block may run or not, then finally"""

        statements = list(self._body(node.child_by_field_name("body")))
        handler = node.child_by_field_name("handler")
        if handler is not None:
            statements.append(Branch((self._body(handler.child_by_field_name("body")),), False))
        finalizer = node.child_by_field_name("finalizer")
        if finalizer is not None:
            statements.extend(self._body(finalizer.child_by_field_name("body")))
        return statements

    def expr(self, node: Node | None) -> Expr:
        """Lower an expression, adding a sink when it computes a tool description"""

        if node is None:
            return EMPTY
        result = self._expr(node)
        if (node.start_byte, node.end_byte) in self.descriptions:
            sink = SinkSpec(FlowSinkKind.TOOL_DESCRIPTION, ROLE_DESCRIPTION, (0,), "description", node.start_byte)
            result = Operation((result,), node.start_byte, (sink,), Result("union", (0,)))
        return result

    def _expr(self, node: Node) -> Expr:
        """Lower an expression by its node type"""

        kind = node.type
        if kind in LEAF_NODES:
            return EMPTY
        if kind in INNER_NODES:
            children = [child for child in node.named_children if child.type != "comment"]
            if not children:
                return EMPTY
            return self.expr(children[0])
        if kind == "identifier":
            name = node_text(node)
            if name in self.file.aliases or name in self.file.internal:
                return EMPTY
            return Name(name)
        if kind == "this":
            return Name("this")
        if kind == "member_expression":
            return self._member(node)
        if kind == "subscript_expression":
            target = node.child_by_field_name("object")
            resolved = self.file.resolve(target)
            if resolved is not None and resolved[0] in JAVASCRIPT_ENV_OBJECTS:
                return EMPTY
            index = unwrap(node.child_by_field_name("index"))
            name = None
            if index is not None and index.type == "string":
                name = self.file._decode_string(index).value
            return Member(self.expr(target), name)
        if kind in ("call_expression", "new_expression"):
            return self._call(node)
        if kind == "string":
            return _literal(self.file._decode_string(node).value, node.start_byte)
        if kind == "template_string":
            return self._template(node)
        if kind == "binary_expression":
            return self._binary(node)
        if kind == "ternary_expression":
            parts = tuple(self.expr(child) for child in node.named_children)
            return Operation(parts, node.start_byte, result=Result("union", (1, 2)))
        if kind == "unary_expression":
            operator = node.child_by_field_name("operator")
            argument = self.expr(node.child_by_field_name("argument"))
            if operator is not None and operator.type in UNLABELLED_UNARY:
                return Operation((argument,), node.start_byte)
            return argument
        if kind == "object":
            return self._object(node)
        if kind == "array":
            return Union(tuple(self.expr(child) for child in node.named_children))
        if kind == "assignment_expression":
            left = node.child_by_field_name("left")
            if left is None:
                return EMPTY
            return Assigned(self._targets(left), self.expr(node.child_by_field_name("right")))
        if kind == "augmented_assignment_expression":
            left = node.child_by_field_name("left")
            if left is None:
                return EMPTY
            value = Compose((self.expr(left), self.expr(node.child_by_field_name("right"))))
            return Assigned(self._targets(left), value)
        if kind == "sequence_expression":
            parts = tuple(self.expr(child) for child in node.named_children)
            return Operation(parts, node.start_byte, result=Result("union", (len(parts) - 1,)))
        return Operation(tuple(self.expr(child) for child in node.named_children), node.start_byte)

    def _member(self, node: Node) -> Expr:
        """Lower a member: process.env is the whole environment, other chains keep their object's labels"""

        resolved = self.file.resolve(node)
        if resolved is not None:
            qualified, imported = resolved
            if qualified in JAVASCRIPT_ENV_OBJECTS:
                return Source(FlowSourceKind.ENVIRONMENT, qualified, node.start_byte)
            if any(qualified.startswith(prefix + ".") for prefix in JAVASCRIPT_ENV_OBJECTS) or imported:
                return EMPTY
        target = node.child_by_field_name("object")
        name = property_name(node.child_by_field_name("property"))
        member = Member(self.expr(target), name)
        if resolved is not None:
            return Union((Name(node_text(node)), member))
        return member

    def _template(self, node: Node) -> Expr:
        """Lower a template literal, splitting text and computed parts"""

        if not any(child.type == "template_substitution" for child in node.named_children):
            return _literal(self.file._decode_string(node).value, node.start_byte)
        parts: list[Expr] = []
        for child in node.named_children:
            if child.type == "string_fragment":
                parts.append(_literal(node_text(child), child.start_byte))
            elif child.type == "escape_sequence":
                parts.append(_literal(node_text(child), child.start_byte))
            elif child.type == "template_substitution":
                inner = [item for item in child.named_children if item.type != "comment"]
                if inner:
                    parts.append(self.expr(inner[0]))
        return Compose(tuple(parts))

    def _binary(self, node: Node) -> Expr:
        """Lower a binary expression: + builds strings, logical operators mix, comparisons give booleans"""

        left = self.expr(node.child_by_field_name("left"))
        right = self.expr(node.child_by_field_name("right"))
        operator = node.child_by_field_name("operator")
        symbol = ""
        if operator is not None:
            symbol = operator.type
        if symbol == "+":
            return Compose((left, right))
        if symbol in UNION_OPERATORS:
            return Union((left, right))
        return Operation((left, right), node.start_byte)

    def _object(self, node: Node) -> Expr:
        """Lower an object literal: it holds the labels of its values"""

        parts: list[Expr] = []
        for child in node.named_children:
            if child.type == "pair":
                parts.append(self.expr(child.child_by_field_name("value")))
            elif child.type == "shorthand_property_identifier":
                parts.append(Name(node_text(child)))
            elif child.type == "spread_element":
                parts.append(self.expr(child))
        return Union(tuple(parts))

    def _call(self, node: Node) -> Expr:
        """Lower a call: package functions, then the flow tables, then methods of values"""

        callee = node.child_by_field_name("function") or node.child_by_field_name("constructor")
        offset = node.start_byte
        arguments = call_arguments(node)
        template = node.child_by_field_name("arguments")
        if template is not None and template.type == "template_string":
            arguments = [template]
        current = unwrap(callee)
        if current is None:
            return EMPTY
        if current.type == "identifier" and self.resolvers and node_text(current) == self.resolvers[-1]:
            return Resolve(Union(tuple(self.expr(argument) for argument in arguments)))
        if current.type == "import":
            inputs = self._inputs(None, arguments)
            return self._sinks(inputs, offset, [(FlowSinkKind.CODE, ROLE_CODE, inputs.argument(0), "import()")])
        targets = None
        if node.type == "call_expression":
            targets, _ = self.file.dispatch(node, callee)
        if targets is None:
            target = self.file.call_target(callee, offset)
            targets = []
            if target is not None:
                targets = [target]
        if node.type == "new_expression" and is_promise(node) and arguments:
            executor = unwrap(arguments[0])
            if executor is not None and executor.type in INLINE_FUNCTIONS:
                callback = self._callback(executor, (), returns=True, resolver=True)
                return Operation((), offset, callbacks=(callback,))
        callbacks = self._plain_callbacks(arguments)
        if targets:
            argument_exprs = tuple(self.expr(argument) for argument in arguments)
            calls = tuple(Call(target, argument_exprs, (), None, offset) for target in targets)
            call: Expr = Union(calls)
            if len(calls) == 1:
                call = calls[0]
            if callbacks:
                return Operation((call,), offset, result=Result("union", (0,)), callbacks=callbacks)
            return call
        resolved = self.file.resolve(current)
        qualified, imported = "", False
        if resolved is not None:
            qualified, imported = resolved
        receiver: Node | None = None
        method = None
        if current.type == "member_expression":
            receiver = unwrap(current.child_by_field_name("object"))
            method = property_name(current.child_by_field_name("property"))
        inputs = self._inputs(receiver, arguments)
        if current.type not in ("identifier", "member_expression"):
            inputs.add(self.expr(current))
        if qualified:
            known = self._known_call(qualified, imported, arguments, inputs, offset)
            if known is not None:
                return known
        if receiver is not None and method is not None and not imported:
            return self._method(method, receiver, arguments, inputs, offset)
        name = qualified.rsplit(".", 1)[-1]
        result = Result("none")
        if node.type == "new_expression" or name[:1].isupper():
            result = Result("union", inputs.arguments())
        return Operation(tuple(inputs.items), offset, result=result, callbacks=callbacks)

    def _inputs(self, receiver: Node | None, arguments: list[Node]) -> _Inputs:
        """Lower the receiver and the arguments of a call into inputs"""

        inputs = _Inputs()
        if receiver is not None:
            inputs.add(self.expr(receiver))
        for argument in arguments:
            inputs.positional.append(inputs.add(self.expr(argument)))
        return inputs

    def _plain_callbacks(self, arguments: list[Node]) -> tuple[Callback, ...]:
        """Lower the inline functions given to a call, with unbound parameters"""

        callbacks = []
        for argument in arguments:
            current = unwrap(argument)
            if current is not None and current.type in INLINE_FUNCTIONS:
                callbacks.append(self._callback(current, ()))
        return tuple(callbacks)

    def _callback(
        self,
        function: Node,
        bindings: tuple[int | None, ...],
        returns: bool = False,
        resolver: bool = False,
        source: FlowSourceKind | None = None,
        detail: str = "",
    ) -> Callback:
        """Lower an inline function evaluated where it is written"""

        parameters, prelude = self._parameters(function)
        resolver_name = None
        if resolver and parameters:
            resolver_name = parameters[0]
            self.resolvers.append(resolver_name)
        body = prelude + self._function_body(function)
        if resolver_name is not None:
            self.resolvers.pop()
        padded = bindings + (None,) * (len(parameters) - len(bindings))
        return Callback(parameters, padded[: len(parameters)], body, resolver_name, returns, source, detail)

    def _known_call(
        self, qualified: str, imported: bool, arguments: list[Node], inputs: _Inputs, offset: int
    ) -> Expr | None:
        """Lower a call found in the flow tables or the network capability table"""

        first = inputs.argument(0)
        if qualified in JAVASCRIPT_ENV_GETTERS:
            return Operation(tuple(inputs.items), offset)
        decoded = self._decoder(qualified, arguments, inputs, offset)
        if decoded is not None:
            return decoded
        if qualified in JAVASCRIPT_SHELL_CALLS:
            return self._sinks(inputs, offset, [(FlowSinkKind.SHELL, ROLE_COMMAND, first, qualified)])
        if qualified in JAVASCRIPT_SHELL_OPTION_CALLS or qualified in JAVASCRIPT_PROCESS_CALLS:
            return self._process(qualified, arguments, inputs, offset)
        if qualified in JAVASCRIPT_CODE_CALLS:
            code = first
            if qualified == "Function":
                code = inputs.arguments()
            return self._sinks(inputs, offset, [(FlowSinkKind.CODE, ROLE_CODE, code, qualified)])
        if qualified in JAVASCRIPT_TIMERS and arguments:
            current = unwrap(arguments[0])
            if current is not None and current.type in TEXT_NODES | {"binary_expression", "identifier"}:
                if current.type != "identifier" or node_text(current) not in self.file.function_names:
                    return self._sinks(inputs, offset, [(FlowSinkKind.CODE, ROLE_CODE, first, qualified)])
        if qualified in JAVASCRIPT_LOADERS and not imported:
            current = None
            if arguments:
                current = unwrap(arguments[0])
            if current is not None and current.type != "string":
                return self._sinks(inputs, offset, [(FlowSinkKind.CODE, ROLE_CODE, first, qualified)])
            return Operation(tuple(inputs.items), offset)
        if qualified in JAVASCRIPT_RUN_FILE_CALLS:
            return self._sinks(inputs, offset, [(FlowSinkKind.RUN_FILE, ROLE_PATH, first, qualified)])
        if qualified in JAVASCRIPT_WRITE_CALLS:
            path_index, content_index = JAVASCRIPT_WRITE_CALLS[qualified]
            target: tuple[str, ...] = ()
            if path_index < len(arguments):
                target = _names(arguments[path_index])
            sinks = [
                (FlowSinkKind.FILE_WRITE, ROLE_PATH, inputs.argument(path_index), qualified),
                (FlowSinkKind.FILE_WRITE, ROLE_CONTENT, inputs.argument(content_index), qualified),
            ]
            return self._sinks(inputs, offset, sinks, target=target)
        if qualified in JAVASCRIPT_COPY_CALLS or qualified in JAVASCRIPT_STREAM_CALLS:
            destination = inputs.argument(JAVASCRIPT_COPY_CALLS.get(qualified, 0))
            return self._sinks(inputs, offset, [(FlowSinkKind.FILE_WRITE, ROLE_PATH, destination, qualified)])
        if qualified in JAVASCRIPT_READ_CALLS:
            return Operation(tuple(inputs.items), offset, result=Result("read", first))
        kind = RuleKind.GLOBAL
        if imported:
            kind = RuleKind.MODULE
        rule = match_rule(JAVASCRIPT_RULES, qualified, kind)
        if rule is not None and rule.capability is Capability.NETWORK:
            return self._network(inputs, arguments, offset, qualified)
        if qualified.rsplit(".", 1)[-1] in JAVASCRIPT_TOOL_BUILDERS:
            sources = inputs.arguments()
            if any(self.file.static_text(item).value.startswith(URL_PREFIXES) for item in arguments):
                sources += (inputs.add(Source(FlowSourceKind.NETWORK_RESPONSE, qualified, offset)),)
            sink = (FlowSinkKind.TOOL_DESCRIPTION, ROLE_DESCRIPTION, sources, qualified)
            return self._sinks(inputs, offset, [sink])
        if qualified in JAVASCRIPT_PROPAGATORS:
            return Operation(tuple(inputs.items), offset, result=Result("union", inputs.arguments()))
        return None

    def _decoder(self, qualified: str, arguments: list[Node], inputs: _Inputs, offset: int) -> Expr | None:
        """Lower atob, Buffer.from with an encoding, zlib and String.fromCharCode"""

        first = inputs.argument(0)
        if qualified in JAVASCRIPT_DECODERS:
            if arguments and self._is_literal(arguments[0]):
                return self._source(inputs, offset, qualified)
            return Operation(tuple(inputs.items), offset, result=Result("decode", first))
        if qualified == JAVASCRIPT_BUFFER_FROM and arguments:
            if self._is_code_array(arguments[0]):
                return self._source(inputs, offset, qualified)
            encoding = ""
            if len(arguments) > 1:
                encoding = self.file.static_text(arguments[1]).value
            if encoding in JAVASCRIPT_DECODING_ENCODINGS:
                if self._is_literal(arguments[0]):
                    return self._source(inputs, offset, qualified)
                return Operation(tuple(inputs.items), offset, result=Result("decode", first))
            return None
        if qualified in JAVASCRIPT_CHARACTER_FUNCTIONS:
            numbers = [unwrap(argument) for argument in arguments]
            if len(numbers) >= MIN_CODE_ARRAY and all(item is not None and item.type == "number" for item in numbers):
                return self._source(inputs, offset, qualified)
            for argument in numbers:
                if argument is not None and argument.type == "spread_element" and argument.named_children:
                    if self._is_code_array(argument.named_children[0]):
                        return self._source(inputs, offset, qualified)
            return Operation(tuple(inputs.items), offset, result=Result("decode", inputs.arguments()))
        return None

    def _process(self, qualified: str, arguments: list[Node], inputs: _Inputs, offset: int) -> Expr:
        """Lower child_process, execa, Bun and Deno calls into shell or process sinks"""

        if qualified in JAVASCRIPT_SHELL_OPTION_CALLS and self._shell_option(arguments):
            command = inputs.argument(0)
            if len(arguments) > 1 and self.file._as_object(arguments[1]) is None:
                command = command + inputs.argument(1)
            return self._sinks(inputs, offset, [(FlowSinkKind.SHELL, ROLE_COMMAND, command, qualified)])
        program = None
        if arguments:
            program = unwrap(arguments[0])
        if program is not None and program.type == "array" and program.named_children:
            elements = [self.expr(child) for child in program.named_children]
            first = inputs.add(elements[0])
            others = tuple(inputs.add(element) for element in elements[1:])
            sinks = [
                (FlowSinkKind.PROCESS, ROLE_PROGRAM, (first,), qualified),
                (FlowSinkKind.PROCESS, ROLE_ARGUMENTS, others + inputs.rest(1), qualified),
            ]
            return self._sinks(inputs, offset, sinks)
        sinks = [
            (FlowSinkKind.PROCESS, ROLE_PROGRAM, inputs.argument(0), qualified),
            (FlowSinkKind.PROCESS, ROLE_ARGUMENTS, inputs.rest(1), qualified),
        ]
        return self._sinks(inputs, offset, sinks)

    def _shell_option(self, arguments: list[Node]) -> bool:
        """Tell whether the options object of a process call sets shell to a true value"""

        for argument in arguments[1:]:
            options = self.file._as_object(argument)
            if options is None:
                continue
            value = unwrap(self.file._object_value(options, JAVASCRIPT_SHELL_OPTION))
            if value is not None and value.type in ("true", "string", "template_string"):
                return True
        return False

    def _method(self, method: str, receiver: Node, arguments: list[Node], inputs: _Inputs, offset: int) -> Expr:
        """Lower a method call on a value: clients, streams, callbacks, string building, containers"""

        receiver_text = node_text(receiver)
        first = inputs.argument(0)
        if self.file._client_of(receiver_text, offset) is not None or receiver_text in self.network:
            return self._network(inputs, arguments, offset, f"{receiver_text}.{method}")
        if method in JAVASCRIPT_HANDLE_WRITE_METHODS and receiver_text in self.handles:
            target = _names(self.handles[receiver_text])
            sink = (FlowSinkKind.FILE_WRITE, ROLE_CONTENT, inputs.arguments(), f".{method}")
            return self._sinks(inputs, offset, [sink], target=target)
        if method in JAVASCRIPT_SHELL_METHODS:
            return self._sinks(inputs, offset, [(FlowSinkKind.SHELL, ROLE_COMMAND, first, f".{method}")])
        if method == "map" and self._is_code_array(receiver) and self._decodes_codes(arguments):
            return self._source(inputs, offset, "String.fromCharCode")
        callbacks = self._method_callbacks(method, arguments)
        if callbacks:
            result = Result("union", (0,))
            if method in JAVASCRIPT_RESULT_CALLBACKS:
                result = Result("none")
            if method == "forEach" or method in ("on", "once", "addListener", "addEventListener"):
                result = Result("none")
            return Operation(tuple(inputs.items), offset, result=result, callbacks=callbacks)
        if method == "join":
            separator = ","
            if arguments:
                separator = self.file.static_text(arguments[0]).value
            if receiver.type == "array" and receiver.named_children:
                parts: list[int] = []
                for index, element in enumerate(receiver.named_children):
                    if index and separator:
                        parts.append(inputs.add(_literal(separator, offset)))
                    parts.append(inputs.add(self.expr(element)))
                return Operation(tuple(inputs.items), offset, result=Result("compose", tuple(parts)))
            if separator:
                literal = inputs.add(_literal(separator, offset))
                return Operation(tuple(inputs.items), offset, result=Result("compose", (literal, 0)))
            return Operation(tuple(inputs.items), offset, result=Result("union", (0,)))
        if method in ("concat", "replace", "replaceAll"):
            parts = (0, *inputs.arguments())
            if method != "concat":
                parts = (0, *inputs.argument(1))
            return Operation(tuple(inputs.items), offset, result=Result("compose", parts))
        if method in JAVASCRIPT_MUTATING_METHODS:
            updates = tuple((name, inputs.arguments()) for name in _names(receiver))
            return Operation(tuple(inputs.items), offset, updates=updates)
        return Operation(tuple(inputs.items), offset, result=Result("union", (0,)))

    def _method_callbacks(self, method: str, arguments: list[Node]) -> tuple[Callback, ...]:
        """Lower the inline functions given to then, map, on, reduce and the like, with their bindings"""

        callbacks = []
        for position, argument in enumerate(arguments):
            current = unwrap(argument)
            if current is None or current.type not in INLINE_FUNCTIONS:
                continue
            returns = method in JAVASCRIPT_RESULT_CALLBACKS
            if method in JAVASCRIPT_ELEMENT_CALLBACKS or method in JAVASCRIPT_VALUE_CALLBACKS:
                callbacks.append(self._callback(current, (0,), returns))
            elif method in JAVASCRIPT_REDUCERS and position == 0:
                initial = None
                if len(arguments) > 1:
                    initial = 2
                callbacks.append(self._callback(current, (initial, 0), True))
            else:
                callbacks.append(self._callback(current, ()))
        return tuple(callbacks)

    def _network(self, inputs: _Inputs, arguments: list[Node], offset: int, detail: str) -> Expr:
        """Lower a network call: everything given to it is sent, its result and callbacks get the response"""

        sink = SinkSpec(FlowSinkKind.NETWORK, ROLE_DATA, tuple(range(len(inputs.items))), detail, offset)
        callbacks = []
        for argument in arguments:
            current = unwrap(argument)
            if current is not None and current.type in INLINE_FUNCTIONS:
                callbacks.append(
                    self._callback(current, (None,), source=FlowSourceKind.NETWORK_RESPONSE, detail=detail)
                )
        result = Result("source", source=FlowSourceKind.NETWORK_RESPONSE, detail=detail)
        return Operation(tuple(inputs.items), offset, (sink,), result, callbacks=tuple(callbacks))

    def _source(self, inputs: _Inputs, offset: int, detail: str) -> Expr:
        """Lower a call that decodes a literal of the package"""

        result = Result("source", source=FlowSourceKind.ENCODED_LITERAL, detail=detail)
        return Operation(tuple(inputs.items), offset, result=result)

    def _sinks(
        self,
        inputs: _Inputs,
        offset: int,
        sinks: list[tuple[FlowSinkKind, str, tuple[int, ...], str]],
        result: Result = Result("none"),
        target: tuple[str, ...] = (),
    ) -> Expr:
        """Lower a call that feeds some of its inputs to sinks"""

        specs = tuple(SinkSpec(kind, role, indexes, detail, offset, target) for kind, role, indexes, detail in sinks)
        return Operation(tuple(inputs.items), offset, specs, result)

    def _is_literal(self, node: Node) -> bool:
        """Tell whether a value is a literal written in the package, directly or through constants"""

        current = unwrap(node)
        if current is None or current.type not in TEXT_NODES | {"identifier", "binary_expression", "member_expression"}:
            return False
        return not self.file.static_text(current).dynamic

    def _is_code_array(self, node: Node | None) -> bool:
        """Tell whether a node is an array literal of character codes, directly or through a constant"""

        current = unwrap(node)
        if current is not None and current.type == "identifier":
            current = unwrap(self.file.constants.get(node_text(current)))
        if current is None or current.type != "array":
            return False
        items = current.named_children
        return len(items) >= MIN_CODE_ARRAY and all(item.type == "number" for item in items)

    def _decodes_codes(self, arguments: list[Node]) -> bool:
        """Tell whether a map callback turns character codes into characters"""

        if not arguments:
            return False
        text = node_text(arguments[0])
        return any(name.split(".")[-1] in text for name in JAVASCRIPT_CHARACTER_FUNCTIONS)


def _literal(text: str, offset: int) -> Expr:
    """Build a literal with the sensitive path categories it mentions; a path also names the file it points to"""

    categories = tuple(dict.fromkeys(category for category, _ in find_sensitive_paths(text)))
    literal = Literal(text, offset, categories)
    if looks_like_path(text):
        return Union((literal, Name(literal_path(text))))
    return literal


def _names(node: Node) -> tuple[str, ...]:
    """Return the variable, member chain or literal path a node refers to, like stream, this.out or a /tmp path"""

    current = unwrap(node)
    if current is not None and current.type == "string":
        text = "".join(node_text(child) for child in current.named_children)
        if looks_like_path(text):
            return (literal_path(text),)
    if current is None or current.type not in ("identifier", "member_expression", "this"):
        return ()
    return (node_text(current),)


def is_promise(node: Node) -> bool:
    """Tell whether a new expression builds a Promise"""

    constructor = node.child_by_field_name("constructor")
    return constructor is not None and node_text(constructor) == JAVASCRIPT_PROMISE
