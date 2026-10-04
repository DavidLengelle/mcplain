"""Python adapter: reads Python source with tree-sitter, never imports it"""

import re
import unicodedata
from pathlib import Path

import tree_sitter_python
from tree_sitter import Language, Node, Parser

from mcplain.adapters.base import Adapter
from mcplain.adapters.common import (
    ANNOTATION_KEYS,
    BOOLEAN_NODES,
    COMPUTED,
    DYNAMIC_PLACEHOLDER,
    TITLE_KEY,
    UNSET_NODES,
    Piece,
    SourceText,
    TextValue,
    collect_nodes,
    dynamic_text,
    first_error,
    innermost,
    join_texts,
    mark_dynamic,
    node_text,
    text_from_pieces,
)
from mcplain.adapters.report import (
    FileReport,
    PackageContext,
    RawBlock,
    RawCall,
    RawFinding,
    RawFunction,
    RawGap,
    RawHandler,
    RawString,
    RawTool,
)
from mcplain.capabilities import (
    NETWORK_CLIENT_METHODS,
    PYTHON_CLIENT_URL_KEYWORDS,
    PYTHON_ENV_GETTERS,
    PYTHON_ENV_MAPPINGS,
    PYTHON_NETWORK_CLIENTS,
    PYTHON_OPEN_FUNCTIONS,
    PYTHON_OPEN_GLOBALS,
    PYTHON_RULES,
    PYTHON_TEXT_HELPERS,
    PYTHON_URL_FUNCTIONS,
    PYTHON_WRITE_MODE_CHARS,
    URL_AFTER_METHOD,
    Capability,
    RuleKind,
    find_sensitive_paths,
    is_secret_name,
    match_rule,
)
from mcplain.manifests import load_toml, read_text, string_list, table
from mcplain.models import DeclarationKind, InstallScript, ToolParameter, TrackingGap, UrlKind

PYTHON_LANGUAGE = Language(tree_sitter_python.language())
PYTHON_EXTENSIONS: frozenset[str] = frozenset({".py", ".pyw"})
NODE_TYPES: tuple[str, ...] = (
    "import_statement",
    "import_from_statement",
    "call",
    "attribute",
    "subscript",
    "string",
    "decorated_definition",
    "function_definition",
    "class_definition",
    "if_statement",
    "elif_clause",
    "match_statement",
    "assignment",
    "with_item",
    "lambda",
)
SIMPLE_ESCAPES: dict[str, str] = {
    "\\": "\\",
    "'": "'",
    '"': '"',
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\n": "",
}
STRING_TYPES: frozenset[str] = frozenset({"string", "concatenated_string"})
SKIPPED_PARAMETERS: frozenset[str] = frozenset({"self", "cls"})
CONTEXT_MARKER = "Context"
NAME_REFERENCE_PATTERN = re.compile(r"name$", re.IGNORECASE)
TOOL_ATTRIBUTE = "tool"
CALL_TOOL_ATTRIBUTE = "call_tool"
TOOL_SDK_ROOTS: frozenset[str] = frozenset({"fastmcp", "mcp"})
MAX_CONSTANT_DEPTH = 5
SCHEMA_METHODS: frozenset[str] = frozenset({"model_json_schema", "schema"})
FIELD_FUNCTION = "Field"
ANNOTATED_NAME = "Annotated"
ANNOTATIONS_CLASS = "ToolAnnotations"
CALL_TOOL_KEYWORD = "on_call_tool"
SELF_NAMES: frozenset[str] = frozenset({"self", "cls"})
MAIN_MODULE = "__main__.py"
ENTRY_POINTS_FILE = "entry_points.txt"
DIST_INFO_SUFFIX = ".dist-info"
SCRIPT_TABLES: tuple[str, ...] = ("scripts", "gui-scripts")
INIT_MODULE = "__init__"
SOURCE_ROOT = "src"
REFERENCE_TYPES: frozenset[str] = frozenset({"identifier", "attribute"})
CMDCLASS_KEYWORD = "cmdclass"
SETUP_SCRIPT = "setup.py"
OVERLOAD_DECORATORS: frozenset[str] = frozenset({"overload", "typing.overload", "typing_extensions.overload"})
ACCESSOR_DECORATORS: frozenset[str] = frozenset({"setter", "deleter"})
LOOKUP_METHOD = "get"
GETATTR_NAME = "getattr"
NAMESPACE_FUNCTIONS: frozenset[str] = frozenset({"globals", "locals", "vars"})
IMMEDIATE_CALLBACK_FUNCTIONS: frozenset[str] = frozenset({"map", "filter", "sorted", "sort", "min", "max", "reduce"})


def decode_escape(text: str) -> str:
    """Decode one Python escape sequence without evaluating code"""

    body = text[1:]
    if not body:
        return text
    head = body[0]
    try:
        if body in SIMPLE_ESCAPES:
            return SIMPLE_ESCAPES[body]
        if head in "xuU":
            return chr(int(body[1:], 16))
        if head == "N" and body.startswith("N{") and body.endswith("}"):
            return unicodedata.lookup(body[2:-1])
        if head in "01234567":
            return chr(int(body, 8))
    except (ValueError, KeyError, OverflowError):
        return text
    return text


def split_arguments(arguments: Node | None) -> tuple[list[Node], dict[str, Node]]:
    """Split a call's arguments into positional nodes and keyword nodes"""

    positional: list[Node] = []
    keywords: dict[str, Node] = {}
    if arguments is None:
        return positional, keywords
    for child in arguments.named_children:
        if child.type == "keyword_argument":
            name = child.child_by_field_name("name")
            value = child.child_by_field_name("value")
            if name is not None and value is not None:
                keywords[node_text(name)] = value
        elif child.type not in ("comment", "list_splat", "dictionary_splat"):
            positional.append(child)
    return positional, keywords


def dotted_parts(node: Node | None) -> list[str] | None:
    """Return the identifiers of a dotted name like a.b.c"""

    parts: list[str] = []
    current = node
    while current is not None and current.type == "attribute":
        attribute = current.child_by_field_name("attribute")
        if attribute is None:
            return None
        parts.append(node_text(attribute))
        current = current.child_by_field_name("object")
    if current is None or current.type != "identifier":
        return None
    parts.append(node_text(current))
    parts.reverse()
    return parts


def enclosing_function(node: Node) -> str | None:
    """Return the name of the innermost named function around a node, skipping lambdas"""

    current = node.parent
    while current is not None:
        if current.type == "function_definition":
            name = current.child_by_field_name("name")
            if name is not None:
                return node_text(name)
        current = current.parent
    return None


def enclosing_class(node: Node) -> str | None:
    """Return the name of the class whose body holds a node"""

    current = node.parent
    while current is not None:
        if current.type == "class_definition":
            name = current.child_by_field_name("name")
            if name is not None:
                return node_text(name)
        current = current.parent
    return None


def module_names(path: str) -> list[str]:
    """Return the dotted module names a Python file can be imported as"""

    stem = path.rsplit(".", 1)[0]
    parts = stem.split("/")
    if parts[-1] == INIT_MODULE:
        parts = parts[:-1]
    names = []
    if len(parts) > 1 and parts[0] == SOURCE_ROOT:
        names.append(".".join(parts[1:]))
    if parts:
        names.append(".".join(parts))
    return names


