"""Lowering of Python syntax trees into the data flow intermediate form"""

from typing import TYPE_CHECKING

from tree_sitter import Node

from mcplain.adapters.common import node_text
from mcplain.adapters.dataflow import (
    EMPTY,
    Assign,
    Assigned,
    Branch,
    Call,
    Compose,
    Comprehension,
    Evaluate,
    Expr,
    FlowFunction,
    Literal,
    Loop,
    Member,
    Name,
    Operation,
    Result,
    Return,
    SinkSpec,
    Source,
    Stmt,
    Union,
    literal_path,
    looks_like_path,
)
from mcplain.adapters.python_syntax import dotted_parts, split_arguments
from mcplain.capabilities import (
    PYTHON_ENV_GETTERS,
    PYTHON_ENV_MAPPINGS,
    PYTHON_RULES,
    PYTHON_WRITE_MODE_CHARS,
    Capability,
    RuleKind,
    find_sensitive_paths,
    match_rule,
)
from mcplain.flows import (
    PYTHON_CHARACTER_FUNCTION,
    PYTHON_CODE_ARRAY_CALLS,
    PYTHON_CODE_CALLS,
    PYTHON_COMMAND_KEYWORDS,
    PYTHON_COPY_CALLS,
    PYTHON_DECODERS,
    PYTHON_HANDLE_WRITE_METHODS,
    PYTHON_MUTATING_METHODS,
    PYTHON_OPEN_CALLS,
    PYTHON_PATH_READ_METHODS,
    PYTHON_PATH_WRITE_METHODS,
    PYTHON_PROCESS_CALLS,
    PYTHON_PROPAGATORS,
    PYTHON_RUN_FILE_CALLS,
    PYTHON_RUN_FILE_METHODS,
    PYTHON_SHELL_CALLS,
    PYTHON_SHELL_KEYWORD,
    PYTHON_SHELL_METHODS,
    PYTHON_SHELL_OPTION_CALLS,
    PYTHON_TOOL_BUILDERS,
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
    from mcplain.adapters.python import _PythonFile

STRING_NODES: frozenset[str] = frozenset({"string", "concatenated_string"})
SEQUENCE_NODES: frozenset[str] = frozenset({"list", "tuple", "set", "expression_list"})
COMPREHENSION_NODES: frozenset[str] = frozenset(
    {"list_comprehension", "generator_expression", "set_comprehension", "dictionary_comprehension"}
)
PATTERN_NODES: frozenset[str] = frozenset({"pattern_list", "tuple_pattern", "list_pattern", "expression_list", "tuple", "list"})
SPLAT_NODES: frozenset[str] = frozenset({"list_splat", "dictionary_splat"})
SKIPPED_STATEMENTS: frozenset[str] = frozenset(
    {"function_definition", "class_definition", "import_statement", "import_from_statement"}
)
URL_PREFIXES: tuple[str, ...] = ("http://", "https://")
LEAF_NODES: frozenset[str] = frozenset(
    {"integer", "float", "true", "false", "none", "ellipsis", "lambda", "slice", "yield", "comment"}
)
STATIC_METHOD = "staticmethod"
SHELL_TRUE = "true"
MIN_CODE_ARRAY = 4


class _Inputs:
    """Class that collects the inputs of an operation and remembers where each argument sits"""

    def __init__(self) -> None:
        """Start with no input"""

        self.items: list[Expr] = []
        self.positional: list[int] = []
        self.keywords: dict[str, int] = {}

    def add(self, expr: Expr) -> int:
        """Add one input and return its index"""

        self.items.append(expr)
        return len(self.items) - 1

    def argument(self, position: int, keyword: str | None = None) -> tuple[int, ...]:
        """Return the input of a positional argument, or of a keyword argument"""

        if keyword is not None and keyword in self.keywords:
            return (self.keywords[keyword],)
        if position < len(self.positional):
            return (self.positional[position],)
        return ()

    def arguments(self) -> tuple[int, ...]:
        """Return every argument input"""

        return tuple(self.positional) + tuple(self.keywords.values())

    def rest(self, position: int) -> tuple[int, ...]:
        """Return the positional inputs from a position on, and the keywords"""

        return tuple(self.positional[position:]) + tuple(self.keywords.values())


class PythonLowering:
    """Class that lowers the functions of one parsed Python file"""

    def __init__(self, file: "_PythonFile") -> None:
        """Keep the analyzed file and index what the lowering needs"""

        self.file = file
        self.path = file.report.path
        self.names = {function.start: function.name for function in file.report.functions}
        self.descriptions = {tool.description_range for tool in file.report.tools if tool.description_range}
        self.handles: dict[str, Node] = {}
        self.network: set[str] = set()

    def functions(self) -> list[FlowFunction]:
        """Lower the module-level code, every function and every lambda"""

        result = []
        self._index_scope(self.file.root)
        module_body = self._block(self.file.root.named_children)
        result.append(FlowFunction(self.path, 0, len(self.file.source.data) + 1, None, (), module_body, module=True))
        for definition in self.file.nodes["function_definition"]:
            result.append(self._function(definition))
        for node in self.file.nodes["lambda"]:
            parameters = node.child_by_field_name("parameters")
            names = tuple(self._parameter_names(parameters))
            body = (Return(self.expr(node.child_by_field_name("body"))),)
            result.append(FlowFunction(self.path, node.start_byte, node.end_byte, None, names, body))
        return result

    def _function(self, definition: Node) -> FlowFunction:
        """Lower one function definition"""

        self._index_scope(definition)
        name_node = definition.child_by_field_name("name")
        name = self.names.get(definition.start_byte)
        if name is None and name_node is not None:
            name = node_text(name_node)
        body = definition.child_by_field_name("body")
        statements: tuple[Stmt, ...] = ()
        if body is not None:
            statements = self._block(body.named_children)
        parameters = tuple(self._parameter_names(definition.child_by_field_name("parameters")))
        return FlowFunction(
            self.path,
            definition.start_byte,
            definition.end_byte,
            name,
            parameters,
            statements,
            method=self._is_method(definition),
        )

    def _is_method(self, definition: Node) -> bool:
        """Tell whether a function is a method that receives the object as first parameter"""

        parent = definition.parent
        if parent is not None and parent.type == "decorated_definition":
            for decorator in parent.children:
                if decorator.type == "decorator" and node_text(decorator).lstrip("@").strip() == STATIC_METHOD:
                    return False
            parent = parent.parent
        return parent is not None and parent.type == "block" and parent.parent is not None and parent.parent.type == "class_definition"

    def _parameter_names(self, parameters: Node | None) -> list[str]:
        """Return the parameter names of a function or lambda, in order"""

        names: list[str] = []
        if parameters is None:
            return names
        for child in parameters.named_children:
            node = child
            if child.type in ("default_parameter", "typed_default_parameter"):
                node = child.child_by_field_name("name")
            elif child.type in ("typed_parameter", "list_splat_pattern", "dictionary_splat_pattern"):
                node = next((item for item in child.named_children if item.type == "identifier"), None)
            if node is not None and node.type == "identifier":
                names.append(node_text(node))
        return names

    def _index_scope(self, scope: Node) -> None:
        """Remember file handles opened for writing and network clients created in one scope"""

        self.handles = {}
        self.network = set()
        stack = list(scope.named_children)
        if scope.type == "function_definition":
            body = scope.child_by_field_name("body")
            stack = list(body.named_children) if body is not None else []
        while stack:
            node = stack.pop()
            if node.type in ("function_definition", "class_definition", "lambda"):
                continue
            if node.type == "assignment":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if left is not None and right is not None:
                    self._remember(node_text(left), right)
            elif node.type == "with_item":
                value = node.child_by_field_name("value")
                if value is not None and value.type == "as_pattern" and value.named_children:
                    alias = value.child_by_field_name("alias")
                    if alias is not None:
                        self._remember(node_text(alias), value.named_children[0])
            stack.extend(node.named_children)

    def _remember(self, name: str, value: Node) -> None:
        """Remember that a variable holds a file opened for writing or a network client"""

        if value.type == "await" and value.named_children:
            value = value.named_children[0]
        if value.type != "call":
            return
        parts = dotted_parts(value.child_by_field_name("function"))
        if not parts:
            return
        qualified, imported = self.file._resolve(parts)
        if self._is_open(qualified, imported) and self._writes(value):
            positional, _ = split_arguments(value.child_by_field_name("arguments"))
            if positional:
                self.handles[name] = positional[0]
        elif imported:
            rule = match_rule(PYTHON_RULES, qualified, RuleKind.MODULE)
            if rule is not None and rule.capability is Capability.NETWORK:
                self.network.add(name)

    def _is_open(self, qualified: str, imported: bool) -> bool:
        """Tell whether a call opens a file"""

        return qualified in PYTHON_OPEN_CALLS and (imported or qualified == "open")

    def _writes(self, call: Node) -> bool:
        """Tell whether an open() call can write, from its mode argument"""

        positional, keywords = split_arguments(call.child_by_field_name("arguments"))
        mode = keywords.get("mode")
        if mode is None and len(positional) > 1:
            mode = positional[1]
        if mode is None:
            return False
        text = self.file.static_text(mode)
        return text.dynamic or any(character in text.value for character in PYTHON_WRITE_MODE_CHARS)

    def _block(self, nodes: list[Node]) -> tuple[Stmt, ...]:
        """Lower a list of statements"""

        statements: list[Stmt] = []
        for node in nodes:
            statements.extend(self._statement(node))
        return tuple(statements)

    def _body(self, node: Node | None) -> tuple[Stmt, ...]:
        """Lower the block of a compound statement"""

        if node is None:
            return ()
        if node.type == "block":
            return self._block(node.named_children)
        return self._block([node])

    def _statement(self, node: Node) -> list[Stmt]:
        """Lower one statement"""

        kind = node.type
        if kind in SKIPPED_STATEMENTS:
            return []
        if kind == "decorated_definition":
            return [
                Evaluate(self.expr(decorator.named_children[0]))
                for decorator in node.children
                if decorator.type == "decorator" and decorator.named_children
            ]
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
            return self._if(node)
        if kind == "for_statement":
            return self._for(node)
        if kind == "while_statement":
            body = (Evaluate(self.expr(node.child_by_field_name("condition"))), *self._body(node.child_by_field_name("body")))
            statements = [Loop(body)]
            alternative = node.child_by_field_name("alternative")
            if alternative is not None:
                statements.extend(self._body(alternative.child_by_field_name("body")))
            return statements
        if kind == "try_statement":
            return self._try(node)
        if kind == "with_statement":
            return self._with(node)
        if kind == "match_statement":
            return self._match(node)
        if kind in ("raise_statement", "assert_statement"):
            return [Evaluate(self.expr(child)) for child in node.named_children]
        if kind == "block":
            return list(self._block(node.named_children))
        return []

    def _expression_statement(self, node: Node) -> list[Stmt]:
        """Lower an assignment or an expression evaluated for its effects"""

        if node.type == "assignment":
            return self._assignment(node)
        if node.type == "augmented_assignment":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            operator = node.child_by_field_name("operator")
            if left is None:
                return []
            value: Expr = Union((self.expr(left), self.expr(right)))
            if operator is not None and operator.type == "+=":
                value = Compose((self.expr(left), self.expr(right)))
            return [Assign(self._targets(left), value)]
        return [Evaluate(self.expr(node))]

    def _assignment(self, node: Node) -> list[Stmt]:
        """Lower a simple, annotated or chained assignment"""

        targets: list[tuple[str, bool]] = []
        current = node
        while current is not None and current.type == "assignment":
            left = current.child_by_field_name("left")
            if left is not None:
                targets.extend(self._targets(left))
            current = current.child_by_field_name("right")
        if current is None:
            return []
        return [Assign(tuple(targets), self.expr(current))]

    def _targets(self, node: Node) -> tuple[tuple[str, bool], ...]:
        """Return the variables an assignment writes; containers and objects keep their old labels"""

        if node.type == "identifier":
            return ((node_text(node), False),)
        if node.type == "attribute":
            parts = dotted_parts(node)
            if not parts:
                return ()
            return ((".".join(parts), False), (".".join(parts[:-1]), True))
        if node.type == "subscript":
            value = node.child_by_field_name("value")
            parts = dotted_parts(value)
            if not parts:
                return ()
            return ((".".join(parts), True),)
        if node.type in PATTERN_NODES or node.type in ("list_splat_pattern", "parenthesized_expression"):
            targets: list[tuple[str, bool]] = []
            for child in node.named_children:
                targets.extend(self._targets(child))
            return tuple(targets)
        return ()

    def _if(self, node: Node) -> list[Stmt]:
        """Lower an if statement with its elif and else clauses"""

        statements: list[Stmt] = [Evaluate(self.expr(node.child_by_field_name("condition")))]
        arms = [self._body(node.child_by_field_name("consequence"))]
        complete = False
        for alternative in node.children_by_field_name("alternative"):
            if alternative.type == "elif_clause":
                condition = Evaluate(self.expr(alternative.child_by_field_name("condition")))
                arms.append((condition, *self._body(alternative.child_by_field_name("consequence"))))
            elif alternative.type == "else_clause":
                arms.append(self._body(alternative.child_by_field_name("body")))
                complete = True
        statements.append(Branch(tuple(arms), complete))
        return statements

    def _for(self, node: Node) -> list[Stmt]:
        """Lower a for loop: the loop variables receive the labels of the iterable"""

        iterable = f"$for{node.start_byte}"
        left = node.child_by_field_name("left")
        statements: list[Stmt] = [Assign(((iterable, False),), self.expr(node.child_by_field_name("right")))]
        body: list[Stmt] = []
        if left is not None:
            body.append(Assign(self._targets(left), Member(Name(iterable), None)))
        body.extend(self._body(node.child_by_field_name("body")))
        statements.append(Loop(tuple(body)))
        alternative = node.child_by_field_name("alternative")
        if alternative is not None:
            statements.extend(self._body(alternative.child_by_field_name("body")))
        return statements

    def _try(self, node: Node) -> list[Stmt]:
        """Lower a try statement: handlers may run or not, then else and finally"""

        statements = list(self._body(node.child_by_field_name("body")))
        handlers = []
        tail: list[Stmt] = []
        for child in node.named_children:
            if child.type in ("except_clause", "except_group_clause"):
                blocks = [item for item in child.named_children if item.type == "block"]
                handlers.append(self._body(blocks[0]) if blocks else ())
            elif child.type == "else_clause":
                statements.extend(self._body(child.child_by_field_name("body")))
            elif child.type == "finally_clause":
                blocks = [item for item in child.named_children if item.type == "block"]
                if blocks:
                    tail.extend(self._body(blocks[0]))
        if handlers:
            statements.append(Branch(tuple(handlers), False))
        statements.extend(tail)
        return statements

    def _with(self, node: Node) -> list[Stmt]:
        """Lower a with statement: each as-target receives the labels of its context manager"""

        statements: list[Stmt] = []
        for clause in node.named_children:
            if clause.type != "with_clause":
                continue
            for item in clause.named_children:
                value = item.child_by_field_name("value")
                if value is None:
                    continue
                if value.type == "as_pattern" and value.named_children:
                    alias = value.child_by_field_name("alias")
                    targets: tuple[tuple[str, bool], ...] = ()
                    if alias is not None:
                        for child in alias.named_children or [alias]:
                            targets += self._targets(child)
                    statements.append(Assign(targets, self.expr(value.named_children[0])))
                else:
                    statements.append(Evaluate(self.expr(value)))
        statements.extend(self._body(node.child_by_field_name("body")))
        return statements

    def _match(self, node: Node) -> list[Stmt]:
        """Lower a match statement: one arm per case"""

        statements: list[Stmt] = [Evaluate(self.expr(node.child_by_field_name("subject")))]
        body = node.child_by_field_name("body")
        arms = []
        for clause in body.named_children if body is not None else []:
            if clause.type == "case_clause":
                arms.append(self._body(clause.child_by_field_name("consequence")))
        statements.append(Branch(tuple(arms), False))
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
        if kind == "identifier":
            if node_text(node) in self.file.aliases:
                return EMPTY
            return Name(node_text(node))
        if kind == "attribute":
            return self._attribute(node)
        if kind == "subscript":
            value = node.child_by_field_name("value")
            parts = dotted_parts(value)
            if parts:
                qualified, imported = self.file._resolve(parts)
                if imported and qualified in PYTHON_ENV_MAPPINGS:
                    return EMPTY
            key = node.child_by_field_name("subscript")
            name = None
            if key is not None and key.type in STRING_NODES:
                text = self.file.static_text(key)
                if not text.dynamic:
                    name = text.value
            return Member(self.expr(value), name)
        if kind == "call":
            return self._call(node)
        if kind == "string":
            return self._string(node)
        if kind == "concatenated_string":
            return Compose(tuple(self._string(child) for child in node.named_children if child.type == "string"))
        if kind == "binary_operator":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            operator = node.child_by_field_name("operator")
            symbol = operator.type if operator is not None else ""
            if symbol == "+" or (symbol == "%" and left is not None and left.type in STRING_NODES):
                return Compose((self.expr(left), self.expr(right)))
            return Union((self.expr(left), self.expr(right)))
        if kind == "boolean_operator":
            return Union((self.expr(node.child_by_field_name("left")), self.expr(node.child_by_field_name("right"))))
        if kind in ("not_operator", "comparison_operator"):
            return Operation(tuple(self.expr(child) for child in node.named_children), node.start_byte)
        if kind == "conditional_expression":
            parts = tuple(self.expr(child) for child in node.named_children)
            return Operation(parts, node.start_byte, result=Result("union", tuple(index for index in (0, 2) if index < len(parts))))
        if kind in ("parenthesized_expression", "await", "list_splat", "dictionary_splat", "parenthesized_list_splat"):
            children = [child for child in node.named_children if child.type != "comment"]
            if not children:
                return EMPTY
            return self.expr(children[0])
        if kind == "unary_operator":
            return self.expr(node.child_by_field_name("argument"))
        if kind in SEQUENCE_NODES:
            return Union(tuple(self.expr(child) for child in node.named_children))
        if kind == "dictionary":
            parts = []
            for child in node.named_children:
                if child.type == "pair":
                    parts.append(self.expr(child.child_by_field_name("value")))
                elif child.type == "dictionary_splat":
                    parts.append(self.expr(child))
            return Union(tuple(parts))
        if kind in COMPREHENSION_NODES:
            return self._comprehension(node)
        if kind == "named_expression":
            name = node.child_by_field_name("name")
            if name is None:
                return EMPTY
            return Assigned(((node_text(name), False),), self.expr(node.child_by_field_name("value")))
        return Operation(tuple(self.expr(child) for child in node.named_children), node.start_byte)

    def _attribute(self, node: Node) -> Expr:
        """Lower an attribute: os.environ is the whole environment, other chains keep their object's labels"""

        parts = dotted_parts(node)
        if parts:
            qualified, imported = self.file._resolve(parts)
            if imported and qualified in PYTHON_ENV_MAPPINGS:
                return Source(FlowSourceKind.ENVIRONMENT, qualified, node.start_byte)
            if imported:
                return EMPTY
            return Union((Name(".".join(parts)), Member(self.expr(node.child_by_field_name("object")), parts[-1])))
        attribute = node.child_by_field_name("attribute")
        name = node_text(attribute) if attribute is not None else None
        return Member(self.expr(node.child_by_field_name("object")), name)

    def _string(self, node: Node) -> Expr:
        """Lower a string literal, splitting f-strings into text and computed parts"""

        if not any(child.type == "interpolation" for child in node.children):
            value = self.file._decode_string(node).value
            return _literal(value, node.start_byte)
        parts: list[Expr] = []
        for child in node.children:
            if child.type == "string_content":
                parts.append(_literal(node_text(child), child.start_byte))
            elif child.type == "interpolation":
                parts.append(self.expr(child.child_by_field_name("expression")))
        return Compose(tuple(parts))

    def _comprehension(self, node: Node) -> Expr:
        """Lower a comprehension: loop variables take the labels of their iterables"""

        bindings = []
        for clause in node.named_children:
            if clause.type == "for_in_clause":
                left = clause.child_by_field_name("left")
                targets = tuple(name for name, _ in self._targets(left)) if left is not None else ()
                bindings.append((targets, Member(self.expr(clause.child_by_field_name("right")), None)))
        body = node.child_by_field_name("body")
        if body is not None and body.type == "pair":
            body = body.child_by_field_name("value")
        return Comprehension(tuple(bindings), self.expr(body))

    def _call(self, node: Node) -> Expr:
        """Lower a call: package functions, then the flow tables, then methods of values"""

        callee = node.child_by_field_name("function")
        arguments = node.child_by_field_name("arguments")
        offset = node.start_byte
        positional, keywords = split_arguments(arguments)
        splats: list[Node] = []
        if arguments is not None and arguments.type == "generator_expression":
            positional = [arguments]
        elif arguments is not None:
            splats = [child for child in arguments.named_children if child.type in SPLAT_NODES]
        if callee is None:
            return EMPTY
        targets, _ = self.file.dispatch(node, callee)
        if targets is None:
            target = self.file.call_target(callee, offset)
            targets = [target] if target is not None else []
        if targets:
            return self._package_call(callee, targets, positional, keywords, splats, offset)
        parts = dotted_parts(callee)
        qualified, imported = "", False
        if parts:
            qualified, imported = self.file._resolve(parts)
        inputs = _Inputs()
        receiver: Node | None = None
        if callee.type == "attribute":
            receiver = callee.child_by_field_name("object")
            inputs.add(self.expr(receiver))
        for argument in positional:
            inputs.positional.append(inputs.add(self.expr(argument)))
        for name, value in keywords.items():
            inputs.keywords[name] = inputs.add(self.expr(value))
        for splat in splats:
            inputs.positional.append(inputs.add(self.expr(splat)))
        special = self._process_call(qualified, imported, positional, keywords, inputs, offset)
        if special is not None:
            return special
        if parts and (imported or len(parts) == 1 or parts[0] in PYTHON_CODE_ARRAY_CALLS):
            known = self._known_call(qualified, imported, positional, keywords, inputs, offset)
            if known is not None:
                return known
        if receiver is not None:
            attribute = callee.child_by_field_name("attribute")
            method = node_text(attribute) if attribute is not None else ""
            return self._method(method, receiver, positional, keywords, inputs, offset)
        if parts and parts[-1][:1].isupper():
            return Operation(tuple(inputs.items), offset, result=Result("union", inputs.arguments()))
        return Operation(tuple(inputs.items), offset)

    def _package_call(
        self,
        callee: Node,
        targets: list,
        positional: list[Node],
        keywords: dict[str, Node],
        splats: list[Node],
        offset: int,
    ) -> Expr:
        """Lower a call to functions of the package, keeping the bound object of a method call"""

        arguments = tuple(self.expr(item) for item in positional + splats)
        named = tuple((name, self.expr(value)) for name, value in keywords.items())
        receiver: Expr | None = None
        parts = dotted_parts(callee)
        if callee.type == "attribute" and not (parts and len(parts) == 2 and parts[0] in self.file.classes):
            receiver = self.expr(callee.child_by_field_name("object"))
        calls = tuple(Call(target, arguments, named, receiver, offset) for target in targets)
        if len(calls) == 1:
            return calls[0]
        return Union(calls)

    def _process_call(
        self,
        qualified: str,
        imported: bool,
        positional: list[Node],
        keywords: dict[str, Node],
        inputs: _Inputs,
        offset: int,
    ) -> Expr | None:
        """Lower subprocess and os calls into shell or process sinks"""

        if not imported:
            return None
        if qualified in PYTHON_SHELL_CALLS:
            command = inputs.argument(0, "cmd")
            return self._sinks(inputs, offset, [(FlowSinkKind.SHELL, ROLE_COMMAND, command, qualified)])
        shell = keywords.get(PYTHON_SHELL_KEYWORD)
        if qualified in PYTHON_SHELL_OPTION_CALLS and shell is not None and shell.type == SHELL_TRUE:
            command = inputs.argument(0, PYTHON_COMMAND_KEYWORDS[0])
            return self._sinks(inputs, offset, [(FlowSinkKind.SHELL, ROLE_COMMAND, command, qualified)])
        position = PYTHON_PROCESS_CALLS.get(qualified)
        if qualified in PYTHON_SHELL_OPTION_CALLS:
            position = 0
        if position is None:
            return None
        command_node = positional[position] if position < len(positional) else keywords.get(PYTHON_COMMAND_KEYWORDS[0])
        return self._process(command_node, inputs, position, qualified, offset)

    def _process(self, command: Node | None, inputs: _Inputs, position: int, detail: str, offset: int) -> Expr:
        """Split a process call into the program it runs and its other arguments"""

        sinks: list[tuple[FlowSinkKind, str, tuple[int, ...], str]] = []
        rest = tuple(index for index in inputs.rest(position + 1))
        if command is not None and command.type in ("list", "tuple") and command.named_children:
            elements = [self.expr(child) for child in command.named_children]
            program = inputs.add(elements[0])
            others = tuple(inputs.add(element) for element in elements[1:])
            sinks.append((FlowSinkKind.PROCESS, ROLE_PROGRAM, (program,), detail))
            sinks.append((FlowSinkKind.PROCESS, ROLE_ARGUMENTS, others + rest, detail))
        elif command is not None and command.type in STRING_NODES | {"binary_operator"}:
            sinks.append((FlowSinkKind.PROCESS, ROLE_PROGRAM, inputs.argument(position), detail))
            sinks.append((FlowSinkKind.PROCESS, ROLE_ARGUMENTS, rest, detail))
        else:
            sinks.append((FlowSinkKind.PROCESS, ROLE_ARGUMENTS, inputs.argument(position) + rest, detail))
        return self._sinks(inputs, offset, sinks)

    def _known_call(
        self,
        qualified: str,
        imported: bool,
        positional: list[Node],
        keywords: dict[str, Node],
        inputs: _Inputs,
        offset: int,
    ) -> Expr | None:
        """Lower a call found in the flow tables or the network capability table"""

        first = inputs.argument(0)
        if imported and qualified in PYTHON_ENV_GETTERS:
            return Operation(tuple(inputs.items), offset)
        if qualified in PYTHON_DECODERS:
            if positional and self._is_literal(positional[0]):
                return self._source(inputs, offset, FlowSourceKind.ENCODED_LITERAL, qualified)
            return Operation(tuple(inputs.items), offset, result=Result("decode", first))
        if not imported and qualified in PYTHON_CODE_ARRAY_CALLS:
            if positional and _is_code_array(positional[0]):
                return self._source(inputs, offset, FlowSourceKind.ENCODED_LITERAL, qualified)
            return Operation(tuple(inputs.items), offset, result=Result("union", inputs.arguments()))
        if qualified in PYTHON_CODE_CALLS:
            result = Result("none")
            if qualified.endswith("compile"):
                result = Result("union", first)
            return self._sinks(inputs, offset, [(FlowSinkKind.CODE, ROLE_CODE, first, qualified)], result)
        if imported and qualified in PYTHON_RUN_FILE_CALLS:
            return self._sinks(inputs, offset, [(FlowSinkKind.RUN_FILE, ROLE_PATH, first, qualified)])
        if self._is_open(qualified, imported):
            call_mode = keywords.get("mode") or (positional[1] if len(positional) > 1 else None)
            text = self.file.static_text(call_mode) if call_mode is not None else None
            if text is not None and (text.dynamic or any(character in text.value for character in PYTHON_WRITE_MODE_CHARS)):
                return self._sinks(inputs, offset, [(FlowSinkKind.FILE_WRITE, ROLE_PATH, first, qualified)])
            return Operation(tuple(inputs.items), offset, result=Result("read", first))
        if imported and qualified in PYTHON_COPY_CALLS:
            destination = inputs.argument(PYTHON_COPY_CALLS[qualified])
            return self._sinks(inputs, offset, [(FlowSinkKind.FILE_WRITE, ROLE_PATH, destination, qualified)])
        if imported:
            rule = match_rule(PYTHON_RULES, qualified, RuleKind.MODULE)
            if rule is not None and rule.capability is Capability.NETWORK:
                return self._network(inputs, offset, qualified)
        if qualified.rsplit(".", 1)[-1] in PYTHON_TOOL_BUILDERS:
            sources = inputs.arguments()
            if any(self.file.static_text(item).value.startswith(URL_PREFIXES) for item in positional + list(keywords.values())):
                sources += (inputs.add(Source(FlowSourceKind.NETWORK_RESPONSE, qualified, offset)),)
            sink = (FlowSinkKind.TOOL_DESCRIPTION, ROLE_DESCRIPTION, sources, qualified)
            return self._sinks(inputs, offset, [sink])
        if qualified in PYTHON_PROPAGATORS:
            return Operation(tuple(inputs.items), offset, result=Result("union", inputs.arguments()))
        return None

    def _method(
        self,
        method: str,
        receiver: Node,
        positional: list[Node],
        keywords: dict[str, Node],
        inputs: _Inputs,
        offset: int,
    ) -> Expr:
        """Lower a method call on a value: clients, files, string building, containers"""

        receiver_text = node_text(receiver)
        first = inputs.argument(0)
        if self.file._client_of(receiver_text, offset) is not None or receiver_text in self.network:
            return self._network(inputs, offset, f"{receiver_text}.{method}")
        if method in PYTHON_HANDLE_WRITE_METHODS and receiver_text in self.handles:
            target = _names(self.handles[receiver_text])
            sink = (FlowSinkKind.FILE_WRITE, ROLE_CONTENT, inputs.arguments(), f".{method}")
            return self._sinks(inputs, offset, [sink], target=target)
        if method in PYTHON_PATH_WRITE_METHODS:
            target = _names(receiver)
            sinks = [
                (FlowSinkKind.FILE_WRITE, ROLE_PATH, (0,), f".{method}"),
                (FlowSinkKind.FILE_WRITE, ROLE_CONTENT, first, f".{method}"),
            ]
            return self._sinks(inputs, offset, sinks, target=target)
        if method in PYTHON_PATH_READ_METHODS:
            mode = keywords.get("mode") or (positional[0] if positional else None)
            if method == "open" and mode is not None:
                text = self.file.static_text(mode)
                if text.dynamic or any(character in text.value for character in PYTHON_WRITE_MODE_CHARS):
                    return self._sinks(inputs, offset, [(FlowSinkKind.FILE_WRITE, ROLE_PATH, (0,), ".open")])
            return Operation(tuple(inputs.items), offset, result=Result("read", (0,)))
        if method in PYTHON_RUN_FILE_METHODS:
            return self._sinks(inputs, offset, [(FlowSinkKind.RUN_FILE, ROLE_PATH, (0,), f".{method}")])
        if method in PYTHON_SHELL_METHODS:
            return self._sinks(inputs, offset, [(FlowSinkKind.SHELL, ROLE_COMMAND, first, f".{method}")])
        if method == "join" and receiver.type in STRING_NODES:
            return self._join(receiver, positional, inputs, offset)
        if method in ("format", "replace") and receiver.type in STRING_NODES | {"identifier", "attribute"}:
            parts = (0, *inputs.arguments())
            if method == "replace":
                parts = (0, *inputs.argument(1))
            return Operation(tuple(inputs.items), offset, result=Result("compose", parts))
        if method in PYTHON_MUTATING_METHODS:
            names = _names(receiver)
            updates = tuple((name, inputs.arguments()) for name in names)
            return Operation(tuple(inputs.items), offset, updates=updates)
        return Operation(tuple(inputs.items), offset, result=Result("union", (0,)))

    def _join(self, receiver: Node, positional: list[Node], inputs: _Inputs, offset: int) -> Expr:
        """Lower separator.join(items): a list literal is composed in order, characters codes are a payload"""

        if positional and _joins_character_codes(positional[0]):
            return self._source(inputs, offset, FlowSourceKind.ENCODED_LITERAL, PYTHON_CHARACTER_FUNCTION)
        separator = self.file.static_text(receiver).value
        if positional and positional[0].type in ("list", "tuple"):
            parts: list[int] = []
            for index, element in enumerate(positional[0].named_children):
                if index and separator:
                    parts.append(inputs.add(_literal(separator, receiver.start_byte)))
                parts.append(inputs.add(self.expr(element)))
            return Operation(tuple(inputs.items), offset, result=Result("compose", tuple(parts)))
        if separator:
            return Operation(tuple(inputs.items), offset, result=Result("compose", (0, *inputs.argument(0))))
        return Operation(tuple(inputs.items), offset, result=Result("union", inputs.argument(0)))

    def _is_literal(self, node: Node) -> bool:
        """Tell whether a value is a literal written in the package, directly or through constants"""

        if node.type not in STRING_NODES | {"identifier", "binary_operator", "attribute", "parenthesized_expression"}:
            return False
        return not self.file.static_text(node).dynamic

    def _network(self, inputs: _Inputs, offset: int, detail: str) -> Expr:
        """Lower a network call: everything given to it is sent, its result is a network response"""

        sink = SinkSpec(FlowSinkKind.NETWORK, ROLE_DATA, tuple(range(len(inputs.items))), detail, offset)
        result = Result("source", source=FlowSourceKind.NETWORK_RESPONSE, detail=detail)
        return Operation(tuple(inputs.items), offset, (sink,), result)

    def _source(self, inputs: _Inputs, offset: int, kind: FlowSourceKind, detail: str) -> Expr:
        """Lower a call whose result is a fresh source"""

        return Operation(tuple(inputs.items), offset, result=Result("source", source=kind, detail=detail))

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


def _literal(text: str, offset: int) -> Expr:
    """Build a literal with the sensitive path categories it mentions; a path also names the file it points to"""

    categories = tuple(dict.fromkeys(category for category, _ in find_sensitive_paths(text)))
    literal = Literal(text, offset, categories)
    if looks_like_path(text):
        return Union((literal, Name(literal_path(text))))
    return literal


def _names(node: Node) -> tuple[str, ...]:
    """Return the variable, attribute chain or literal path a node writes to, like f, self.out or a /tmp path"""

    if node.type == "string" and not any(child.type == "interpolation" for child in node.children):
        text = "".join(node_text(child) for child in node.children if child.type == "string_content")
        if looks_like_path(text):
            return (literal_path(text),)
    parts = dotted_parts(node)
    if not parts:
        return ()
    return (".".join(parts),)


def _is_code_array(node: Node) -> bool:
    """Tell whether a node is a list literal of character codes"""

    if node.type not in ("list", "tuple"):
        return False
    items = node.named_children
    return len(items) >= MIN_CODE_ARRAY and all(item.type == "integer" for item in items)


def _joins_character_codes(node: Node) -> bool:
    """Tell whether a join argument turns a list of codes into characters, with chr()"""

    if node.type == "generator_expression":
        body = node.child_by_field_name("body")
        iterables = [
            clause.child_by_field_name("right") for clause in node.named_children if clause.type == "for_in_clause"
        ]
        uses_chr = body is not None and body.type == "call" and node_text(body.child_by_field_name("function") or body) == PYTHON_CHARACTER_FUNCTION
        return uses_chr and any(item is not None and _is_code_array(item) for item in iterables)
    if node.type == "call":
        function = node.child_by_field_name("function")
        positional, _ = split_arguments(node.child_by_field_name("arguments"))
        if function is not None and node_text(function) == "map" and len(positional) == 2:
            return node_text(positional[0]) == PYTHON_CHARACTER_FUNCTION and _is_code_array(positional[1])
    return False