def _runs_immediately(function: Node) -> bool:
    """Tell whether a lambda runs at once, like the function given to map, filter or sorted"""

    arguments = function.parent
    if arguments is not None and arguments.type == "keyword_argument":
        arguments = arguments.parent
    if arguments is None or arguments.type != "argument_list" or arguments.parent is None:
        return False
    parts = dotted_parts(arguments.parent.child_by_field_name("function"))
    return bool(parts) and parts[-1] in IMMEDIATE_CALLBACK_FUNCTIONS


def docstring_node(definition: Node) -> Node | None:
    """Return the docstring literal of a function or class"""

    body = definition.child_by_field_name("body")
    if body is None:
        return None
    for child in body.named_children:
        if child.type == "comment":
            continue
        if child.type == "expression_statement" and child.named_children:
            first = child.named_children[0]
            if first.type in STRING_TYPES:
                return first
        return None
    return None


class _PythonFile:
    """Class that analyzes one parsed Python file"""

    def __init__(self, relative_path: str, source: SourceText, context: PackageContext) -> None:
        """Parse the file and index the nodes the analysis needs"""

        self.source = source
        self.context = context
        self.report = FileReport(path=relative_path, source=source)
        names = module_names(relative_path)
        package = []
        if names:
            package = names[0].split(".")
            if not relative_path.endswith(f"{INIT_MODULE}.py"):
                package = package[:-1]
        self.package_parts = package
        tree = Parser(PYTHON_LANGUAGE).parse(source.data)
        self.root = tree.root_node
        error = first_error(self.root)
        if error is not None:
            self.report.error_offset = error.start_byte
        self.nodes = collect_nodes(PYTHON_LANGUAGE, self.root, NODE_TYPES)
        self.aliases: dict[str, str] = {}
        self.constants: dict[str, Node] = {}
        self.functions: dict[str, Node] = {}
        self.classes: dict[str, Node] = {}
        self.function_names: set[str] = set()
        self.class_constants: dict[str, Node] = {}
        self.clients: list[tuple[str, int, int, str]] = []
        self.tool_definitions: set[int] = set()
        self.tables: list[tuple[str, int, int, list[tuple[str, Node]]]] = []
        self.instances: list[tuple[str, int, int, tuple[str, str | None]]] = []
        self.lookups: list[tuple[str, int, int, Node]] = []

    def run(self) -> FileReport:
        """Run every analysis step and return the file report"""

        self._index_imports()
        self._index_definitions()
        self._find_decorated_tools()
        self._find_call_tools()
        self._find_low_level_tools()
        self._find_dispatch_blocks()
        self._find_capabilities()
        self._find_calls()
        self._find_strings()
        return self.report

    def _index_imports(self) -> None:
        """Record local names bound by import statements and the package files they load"""

        for statement in self.nodes["import_statement"]:
            for child in statement.named_children:
                if child.type == "dotted_name":
                    full = node_text(child)
                    first = full.split(".")[0]
                    self.aliases[first] = first
                    self._note_import(full)
                elif child.type == "aliased_import":
                    name = child.child_by_field_name("name")
                    alias = child.child_by_field_name("alias")
                    if name is not None and alias is not None:
                        self.aliases[node_text(alias)] = node_text(name)
                        self._note_import(node_text(name))
        for statement in self.nodes["import_from_statement"]:
            module = statement.child_by_field_name("module_name")
            if module is None:
                continue
            module_name = None
            if module.type == "dotted_name":
                module_name = node_text(module)
            elif module.type == "relative_import":
                module_name = self._absolute_module(node_text(module))
            if module_name is None:
                continue
            self._note_import(module_name)
            for child in statement.children_by_field_name("name"):
                if child.type == "dotted_name":
                    imported = node_text(child)
                    self.aliases[imported.split(".")[0]] = f"{module_name}.{imported}"
                    self._note_import(f"{module_name}.{imported}")
                elif child.type == "aliased_import":
                    name = child.child_by_field_name("name")
                    alias = child.child_by_field_name("alias")
                    if name is not None and alias is not None:
                        self.aliases[node_text(alias)] = f"{module_name}.{node_text(name)}"
                        self._note_import(f"{module_name}.{node_text(name)}")

    def _absolute_module(self, relative: str) -> str | None:
        """Turn a relative import like ..pkg.mod into an absolute module name"""

        level = len(relative) - len(relative.lstrip("."))
        rest = relative[level:]
        if level - 1 > len(self.package_parts):
            return None
        parts = self.package_parts[: len(self.package_parts) - (level - 1)]
        if rest:
            parts = parts + rest.split(".")
        if not parts:
            return None
        return ".".join(parts)

    def internal_target(self, qualified: str) -> tuple[str, str | None] | None:
        """Return the package file and member a qualified name points to, if it is internal"""

        modules = self.context.modules
        if qualified in modules:
            return modules[qualified], None
        parts = qualified.split(".")
        for size in range(len(parts) - 1, 0, -1):
            module = ".".join(parts[:size])
            if module in modules:
                return modules[module], ".".join(parts[size:])
        return None

    def _note_import(self, qualified: str) -> None:
        """Remember a package file loaded by an import"""

        target = self.internal_target(qualified)
        if target is not None and target[0] not in self.report.imported_files:
            self.report.imported_files.append(target[0])

    def _index_definitions(self) -> None:
        """Record module constants, functions and classes by name"""

        counts: dict[str, int] = {}
        for statement in self.root.named_children:
            if statement.type != "expression_statement" or not statement.named_children:
                continue
            assignment = statement.named_children[0]
            if assignment.type != "assignment":
                continue
            left = assignment.child_by_field_name("left")
            right = assignment.child_by_field_name("right")
            if left is None or right is None or left.type != "identifier":
                continue
            name = node_text(left)
            counts[name] = counts.get(name, 0) + 1
            self.constants[name] = right
        for name, count in counts.items():
            if count > 1:
                del self.constants[name]
        for definition in self.nodes["function_definition"]:
            self.report.function_ranges.append((definition.start_byte, definition.end_byte))
            name = definition.child_by_field_name("name")
            if name is not None:
                self.functions.setdefault(node_text(name), definition)
                self._add_function(definition, node_text(name))
        for node in self.nodes["lambda"]:
            if not _runs_immediately(node):
                self.report.function_ranges.append((node.start_byte, node.end_byte))
        for definition in self.nodes["class_definition"]:
            name = definition.child_by_field_name("name")
            if name is not None:
                self.classes.setdefault(node_text(name), definition)
                self._index_class_constants(node_text(name), definition)

    def _index_class_constants(self, class_name: str, definition: Node) -> None:
        """Record NAME = value assignments of a class body, such as enum members"""

        body = definition.child_by_field_name("body")
        if body is None:
            return
        for statement in body.named_children:
            if statement.type != "expression_statement" or not statement.named_children:
                continue
            assignment = statement.named_children[0]
            left = assignment.child_by_field_name("left")
            right = assignment.child_by_field_name("right")
            if assignment.type == "assignment" and left is not None and right is not None and left.type == "identifier":
                self.class_constants[f"{class_name}.{node_text(left)}"] = right

    def _add_function(self, definition: Node, name: str) -> None:
        """Index a function for the call graph, as Class.method inside a class body"""

        parent = definition.parent
        overload = False
        if parent is not None and parent.type == "decorated_definition":
            overload = self._is_overload(parent)
            parent = parent.parent
        owner = None
        if parent is not None and parent.type == "block" and parent.parent is not None:
            owner = parent.parent
        if owner is not None and owner.type == "class_definition":
            class_name = owner.child_by_field_name("name")
            if class_name is not None:
                name = f"{node_text(class_name)}.{name}"
        scope_start, scope_end = 0, len(self.source.data) + 1
        module_level = True
        current = definition.parent
        while current is not None:
            if current.type == "function_definition":
                scope_start, scope_end = current.start_byte, current.end_byte
                module_level = False
                break
            current = current.parent
        self.function_names.add(name)
        self.report.functions.append(
            RawFunction(
                name, definition.start_byte, definition.end_byte, scope_start, scope_end, module_level, overload
            )
        )

    def _is_overload(self, decorated: Node) -> bool:
        """Tell whether a definition is a typing overload stub or a property setter or deleter"""

        for decorator in decorated.children:
            if decorator.type != "decorator" or not decorator.named_children:
                continue
            parts = dotted_parts(decorator.named_children[0])
            if not parts:
                continue
            qualified, _ = self._resolve(parts)
            if qualified in OVERLOAD_DECORATORS or parts[-1] in ACCESSOR_DECORATORS:
                return True
        return False

    def call_target(self, node: Node, offset: int) -> RawCall | None:
        """Turn a called or referenced name into a call graph edge"""

        parts = dotted_parts(node)
        if not parts:
            return None
        if len(parts) >= 2:
            instance = self._instance_of(".".join(parts[:-1]), node.start_byte)
            if instance is not None:
                class_name, file = instance
                return RawCall(offset, f"{class_name}.{parts[-1]}", file)
        if parts[0] in SELF_NAMES:
            class_name = enclosing_class(node)
            if class_name is None or len(parts) != 2:
                return None
            return RawCall(offset, f"{class_name}.{parts[1]}")
        if parts[0] in self.aliases:
            qualified, _ = self._resolve(parts)
            target = self.internal_target(qualified)
            if target is None or target[1] is None:
                return None
            return RawCall(offset, target[1], target[0])
        if len(parts) == 1 and parts[0] in self.function_names:
            return RawCall(offset, parts[0])
        if len(parts) == 2 and parts[0] in self.classes:
            return RawCall(offset, f"{parts[0]}.{parts[1]}")
        return None

    def _scope_of(self, node: Node, wanted: str = "function_definition") -> tuple[int, int]:
        """Return the range of the innermost function or class around a node, or the whole file"""

        current = node.parent
        while current is not None:
            if current.type == wanted:
                return current.start_byte, current.end_byte
            current = current.parent
        return 0, len(self.source.data) + 1

    def _index_dispatch(self) -> None:
        """Remember dispatch tables, instances of package classes and variables read from a lookup"""

        for assignment in self.nodes["assignment"]:
            left = assignment.child_by_field_name("left")
            right = assignment.child_by_field_name("right")
            if left is None or right is None:
                continue
            name = node_text(left)
            wanted = "function_definition"
            if name.split(".")[0] in SELF_NAMES:
                wanted = "class_definition"
            start, end = self._scope_of(assignment, wanted)
            if right.type == "dictionary" and (left.type == "identifier" or wanted == "class_definition"):
                entries = self._table_entries(right)
                if entries:
                    self.tables.append((name, start, end, entries))
                continue
            instance = self._constructed_class(right)
            if instance is not None:
                self.instances.append((name, start, end, instance))
            elif left.type == "identifier":
                self.lookups.append((name, start, end, right))
        for item in self.nodes["with_item"]:
            value = item.child_by_field_name("value")
            if value is None or value.type != "as_pattern" or not value.named_children:
                continue
            alias = value.child_by_field_name("alias")
            instance = self._constructed_class(value.named_children[0])
            if alias is not None and instance is not None:
                start, end = self._scope_of(item)
                self.instances.append((node_text(alias), start, end, instance))

    def _table_entries(self, dictionary: Node) -> list[tuple[str, Node]]:
        """Return the literal keys of a dict literal whose values are functions of the package"""

        entries: list[tuple[str, Node]] = []
        for pair in dictionary.named_children:
            key = pair.child_by_field_name("key")
            value = pair.child_by_field_name("value")
            if pair.type != "pair" or key is None or value is None or value.type not in REFERENCE_TYPES:
                continue
            text = self.static_text(key)
            if text.dynamic or self.call_target(value, value.start_byte) is None:
                continue
            entries.append((text.value, value))
        return entries

    def _constructed_class(self, node: Node | None) -> tuple[str, str | None] | None:
        """Return the package class created by a call like Store(...), as class name and file"""

        if node is None or node.type != "call":
            return None
        parts = dotted_parts(node.child_by_field_name("function"))
        if not parts:
            return None
        if len(parts) == 1 and parts[0] in self.classes:
            return parts[0], None
        if parts[0] not in self.aliases:
            return None
        qualified, _ = self._resolve(parts)
        target = self.internal_target(qualified)
        if target is None or target[1] is None or "." in target[1] or not target[1][:1].isupper():
            return None
        return target[1], target[0]

    def _instance_of(self, name: str, offset: int) -> tuple[str, str | None] | None:
        """Return the package class held by a variable or attribute at an offset"""

        return innermost(self.instances, name, offset)

    def _table_named(self, node: Node | None, offset: int) -> list[tuple[str, Node]] | None:
        """Return the entries of the dispatch table a name refers to at an offset"""

        if node is None or node.type not in REFERENCE_TYPES:
            return None
        return innermost(self.tables, node_text(node), offset)

    def _lookup_kind(self, node: Node | None, offset: int) -> tuple[list[tuple[str, Node]] | None, TrackingGap | None]:
        """Classify a callee read from a table, a dict, getattr or globals()"""

        if node is None:
            return None, None
        if node.type == "subscript":
            container = node.child_by_field_name("value")
            if self._namespace_call(container):
                return None, TrackingGap.DYNAMIC_ATTRIBUTE
            table = self._table_named(container, offset)
            if table is not None:
                return table, None
            return None, TrackingGap.DICT_CALL
        if node.type != "call":
            return None, None
        function = node.child_by_field_name("function")
        if function is not None and function.type == "identifier" and node_text(function) == GETATTR_NAME:
            positional, _ = split_arguments(node.child_by_field_name("arguments"))
            if len(positional) > 1 and self.static_text(positional[1]).dynamic:
                return None, TrackingGap.DYNAMIC_ATTRIBUTE
            return None, None
        if function is None or function.type != "attribute":
            return None, None
        attribute = function.child_by_field_name("attribute")
        container = function.child_by_field_name("object")
        if attribute is None or node_text(attribute) != LOOKUP_METHOD:
            return None, None
        if self._namespace_call(container):
            return None, TrackingGap.DYNAMIC_ATTRIBUTE
        table = self._table_named(container, offset)
        if table is not None:
            return table, None
        return None, TrackingGap.DICT_CALL

    def _namespace_call(self, node: Node | None) -> bool:
        """Tell whether an expression is globals(), locals() or vars(...)"""

        if node is None or node.type != "call":
            return False
        function = node.child_by_field_name("function")
        return function is not None and function.type == "identifier" and node_text(function) in NAMESPACE_FUNCTIONS

    def _dynamic_call(self, call: Node, callee: Node) -> bool:
        """Record calls through dispatch tables, and the calls that cannot be followed"""

        offset = call.start_byte
        lookup = callee
        if callee.type == "identifier":
            assigned = innermost(self.lookups, node_text(callee), offset)
            if assigned is None or node_text(callee) in self.function_names:
                return False
            lookup = assigned
        table, gap = self._lookup_kind(lookup, offset)
        if table is not None:
            for key, value in table:
                target = self.call_target(value, offset)
                if target is not None:
                    self.report.calls.append(RawCall(offset, target.name, target.file, key))
            return True
        if gap is not None:
            self.report.gaps.append(RawGap(offset, gap))
            return True
        return False

    def _method_call(self, callee: Node, offset: int) -> None:
        """Remember a method called on an object whose type is unknown"""

        attribute = callee.child_by_field_name("attribute")
        target = callee.child_by_field_name("object")
        if attribute is None or target is None or node_text(attribute).startswith("__"):
            return
        parts = dotted_parts(target)
        if parts and parts[0] in self.aliases:
            return
        if target.type in ("string", "concatenated_string"):
            return
        self.report.method_calls.append(RawCall(offset, node_text(attribute)))

    def _find_calls(self) -> None:
        """Record calls and function references passed as arguments"""

        self._index_dispatch()
        for call in self.nodes["call"]:
            callee = call.child_by_field_name("function")
            if callee is not None and not self._dynamic_call(call, callee):
                target = self.call_target(callee, call.start_byte)
                if target is not None:
                    self.report.calls.append(target)
                elif callee.type == "attribute":
                    self._method_call(callee, call.start_byte)
            positional, keywords = split_arguments(call.child_by_field_name("arguments"))
            for argument in positional + list(keywords.values()):
                if argument.type in REFERENCE_TYPES:
                    target = self.call_target(argument, argument.start_byte)
                    if target is not None:
                        self.report.calls.append(target)

    def _resolve(self, parts: list[str]) -> tuple[str, bool]:
        """Return the qualified name of a dotted name and whether it was imported"""

        head = parts[0]
        if head in self.aliases:
            return ".".join([self.aliases[head], *parts[1:]]), True
        return ".".join(parts), False

    def static_text(self, node: Node | None, depth: int = 0) -> TextValue:
        """Return the string value of an expression when it is known statically"""

        if node is None or depth > MAX_CONSTANT_DEPTH:
            return dynamic_text()
        kind = node.type
        if kind == "string":
            return self._decode_string(node)
        if kind == "concatenated_string":
            return join_texts([self._decode_string(child) for child in node.named_children if child.type == "string"])
        if kind == "parenthesized_expression" and node.named_children:
            return self.static_text(node.named_children[0], depth + 1)
        if kind == "binary_operator":
            operands = self._concatenation_operands(node)
            if operands is None:
                return dynamic_text()
            return join_texts([self.static_text(operand, depth) for operand in operands])
        if kind == "identifier":
            constant = self.constants.get(node_text(node))
            if constant is not None:
                return self.static_text(constant, depth + 1)
            return dynamic_text()
        if kind in ("attribute", "dotted_name"):
            return self._member_text(node_text(node), depth)
        if kind == "call":
            parts = dotted_parts(node.child_by_field_name("function"))
            positional, _ = split_arguments(node.child_by_field_name("arguments"))
            if parts and positional:
                qualified, imported = self._resolve(parts)
                if imported and qualified in PYTHON_TEXT_HELPERS:
                    return mark_dynamic(self.static_text(positional[0], depth + 1))
        return dynamic_text()

    def _member_text(self, dotted: str, depth: int) -> TextValue:
        """Read Class.MEMBER or Class.MEMBER.value from a class constant of this file"""

        parts = dotted.split(".")
        if len(parts) == 3 and parts[2] == "value":
            parts = parts[:2]
        constant = self.class_constants.get(".".join(parts))
        if len(parts) != 2 or constant is None:
            return dynamic_text()
        return self.static_text(constant, depth + 1)

    def _concatenation_operands(self, node: Node) -> list[Node] | None:
        """Flatten a chain of + operations into its operands, left to right"""

        operands: list[Node] = []
        stack: list[Node] = [node]
        while stack:
            current = stack.pop()
            operator = current.child_by_field_name("operator")
            if current.type == "binary_operator" and operator is not None and operator.type == "+":
                left = current.child_by_field_name("left")
                right = current.child_by_field_name("right")
                if left is None or right is None:
                    return None
                stack.append(right)
                stack.append(left)
            elif current.type == "binary_operator":
                return None
            else:
                operands.append(current)
        return operands

    def _decode_string(self, node: Node) -> TextValue:
        """Decode a string literal into its runtime value, keeping source positions"""

        pieces: list[Piece] = []
        dynamic = False
        raw = False
        data = self.source.data
        for child in node.children:
            if child.type == "string_start":
                prefix = node_text(child).lower()
                raw = "r" in prefix.rstrip("'\"")
            elif child.type == "string_content":
                if raw:
                    pieces.append(Piece(node_text(child), child.start_byte, True))
                    continue
                cursor = child.start_byte
                for escape in child.children:
                    if escape.type not in ("escape_sequence", "escape_interpolation"):
                        continue
                    if escape.start_byte > cursor:
                        chunk = data[cursor:escape.start_byte].decode("utf-8", errors="replace")
                        pieces.append(Piece(chunk, cursor, True))
                    text = node_text(escape)
                    decoded = text[:1]
                    if escape.type == "escape_sequence":
                        decoded = decode_escape(text)
                    pieces.append(Piece(decoded, escape.start_byte, False))
                    cursor = escape.end_byte
                if child.end_byte > cursor:
                    chunk = data[cursor:child.end_byte].decode("utf-8", errors="replace")
                    pieces.append(Piece(chunk, cursor, True))
            elif child.type == "interpolation":
                dynamic = True
                pieces.append(Piece(DYNAMIC_PLACEHOLDER, child.start_byte, False))
        return text_from_pieces(pieces, dynamic, node)

    def _function_tool(
        self,
        definition: Node,
        arguments: Node | None,
        declaration: DeclarationKind,
        offset: int,
        skip_first_positional: bool = False,
    ) -> None:
        """Build a tool from a function definition and optional decorator arguments"""

        if definition.id in self.tool_definitions:
            return
        self.tool_definitions.add(definition.id)
        name_node = definition.child_by_field_name("name")
        name = ""
        if name_node is not None:
            name = node_text(name_node)
        name_is_dynamic = False
        positional, keywords = split_arguments(arguments)
        if skip_first_positional:
            positional = positional[1:]
        name_value = keywords.get("name")
        if name_value is None and positional and positional[0].type in STRING_TYPES:
            name_value = positional[0]
        if name_value is not None:
            text = self.static_text(name_value)
            if text.dynamic:
                name_is_dynamic = True
            else:
                name = text.value
        description = None
        if "description" in keywords:
            description = self.static_text(keywords["description"])
        if description is None:
            doc = docstring_node(definition)
            description = TextValue()
            if doc is not None:
                description = self.static_text(doc)
        parameters, parameter_ranges = self._function_parameters(definition)
        tool = RawTool(
            name=name,
            name_is_dynamic=name_is_dynamic,
            description=description,
            offset=offset,
            declaration=declaration,
            parameters=parameters,
            bodies=[(definition.start_byte, definition.end_byte)],
            text_ranges=description.ranges + parameter_ranges,
        )
        self._declare(tool, keywords)
        self.report.tools.append(tool)

    def _declare(self, tool: RawTool, keywords: dict[str, Node]) -> None:
        """Read the title and annotations the author declares for a tool"""

        if TITLE_KEY in keywords:
            tool.title = self.static_text(keywords[TITLE_KEY])
            tool.text_ranges.extend(tool.title.ranges)
        if "annotations" in keywords:
            self._read_annotations(tool, keywords["annotations"], 0)

    def _read_annotations(self, tool: RawTool, node: Node, depth: int) -> None:
        """Read a dict or ToolAnnotations(...) of behavior hints, values kept as declared"""

        if node.type == "identifier" and node_text(node) in self.constants and depth < MAX_CONSTANT_DEPTH:
            self._read_annotations(tool, self.constants[node_text(node)], depth + 1)
            return
        pairs: list[tuple[str, Node]] = []
        if node.type == "dictionary":
            for pair in node.named_children:
                key = pair.child_by_field_name("key")
                value = pair.child_by_field_name("value")
                if pair.type == "pair" and key is not None and value is not None and key.type == "string":
                    pairs.append((self._decode_string(key).value, value))
        elif node.type == "call" and (dotted_parts(node.child_by_field_name("function")) or [""])[-1] == ANNOTATIONS_CLASS:
            _, keywords = split_arguments(node.child_by_field_name("arguments"))
            pairs.extend(keywords.items())
        elif node.type not in UNSET_NODES:
            tool.annotations_are_dynamic = True
            return
        for key, value in pairs:
            if key == TITLE_KEY and tool.title is None:
                tool.title = self.static_text(value)
                tool.text_ranges.extend(tool.title.ranges)
            canonical = ANNOTATION_KEYS.get(key)
            if canonical is None or value.type in UNSET_NODES:
                continue
            tool.annotations[canonical] = BOOLEAN_NODES.get(value.type, COMPUTED)

    def _function_parameters(self, definition: Node) -> tuple[list[ToolParameter], list[tuple[int, int]]]:
        """Read the parameters of a tool function"""

        parameters: list[ToolParameter] = []
        ranges: list[tuple[int, int]] = []
        node = definition.child_by_field_name("parameters")
        if node is None:
            return parameters, ranges
        for child in node.named_children:
            name_node = None
            type_node = None
            default_node = None
            if child.type == "identifier":
                name_node = child
            elif child.type == "typed_parameter":
                if child.named_children and child.named_children[0].type == "identifier":
                    name_node = child.named_children[0]
                type_node = child.child_by_field_name("type")
            elif child.type in ("default_parameter", "typed_default_parameter"):
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                default_node = child.child_by_field_name("value")
            if name_node is None:
                continue
            parameter = self._parameter(node_text(name_node), type_node, default_node, ranges)
            if parameter is not None:
                parameters.append(parameter)
        return parameters, ranges

    def _parameter(
        self,
        name: str,
        type_node: Node | None,
        default_node: Node | None,
        ranges: list[tuple[int, int]],
    ) -> ToolParameter | None:
        """Build one parameter, skipping self, cls and injected contexts"""

        if name in SKIPPED_PARAMETERS:
            return None
        type_text = None
        if type_node is not None:
            type_text = node_text(type_node)
            if CONTEXT_MARKER in type_text:
                return None
        description = self._field_description(type_node)
        if description is None:
            description = self._field_description(default_node)
        text = None
        if description is not None:
            text = description.value
            ranges.extend(description.ranges)
        return ToolParameter(name=name, type=type_text, description=text)

    def _field_description(self, node: Node | None) -> TextValue | None:
        """Find a Field(description=...) or Annotated string inside an expression"""

        if node is None:
            return None
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type == "call":
                parts = dotted_parts(current.child_by_field_name("function"))
                if parts and parts[-1] == FIELD_FUNCTION:
                    _, keywords = split_arguments(current.child_by_field_name("arguments"))
                    if "description" in keywords:
                        return self.static_text(keywords["description"])
            if current.type == "generic_type" and node_text(current).startswith(ANNOTATED_NAME):
                for parameter in current.named_children:
                    if parameter.type != "type_parameter":
                        continue
                    for item in parameter.named_children:
                        if item.named_children and item.named_children[0].type in STRING_TYPES:
                            return self.static_text(item.named_children[0])
            stack.extend(reversed(current.named_children))
        return None

    def _find_decorated_tools(self) -> None:
        """Find tools declared with @x.tool, @x.tool(...) or a standalone @tool"""

        for decorated in self.nodes["decorated_definition"]:
            definition = decorated.child_by_field_name("definition")
            if definition is None or definition.type != "function_definition":
                continue
            for decorator in decorated.children:
                if decorator.type != "decorator" or not decorator.named_children:
                    continue
                expression = decorator.named_children[0]
                callee = expression
                arguments = None
                if expression.type == "call":
                    callee = expression.child_by_field_name("function")
                    arguments = expression.child_by_field_name("arguments")
                role = self._decorator_role(callee)
                if role == TOOL_ATTRIBUTE:
                    self._function_tool(definition, arguments, DeclarationKind.DECORATOR, decorated.start_byte)
                elif role == CALL_TOOL_ATTRIBUTE:
                    self.report.call_handlers.append(RawHandler(definition.start_byte, definition.end_byte))

    def _decorator_role(self, callee: Node | None) -> str | None:
        """Tell whether a decorator declares a tool or a low-level call handler"""

        if callee is None:
            return None
        if callee.type == "attribute":
            attribute = callee.child_by_field_name("attribute")
            if attribute is not None and node_text(attribute) in (TOOL_ATTRIBUTE, CALL_TOOL_ATTRIBUTE):
                return node_text(attribute)
            return None
        if callee.type == "identifier":
            qualified, imported = self._resolve([node_text(callee)])
            parts = qualified.split(".")
            if imported and parts[-1] == TOOL_ATTRIBUTE and parts[0] in TOOL_SDK_ROOTS:
                return TOOL_ATTRIBUTE
        return None

    def _definition_for(self, node: Node) -> Node | None:
        """Find the function a name or attribute refers to in this file"""

        if node.type == "identifier":
            return self.functions.get(node_text(node))
        if node.type == "attribute":
            attribute = node.child_by_field_name("attribute")
            if attribute is not None:
                return self.functions.get(node_text(attribute))
        return None

    def _find_call_tools(self) -> None:
        """Find x.add_tool(fn), x.tool(fn) and Tool.from_function(fn) registrations"""

        for call in self.nodes["call"]:
            arguments = call.child_by_field_name("arguments")
            positional, keywords = split_arguments(arguments)
            if CALL_TOOL_KEYWORD in keywords:
                self._register_call_handler(keywords[CALL_TOOL_KEYWORD])
            callee = call.child_by_field_name("function")
            if callee is None or callee.type != "attribute":
                continue
            attribute = callee.child_by_field_name("attribute")
            target_object = callee.child_by_field_name("object")
            if attribute is None or target_object is None:
                continue
            method = node_text(attribute)
            if method == "from_function" and node_text(target_object).endswith("Tool"):
                self._register_function(call, positional, keywords, arguments, DeclarationKind.FROM_FUNCTION)
            elif method == "add_tool":
                if positional and positional[0].type == "call":
                    continue
                self._register_function(call, positional, keywords, arguments, DeclarationKind.ADD_TOOL)
            elif self._is_tool_call(call, method, positional):
                self._register_function(call, positional, keywords, arguments, DeclarationKind.ADD_TOOL)

    def _is_tool_call(self, call: Node, method: str, positional: list[Node]) -> bool:
        """Tell whether x.tool(fn) is used as a call that registers a function"""

        if method != TOOL_ATTRIBUTE or call.parent is None or call.parent.type == "decorator":
            return False
        return bool(positional) and positional[0].type in ("identifier", "attribute")

    def _register_call_handler(self, node: Node) -> None:
        """Remember a handler given to on_call_tool=, defined here or imported from the package"""

        handler = self._definition_for(node)
        if handler is not None:
            self.report.call_handlers.append(RawHandler(handler.start_byte, handler.end_byte))
            return
        if node.type in REFERENCE_TYPES:
            reference = self.call_target(node, node.start_byte)
            if reference is not None:
                self.report.call_handlers.append(RawHandler(reference=reference))

    def _register_function(
        self,
        call: Node,
        positional: list[Node],
        keywords: dict[str, Node],
        arguments: Node | None,
        declaration: DeclarationKind,
    ) -> None:
        """Register the function passed to a registration call as a tool"""

        target = None
        if positional:
            target = positional[0]
        else:
            target = keywords.get("fn") or keywords.get("tool")
        if target is None:
            return
        definition = self._definition_for(target)
        if definition is not None:
            self._function_tool(definition, arguments, declaration, call.start_byte, skip_first_positional=True)
            return
        entries = []
        if target.type in REFERENCE_TYPES:
            entry = self.call_target(target, call.start_byte)
            if entry is not None:
                entries.append(entry)
        name = node_text(target)
        name_is_dynamic = True
        if "name" in keywords:
            text = self.static_text(keywords["name"])
            if not text.dynamic:
                name = text.value
                name_is_dynamic = False
        description = dynamic_text()
        if "description" in keywords:
            description = self.static_text(keywords["description"])
        tool = RawTool(
            name=name,
            name_is_dynamic=name_is_dynamic,
            description=description,
            offset=call.start_byte,
            declaration=declaration,
            parameters_are_dynamic=True,
            entries=entries,
            text_ranges=description.ranges,
        )
        self._declare(tool, keywords)
        self.report.tools.append(tool)

    def _find_low_level_tools(self) -> None:
        """Find Tool(name=..., description=...) objects of the low-level server"""

        for call in self.nodes["call"]:
            parts = dotted_parts(call.child_by_field_name("function"))
            if not parts or parts[-1] != "Tool":
                continue
            _, keywords = split_arguments(call.child_by_field_name("arguments"))
            if "name" not in keywords:
                continue
            name_text = self.static_text(keywords["name"])
            name = name_text.value
            if name_text.dynamic:
                name = node_text(keywords["name"])
            description = TextValue()
            if "description" in keywords:
                description = self.static_text(keywords["description"])
            schema = keywords.get("input_schema") or keywords.get("inputSchema")
            parameters, dynamic, ranges = self._schema_parameters(schema, 0)
            tool = RawTool(
                name=name,
                name_is_dynamic=name_text.dynamic,
                description=description,
                offset=call.start_byte,
                declaration=DeclarationKind.LOW_LEVEL,
                parameters=parameters,
                parameters_are_dynamic=dynamic,
                text_ranges=description.ranges + ranges,
            )
            self._declare(tool, keywords)
            self.report.tools.append(tool)

    def _schema_parameters(
        self, node: Node | None, depth: int
    ) -> tuple[list[ToolParameter], bool, list[tuple[int, int]]]:
        """Read parameters from a JSON schema dict or a Pydantic model schema"""

        if node is None:
            return [], False, []
        if depth > MAX_CONSTANT_DEPTH:
            return [], True, []
        if node.type == "dictionary":
            properties = self._dictionary_value(node, "properties")
            if properties is None or properties.type != "dictionary":
                return [], properties is not None, []
            return self._dictionary_parameters(properties)
        if node.type == "identifier" and node_text(node) in self.constants:
            return self._schema_parameters(self.constants[node_text(node)], depth + 1)
        if node.type == "call":
            parts = dotted_parts(node.child_by_field_name("function"))
            if parts and len(parts) == 2 and parts[1] in SCHEMA_METHODS and parts[0] in self.classes:
                return self._class_parameters(self.classes[parts[0]])
        return [], True, []

    def _dictionary_value(self, dictionary: Node, key: str) -> Node | None:
        """Return the value of a literal key in a dict literal"""

        for pair in dictionary.named_children:
            if pair.type != "pair":
                continue
            key_node = pair.child_by_field_name("key")
            if key_node is not None and key_node.type == "string" and self._decode_string(key_node).value == key:
                return pair.child_by_field_name("value")
        return None

    def _dictionary_parameters(
        self, properties: Node
    ) -> tuple[list[ToolParameter], bool, list[tuple[int, int]]]:
        """Read parameters from the properties dict of a JSON schema"""

        parameters = []
        ranges: list[tuple[int, int]] = []
        for pair in properties.named_children:
            if pair.type != "pair":
                continue
            key_node = pair.child_by_field_name("key")
            value = pair.child_by_field_name("value")
            if key_node is None or key_node.type != "string":
                continue
            type_text = None
            description = None
            if value is not None and value.type == "dictionary":
                type_node = self._dictionary_value(value, "type")
                if type_node is not None:
                    type_text = self.static_text(type_node).value or None
                description_node = self._dictionary_value(value, "description")
                if description_node is not None:
                    text = self.static_text(description_node)
                    description = text.value
                    ranges.extend(text.ranges)
            parameters.append(
                ToolParameter(name=self._decode_string(key_node).value, type=type_text, description=description)
            )
        return parameters, False, ranges

    def _class_parameters(self, definition: Node) -> tuple[list[ToolParameter], bool, list[tuple[int, int]]]:
        """Read the annotated fields of a Pydantic model class"""

        parameters = []
        ranges: list[tuple[int, int]] = []
        body = definition.child_by_field_name("body")
        if body is None:
            return [], True, []
        for statement in body.named_children:
            if statement.type != "expression_statement" or not statement.named_children:
                continue
            assignment = statement.named_children[0]
            if assignment.type != "assignment":
                continue
            left = assignment.child_by_field_name("left")
            type_node = assignment.child_by_field_name("type")
            if left is None or left.type != "identifier" or type_node is None:
                continue
            name = node_text(left)
            if name.startswith("_") or name == "model_config":
                continue
            parameter = self._parameter(name, type_node, assignment.child_by_field_name("right"), ranges)
            if parameter is not None:
                parameters.append(parameter)
        return parameters, False, ranges

    def _find_dispatch_blocks(self) -> None:
        """Record every branch that runs when a tool name equals a known literal"""

        for node in self.nodes["if_statement"] + self.nodes["elif_clause"]:
            condition = node.child_by_field_name("condition")
            consequence = node.child_by_field_name("consequence")
            if condition is None or consequence is None or condition.type != "comparison_operator":
                continue
            literal = self._compared_literal(condition)
            if literal is not None:
                self.report.dispatch_blocks.append(RawBlock(literal, consequence.start_byte, consequence.end_byte))
        for match in self.nodes["match_statement"]:
            subject = match.child_by_field_name("subject")
            body = match.child_by_field_name("body")
            if subject is None or body is None or not NAME_REFERENCE_PATTERN.search(node_text(subject)):
                continue
            for clause in body.named_children:
                if clause.type != "case_clause":
                    continue
                for pattern in clause.named_children:
                    if pattern.type != "case_pattern" or not pattern.named_children:
                        continue
                    value = pattern.named_children[0]
                    if value.type not in ("string", "dotted_name"):
                        continue
                    text = self.static_text(value)
                    if not text.dynamic:
                        self.report.dispatch_blocks.append(RawBlock(text.value, clause.start_byte, clause.end_byte))

    def _compared_literal(self, condition: Node) -> str | None:
        """Return the known value compared to a tool name, like name == "x" or name == Tools.X.value"""

        operands = condition.named_children
        operators = [child.type for child in condition.children if not child.is_named]
        if len(operands) != 2 or operators != ["=="]:
            return None
        for literal, other in (operands, tuple(reversed(operands))):
            if not NAME_REFERENCE_PATTERN.search(node_text(other)):
                continue
            text = self.static_text(literal)
            if not text.dynamic:
                return text.value
        return None

    def _add(
        self, capability: Capability, node: Node, detail: str | None, url_kind: UrlKind | None = None
    ) -> None:
        """Record one capability finding"""

        self.report.findings.append(
            RawFinding(
                capability=capability,
                offset=node.start_byte,
                function=enclosing_function(node),
                detail=detail,
                url_kind=url_kind,
            )
        )

    def _client_constructor(self, node: Node | None) -> str | None:
        """Return the network client class created by a call, like httpx.AsyncClient"""

        if node is None or node.type != "call":
            return None
        parts = dotted_parts(node.child_by_field_name("function"))
        if not parts:
            return None
        qualified, imported = self._resolve(parts)
        if imported and qualified in PYTHON_NETWORK_CLIENTS:
            return qualified
        return None

    def _index_clients(self) -> None:
        """Remember variables that hold a network client, from assignments and with ... as v"""

        for assignment in self.nodes["assignment"]:
            left = assignment.child_by_field_name("left")
            constructor = self._client_constructor(assignment.child_by_field_name("right"))
            if left is not None and constructor is not None:
                self._bind_client(node_text(left), assignment, constructor)
        for item in self.nodes["with_item"]:
            value = item.child_by_field_name("value")
            if value is None or value.type != "as_pattern" or not value.named_children:
                continue
            alias = value.child_by_field_name("alias")
            constructor = self._client_constructor(value.named_children[0])
            if alias is not None and constructor is not None:
                self._bind_client(node_text(alias), item, constructor)

    def _bind_client(self, name: str, node: Node, constructor: str) -> None:
        """Record a client variable with the range where it is visible"""

        start, end = 0, len(self.source.data) + 1
        wanted = "function_definition"
        if name.split(".")[0] in SELF_NAMES:
            wanted = "class_definition"
        current = node.parent
        while current is not None:
            if current.type == wanted:
                start, end = current.start_byte, current.end_byte
                break
            current = current.parent
        self.clients.append((name, start, end, constructor))

    def _client_of(self, name: str, offset: int) -> str | None:
        """Return the client class held by a variable name at an offset"""

        best = None
        best_size = 0
        for client_name, start, end, constructor in self.clients:
            if client_name == name and start <= offset < end and (best is None or end - start < best_size):
                best = constructor
                best_size = end - start
        return best

    def _url_kind(self, arguments: Node | None, index: int, keywords_to_try: tuple[str, ...] = ("url",)) -> UrlKind:
        """Tell whether the URL argument of a network call is a literal, dynamic or absent"""

        positional, keywords = split_arguments(arguments)
        node = None
        for keyword in keywords_to_try:
            node = node or keywords.get(keyword)
        if node is None and index >= 0 and len(positional) > index:
            node = positional[index]
        if node is None:
            return UrlKind.UNKNOWN
        if self.static_text(node).dynamic:
            return UrlKind.DYNAMIC
        return UrlKind.LITERAL

    def _network_url_kind(self, qualified: str, arguments: Node | None) -> UrlKind:
        """Return the URL kind of a call to a network module function or client class"""

        if qualified in PYTHON_NETWORK_CLIENTS:
            return self._url_kind(arguments, -1, PYTHON_CLIENT_URL_KEYWORDS)
        method = qualified.rsplit(".", 1)[-1]
        if qualified in PYTHON_URL_FUNCTIONS or method in NETWORK_CLIENT_METHODS:
            index = 0
            if method in URL_AFTER_METHOD:
                index = 1
            return self._url_kind(arguments, index)
        return UrlKind.UNKNOWN

    def _find_capabilities(self) -> None:
        """Match calls, environment access and literals against the capability table"""

        self._index_clients()
        for call in self.nodes["call"]:
            self._check_call(call)
        for subscript in self.nodes["subscript"]:
            parts = dotted_parts(subscript.child_by_field_name("value"))
            if not parts:
                continue
            qualified, imported = self._resolve(parts)
            if imported and qualified in PYTHON_ENV_MAPPINGS:
                self._env_access(subscript, subscript.child_by_field_name("subscript"))
        for attribute in self.nodes["attribute"]:
            self._check_env_attribute(attribute)

    def _check_call(self, call: Node) -> None:
        """Match one call against the Python capability rules"""

        callee = call.child_by_field_name("function")
        arguments = call.child_by_field_name("arguments")
        if callee is not None and callee.type == "attribute" and self._client_call(call, callee, arguments):
            return
        parts = dotted_parts(callee)
        if parts:
            qualified, imported = self._resolve(parts)
            if imported and qualified in PYTHON_OPEN_FUNCTIONS:
                self._open_call(call, arguments, qualified)
                return
            if not imported and qualified in PYTHON_OPEN_GLOBALS:
                self._open_call(call, arguments, qualified)
                return
            if imported and qualified in PYTHON_ENV_GETTERS:
                positional, keywords = split_arguments(arguments)
                key = keywords.get("key")
                if positional:
                    key = positional[0]
                self._env_access(call, key)
                return
            kind = RuleKind.GLOBAL
            if imported:
                kind = RuleKind.MODULE
            rule = match_rule(PYTHON_RULES, qualified, kind)
            if rule is not None and rule.capability is Capability.NETWORK:
                self._add(rule.capability, call, qualified, self._network_url_kind(qualified, arguments))
                return
            if rule is not None:
                self._add(rule.capability, call, qualified)
                return
        if callee is not None and callee.type == "attribute":
            attribute = callee.child_by_field_name("attribute")
            if attribute is None:
                return
            method = node_text(attribute)
            rule = match_rule(PYTHON_RULES, method, RuleKind.METHOD)
            if rule is not None:
                self._add(rule.capability, call, "." + method)

    def _client_call(self, call: Node, callee: Node, arguments: Node | None) -> bool:
        """Record client.get(url) and the like when client holds a known network client"""

        attribute = callee.child_by_field_name("attribute")
        target = callee.child_by_field_name("object")
        if attribute is None or target is None or node_text(attribute) not in NETWORK_CLIENT_METHODS:
            return False
        method = node_text(attribute)
        constructor = self._client_of(node_text(target), call.start_byte)
        if constructor is None:
            return False
        index = 0
        if method in URL_AFTER_METHOD:
            index = 1
        self._add(Capability.NETWORK, call, f"{constructor}.{method}", self._url_kind(arguments, index))
        return True

    def _open_call(self, call: Node, arguments: Node | None, qualified: str) -> None:
        """Classify open() as a read or a write from its mode argument"""

        positional, keywords = split_arguments(arguments)
        mode_node = keywords.get("mode")
        if mode_node is None and len(positional) > 1:
            mode_node = positional[1]
        capability = Capability.FS_READ
        detail = qualified
        if mode_node is not None:
            mode = self.static_text(mode_node)
            detail = f"{qualified} mode={mode.value or '?'}"
            if mode.dynamic or any(character in mode.value for character in PYTHON_WRITE_MODE_CHARS):
                capability = Capability.FS_WRITE
        self._add(capability, call, detail)

    def _env_access(self, node: Node, key_node: Node | None) -> None:
        """Classify an environment read as a secret or a plain variable"""

        key = None
        if key_node is not None:
            text = self.static_text(key_node)
            if not text.dynamic:
                key = text.value
        if key is not None and is_secret_name(key):
            self._add(Capability.ENV_READ_SECRET, node, key)
            return
        self._add(Capability.ENV_READ, node, key)

    def _check_env_attribute(self, attribute: Node) -> None:
        """Flag bulk access to os.environ that is not a single-key read"""

        parts = dotted_parts(attribute)
        if not parts:
            return
        qualified, imported = self._resolve(parts)
        if not imported or qualified not in PYTHON_ENV_MAPPINGS:
            return
        parent = attribute.parent
        if parent is None:
            return
        if parent.type == "subscript":
            value = parent.child_by_field_name("value")
            if value is not None and value.id == attribute.id:
                return
        if parent.type == "attribute":
            grandparent = parent.parent
            if grandparent is not None and grandparent.type == "call":
                function = grandparent.child_by_field_name("function")
                parent_parts = dotted_parts(parent)
                if function is not None and function.id == parent.id and parent_parts:
                    parent_name, _ = self._resolve(parent_parts)
                    if parent_name in PYTHON_ENV_GETTERS:
                        return
        self._add(Capability.ENV_READ, attribute, qualified)

    def _find_strings(self) -> None:
        """Decode every string literal for URLs, sensitive paths and invisible characters"""

        for node in self.nodes["string"]:
            value = self._decode_string(node)
            sensitive = find_sensitive_paths(value.value)
            if sensitive:
                detail = ", ".join(match for _, match in sensitive)
                self._add(Capability.SENSITIVE_PATH, node, detail)
            self.report.strings.append(RawString(value=value, offset=node.start_byte, sensitive=sensitive))


class PythonAdapter(Adapter):
    """Class that analyzes Python MCP servers"""

    language = "python"

    def accepts(self, path: Path) -> bool:
        """Accept Python source files"""

        return path.suffix.lower() in PYTHON_EXTENSIONS

    def analyze_file(self, relative_path: str, source: SourceText, context: PackageContext) -> FileReport:
        """Analyze one Python file"""

        return _PythonFile(relative_path, source, context).run()

    def _entry_targets(self, server_dir: Path) -> list[str]:
        """Return the module:function targets of console scripts and entry points"""

        targets: list[str] = []
        project = table(load_toml(server_dir / "pyproject.toml"), "project")
        for name in SCRIPT_TABLES:
            targets.extend(value for value in table(project, name).values() if isinstance(value, str))
        for group in table(project, "entry-points").values():
            if isinstance(group, dict):
                targets.extend(value for value in group.values() if isinstance(value, str))
        for dist_info in server_dir.glob(f"*{DIST_INFO_SUFFIX}"):
            for line in (read_text(dist_info / ENTRY_POINTS_FILE) or "").splitlines():
                if "=" in line and not line.strip().startswith("["):
                    targets.append(line.split("=", 1)[1])
        return string_list(targets)

    def entry_points(self, server_dir: Path, context: PackageContext) -> set[str]:
        """Return __main__ files and the modules named by console scripts and entry points"""

        entries = {path for path in context.files if path.rsplit("/", 1)[-1] == MAIN_MODULE}
        for target in self._entry_targets(server_dir):
            module = target.split(":", 1)[0].strip()
            if module in context.modules:
                entries.add(context.modules[module])
        return entries

    def entry_functions(self, server_dir: Path, context: PackageContext) -> list[tuple[str, str]]:
        """Return the functions named by console scripts and entry points"""

        functions = []
        for target in self._entry_targets(server_dir):
            module, _, function = target.partition(":")
            name = function.split("[", 1)[0].strip()
            if name and module.strip() in context.modules:
                functions.append((context.modules[module.strip()], name))
        return functions

    def install_entries(self, server_dir: Path, context: PackageContext) -> set[str]:
        """Return setup.py, which runs when a source distribution is installed"""

        return {SETUP_SCRIPT} & context.files

    def index_modules(self, paths: list[str]) -> dict[str, str]:
        """Map dotted module names of the package to their files"""

        modules: dict[str, str] = {}
        for path in sorted(paths):
            for name in module_names(path):
                modules.setdefault(name, path)
        return modules

    def install_scripts(self, server_dir: Path) -> list[InstallScript]:
        """Find setup.py command classes and in-tree build backends"""

        scripts = []
        setup_text = read_text(server_dir / SETUP_SCRIPT)
        if setup_text is not None and CMDCLASS_KEYWORD in setup_text:
            source = SourceText(setup_text, self.limits)
            tree = Parser(PYTHON_LANGUAGE).parse(source.data)
            nodes = collect_nodes(PYTHON_LANGUAGE, tree.root_node, ("keyword_argument",))
            for keyword in nodes["keyword_argument"]:
                name = keyword.child_by_field_name("name")
                if name is not None and node_text(name) == CMDCLASS_KEYWORD:
                    line, _ = source.position(keyword.start_byte)
                    scripts.append(
                        InstallScript(
                            kind="setup_py_cmdclass",
                            file=SETUP_SCRIPT,
                            line=line,
                            command=source.snippet(keyword.start_byte),
                        )
                    )
        pyproject_text = read_text(server_dir / "pyproject.toml")
        build_system = table(load_toml(server_dir / "pyproject.toml"), "build-system")
        if pyproject_text is not None and "backend-path" in build_system:
            line = 1
            for number, text in enumerate(pyproject_text.splitlines(), start=1):
                if text.strip().startswith("backend-path"):
                    line = number
                    break
            scripts.append(
                InstallScript(
                    kind="custom_build_backend",
                    file="pyproject.toml",
                    line=line,
                    command=str(build_system.get("build-backend", "")),
                )
            )
        return scripts
