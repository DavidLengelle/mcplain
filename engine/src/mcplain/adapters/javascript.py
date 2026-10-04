"""JavaScript and TypeScript adapter: reads code with tree-sitter, never runs it"""

import posixpath
import re
from pathlib import Path

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from mcplain.adapters.base import Adapter
from mcplain.adapters.common import (
    DYNAMIC_PLACEHOLDER,
    Piece,
    SourceText,
    TextValue,
    collect_nodes,
    dynamic_text,
    first_error,
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
    RawHandler,
    RawString,
    RawTool,
)
from mcplain.capabilities import (
    JAVASCRIPT_BASE64_ENCODINGS,
    JAVASCRIPT_BUFFER_DECODERS,
    JAVASCRIPT_CLIENT_URL_KEYS,
    JAVASCRIPT_ENV_GETTERS,
    JAVASCRIPT_ENV_OBJECTS,
    JAVASCRIPT_NETWORK_CLIENTS,
    JAVASCRIPT_OPEN_FUNCTIONS,
    JAVASCRIPT_RULES,
    JAVASCRIPT_STRING_TIMERS,
    JAVASCRIPT_URL_GLOBALS,
    JAVASCRIPT_URL_KEYS,
    JAVASCRIPT_WRITE_FLAG_CHARS,
    NETWORK_CLIENT_METHODS,
    Capability,
    RuleKind,
    find_sensitive_paths,
    is_secret_name,
    match_rule,
    normalize_javascript_module,
    rewrite_javascript_chain,
)
from mcplain.manifests import load_json_object, read_text, table
from mcplain.models import DeclarationKind, InstallScript, ToolParameter, UrlKind

JAVASCRIPT_LANGUAGE = Language(tree_sitter_javascript.language())
TYPESCRIPT_LANGUAGE = Language(tree_sitter_typescript.language_typescript())
TSX_LANGUAGE = Language(tree_sitter_typescript.language_tsx())
LANGUAGES_BY_SUFFIX: dict[str, Language] = {
    ".js": JAVASCRIPT_LANGUAGE,
    ".mjs": JAVASCRIPT_LANGUAGE,
    ".cjs": JAVASCRIPT_LANGUAGE,
    ".jsx": JAVASCRIPT_LANGUAGE,
    ".ts": TYPESCRIPT_LANGUAGE,
    ".mts": TYPESCRIPT_LANGUAGE,
    ".cts": TYPESCRIPT_LANGUAGE,
    ".tsx": TSX_LANGUAGE,
}
TYPESCRIPT_SUFFIXES: frozenset[str] = frozenset({".ts", ".mts", ".cts", ".tsx"})
DECLARATION_SUFFIXES: tuple[str, ...] = (".d.ts", ".d.mts", ".d.cts")
NODE_TYPES: tuple[str, ...] = (
    "import_statement",
    "variable_declarator",
    "call_expression",
    "new_expression",
    "member_expression",
    "subscript_expression",
    "string",
    "template_string",
    "class_declaration",
    "class",
    "switch_statement",
    "if_statement",
    "object",
    "function_declaration",
    "generator_function_declaration",
    "method_definition",
    "arrow_function",
    "function_expression",
    "generator_function",
    "assignment_expression",
    "export_statement",
)
TYPESCRIPT_NODE_TYPES: tuple[str, ...] = (*NODE_TYPES, "enum_declaration")
SIMPLE_ESCAPES: dict[str, str] = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "b": "\b",
    "f": "\f",
    "v": "\v",
    "0": "\0",
    "\n": "",
    "\r\n": "",
    "\r": "",
    "\u2028": "",
    "\u2029": "",
}
FUNCTION_TYPES: frozenset[str] = frozenset(
    {"arrow_function", "function_expression", "function", "generator_function"}
)
NAMED_FUNCTION_TYPES: frozenset[str] = frozenset(
    {"function_declaration", "generator_function_declaration", "method_definition"}
)
TEXT_TYPES: frozenset[str] = frozenset({"string", "template_string"})
WRAPPER_TYPES: frozenset[str] = frozenset(
    {"parenthesized_expression", "as_expression", "satisfies_expression", "non_null_expression"}
)
DECLARATION_TYPES: frozenset[str] = frozenset({"lexical_declaration", "variable_declaration"})
FIELD_TYPES: frozenset[str] = frozenset({"field_definition", "public_field_definition"})
NAME_REFERENCE_PATTERN = re.compile(r"name\b", re.IGNORECASE)
TOOL_CLASS_PATTERN = re.compile(r"\bextends\s+[\w.]*MCPTool\b")
LIST_TOOLS_SCHEMAS: tuple[str, ...] = ("ListToolsRequestSchema",)
CALL_TOOL_SCHEMAS: tuple[str, ...] = ("CallToolRequestSchema",)
LIST_TOOLS_METHOD = "tools/list"
CALL_TOOL_METHOD = "tools/call"
PROMISIFY_NAMES: frozenset[str] = frozenset({"promisify", "util.promisify"})
TEXT_HELPERS: frozenset[str] = frozenset({"dedent", "String.raw", "outdent", "stripIndent"})
EQUALITY_OPERATORS: frozenset[str] = frozenset({"===", "=="})
INSTALL_HOOKS: tuple[str, ...] = ("preinstall", "install", "postinstall")
MAX_CONSTANT_DEPTH = 5
RESOLVE_EXTENSIONS: tuple[str, ...] = (".js", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".jsx")
SOURCE_SWAPS: dict[str, tuple[str, ...]] = {
    ".js": (".ts", ".tsx"),
    ".mjs": (".mts",),
    ".cjs": (".cts",),
    ".jsx": (".tsx",),
}
RELATIVE_PREFIXES: tuple[str, ...] = ("./", "../")
EXPORT_OBJECTS: frozenset[str] = frozenset({"exports", "module.exports"})
MODULE_EXPORTS = "module.exports"
DEFAULT_EXPORT = "default"
CLASS_TYPES: frozenset[str] = frozenset({"class_declaration", "class"})
REFERENCE_TYPES: frozenset[str] = frozenset({"identifier", "member_expression"})


def decode_escape(text: str) -> str:
    """Decode one JavaScript escape sequence without evaluating code"""

    body = text[1:]
    if body in SIMPLE_ESCAPES:
        return SIMPLE_ESCAPES[body]
    try:
        if body.startswith("u{") and body.endswith("}"):
            return chr(int(body[2:-1], 16))
        if body[:1] in ("u", "x") and len(body) > 1:
            return chr(int(body[1:], 16))
        if body[:1] in "01234567" and body:
            return chr(int(body, 8))
    except (ValueError, OverflowError):
        return body
    return body


def call_arguments(node: Node) -> list[Node]:
    """Return the argument nodes of a call or new expression"""

    arguments = node.child_by_field_name("arguments")
    if arguments is None or arguments.type != "arguments":
        return []
    return [child for child in arguments.named_children if child.type != "comment"]


def unwrap(node: Node | None) -> Node | None:
    """Remove parentheses and TypeScript casts around an expression"""

    current = node
    while current is not None and current.type in WRAPPER_TYPES and current.named_children:
        current = current.named_children[0]
    return current


def property_name(node: Node | None) -> str | None:
    """Return the name of an object key or member property"""

    if node is None:
        return None
    if node.type in ("property_identifier", "identifier", "private_property_identifier", "shorthand_property_identifier"):
        return node_text(node)
    if node.type == "string":
        return "".join(node_text(child) for child in node.named_children if child.type == "string_fragment")
    return None


def enclosing_function(node: Node) -> str | None:
    """Return the name of the innermost function around a node"""

    current = node.parent
    while current is not None:
        if current.type in NAMED_FUNCTION_TYPES:
            name = current.child_by_field_name("name")
            if name is not None:
                return node_text(name)
        if current.type in FUNCTION_TYPES:
            name = current.child_by_field_name("name")
            if name is not None:
                return node_text(name)
            parent = current.parent
            if parent is not None:
                label = _function_label(parent)
                if label is not None:
                    return label
        current = current.parent
    return None


def class_name(definition: Node) -> str | None:
    """Return the name of a class declaration or of the variable holding a class expression"""

    name = definition.child_by_field_name("name")
    if name is not None:
        return node_text(name)
    parent = definition.parent
    if parent is not None and parent.type == "variable_declarator":
        variable = parent.child_by_field_name("name")
        if variable is not None:
            return node_text(variable)
    return None


def enclosing_class(node: Node) -> str | None:
    """Return the name of the class around a node"""

    current = node.parent
    while current is not None:
        if current.type in CLASS_TYPES:
            return class_name(current)
        current = current.parent
    return None


def _function_label(parent: Node) -> str | None:
    """Return the name an anonymous function receives from where it is assigned"""

    if parent.type == "variable_declarator":
        name = parent.child_by_field_name("name")
        if name is not None:
            return node_text(name)
    if parent.type == "pair":
        return property_name(parent.child_by_field_name("key"))
    if parent.type == "assignment_expression":
        left = parent.child_by_field_name("left")
        if left is not None:
            return node_text(left)
    if parent.type in FIELD_TYPES:
        name = parent.child_by_field_name("name") or parent.child_by_field_name("property")
        if name is not None:
            return node_text(name)
    return None


class _JavaScriptFile:
    """Class that analyzes one parsed JavaScript or TypeScript file"""

    def __init__(self, relative_path: str, source: SourceText, language: Language, context: PackageContext) -> None:
        """Parse the file and index the nodes the analysis needs"""

        self.source = source
        self.context = context
        self.report = FileReport(path=relative_path, source=source)
        tree = Parser(language).parse(source.data)
        self.root = tree.root_node
        error = first_error(self.root)
        if error is not None:
            self.report.error_offset = error.start_byte
        node_types = TYPESCRIPT_NODE_TYPES
        if language is JAVASCRIPT_LANGUAGE:
            node_types = NODE_TYPES
        self.nodes = collect_nodes(language, self.root, node_types)
        self.aliases: dict[str, str] = {}
        self.constants: dict[str, Node] = {}
        self.functions: dict[str, Node] = {}
        self.internal: dict[str, tuple[str, str | None]] = {}
        self.function_names: set[str] = set()
        self.class_names: set[str] = set()
        self.enum_members: dict[str, Node] = {}
        self.clients: list[tuple[str, int, int, str]] = []
        self.list_handlers: list[Node] = []
        self.seen_objects: set[int] = set()

    def run(self) -> FileReport:
        """Run every analysis step and return the file report"""

        self._index_imports()
        self._index_definitions()
        self._index_functions()
        self._find_tools()
        self._find_capabilities()
        self._find_calls()
        self._find_strings()
        return self.report

    def internal_file(self, specifier: str) -> str | None:
        """Resolve a relative import specifier to a file of the analyzed package"""

        if not specifier.startswith(RELATIVE_PREFIXES) and specifier not in (".", ".."):
            return None
        base = posixpath.normpath(posixpath.join(posixpath.dirname(self.report.path), specifier))
        if base == ".." or base.startswith("../"):
            return None
        stem, extension = posixpath.splitext(base)
        candidates = [base]
        candidates.extend(stem + swap for swap in SOURCE_SWAPS.get(extension, ()))
        candidates.extend(base + suffix for suffix in RESOLVE_EXTENSIONS)
        candidates.extend(f"{base}/index{suffix}" for suffix in RESOLVE_EXTENSIONS)
        for candidate in candidates:
            if candidate in self.context.files:
                return candidate
        return None

    def _note_file(self, file: str) -> None:
        """Remember a package file loaded by this file"""

        if file not in self.report.imported_files:
            self.report.imported_files.append(file)

    def _loader_specifier(self, node: Node | None) -> str | None:
        """Return the string given to require() or import(), if node is such a call"""

        if node is None or node.type != "call_expression":
            return None
        function = node.child_by_field_name("function")
        if function is None:
            return None
        if not (function.type == "import" or (function.type == "identifier" and node_text(function) == "require")):
            return None
        arguments = call_arguments(node)
        if not arguments or arguments[0].type != "string":
            return None
        return self._decode_string(arguments[0]).value

    def _required_internal(self, value: Node | None) -> tuple[str, str | None] | None:
        """Return the package file and member loaded by require("./x") or await import("./x")"""

        node = unwrap(value)
        if node is not None and node.type == "await_expression" and node.named_children:
            node = unwrap(node.named_children[0])
        member = None
        if node is not None and node.type == "member_expression":
            member = property_name(node.child_by_field_name("property"))
            node = unwrap(node.child_by_field_name("object"))
        specifier = self._loader_specifier(node)
        if specifier is None:
            return None
        file = self.internal_file(specifier)
        if file is None:
            return None
        return file, member

    def _bind_internal_import(self, child: Node, file: str) -> None:
        """Record names bound by an import of a package file"""

        if child.type == "identifier":
            self.internal[node_text(child)] = (file, DEFAULT_EXPORT)
        elif child.type == "namespace_import":
            for identifier in child.named_children:
                if identifier.type == "identifier":
                    self.internal[node_text(identifier)] = (file, None)
        elif child.type == "named_imports":
            for specifier in child.named_children:
                if specifier.type != "import_specifier":
                    continue
                imported = specifier.child_by_field_name("name")
                alias = specifier.child_by_field_name("alias") or imported
                imported_name = property_name(imported)
                if imported_name is not None and alias is not None:
                    self.internal[node_text(alias)] = (file, imported_name)

    def _bind_internal_pattern(self, pattern: Node, target: tuple[str, str | None]) -> None:
        """Record names bound by require() of a package file"""

        file, member = target
        if pattern.type == "identifier":
            self.internal[node_text(pattern)] = (file, member)
            return
        if pattern.type != "object_pattern" or member is not None:
            return
        for child in pattern.named_children:
            if child.type == "shorthand_property_identifier_pattern":
                self.internal[node_text(child)] = (file, node_text(child))
            elif child.type == "pair_pattern":
                key = property_name(child.child_by_field_name("key"))
                value = child.child_by_field_name("value")
                if key is not None and value is not None and value.type == "identifier":
                    self.internal[node_text(value)] = (file, key)

    def _required_module(self, value: Node | None) -> str | None:
        """Return the module loaded by require("x"), await import("x") or require("x").y"""

        node = unwrap(value)
        if node is not None and node.type == "await_expression" and node.named_children:
            node = unwrap(node.named_children[0])
        suffix: list[str] = []
        while node is not None and node.type == "member_expression":
            name = property_name(node.child_by_field_name("property"))
            if name is None:
                return None
            suffix.insert(0, name)
            node = unwrap(node.child_by_field_name("object"))
        if node is None or node.type != "call_expression":
            return None
        function = node.child_by_field_name("function")
        if function is None:
            return None
        specifier = self._loader_specifier(node)
        if specifier is None or specifier.startswith("."):
            return None
        module = normalize_javascript_module(specifier)
        return rewrite_javascript_chain(".".join([module, *suffix]))

    def _index_imports(self) -> None:
        """Record local names bound by import statements and require calls"""

        for statement in self.nodes["import_statement"]:
            source = statement.child_by_field_name("source")
            if source is None or source.type != "string":
                continue
            specifier = self._decode_string(source).value
            internal = self.internal_file(specifier)
            if internal is not None:
                self._note_file(internal)
                for clause in statement.named_children:
                    if clause.type == "import_clause":
                        for child in clause.named_children:
                            self._bind_internal_import(child, internal)
                continue
            if specifier.startswith("."):
                continue
            module = normalize_javascript_module(specifier)
            for clause in statement.named_children:
                if clause.type != "import_clause":
                    continue
                for child in clause.named_children:
                    self._bind_import(child, module)
        for declarator in self.nodes["variable_declarator"]:
            name = declarator.child_by_field_name("name")
            value = declarator.child_by_field_name("value")
            if name is None or value is None:
                continue
            internal = self._required_internal(value)
            if internal is not None:
                self._note_file(internal[0])
                self._bind_internal_pattern(name, internal)
                continue
            module = self._required_module(value)
            if module is not None:
                self._bind_pattern(name, module)
                continue
            target = unwrap(value)
            if target is not None and target.type == "call_expression" and name.type == "identifier":
                function = target.child_by_field_name("function")
                arguments = call_arguments(target)
                if function is not None and node_text(function) in PROMISIFY_NAMES and arguments:
                    resolved = self.resolve(arguments[0])
                    if resolved is not None and resolved[1]:
                        self.aliases[node_text(name)] = resolved[0]

    def _bind_import(self, child: Node, module: str) -> None:
        """Record the names of one import clause part"""

        if child.type == "identifier":
            self.aliases[node_text(child)] = module
        elif child.type == "namespace_import":
            for identifier in child.named_children:
                if identifier.type == "identifier":
                    self.aliases[node_text(identifier)] = module
        elif child.type == "named_imports":
            for specifier in child.named_children:
                if specifier.type != "import_specifier":
                    continue
                imported = specifier.child_by_field_name("name")
                alias = specifier.child_by_field_name("alias") or imported
                imported_name = property_name(imported)
                if imported_name is not None and alias is not None:
                    self.aliases[node_text(alias)] = rewrite_javascript_chain(f"{module}.{imported_name}")

    def _bind_pattern(self, pattern: Node, module: str) -> None:
        """Record names bound by a require or dynamic import"""

        if pattern.type == "identifier":
            self.aliases[node_text(pattern)] = module
            return
        if pattern.type != "object_pattern":
            return
        for child in pattern.named_children:
            if child.type == "shorthand_property_identifier_pattern":
                name = node_text(child)
                self.aliases[name] = rewrite_javascript_chain(f"{module}.{name}")
            elif child.type == "pair_pattern":
                key = property_name(child.child_by_field_name("key"))
                value = child.child_by_field_name("value")
                if key is not None and value is not None and value.type == "identifier":
                    self.aliases[node_text(value)] = rewrite_javascript_chain(f"{module}.{key}")
            elif child.type == "object_assignment_pattern":
                left = child.child_by_field_name("left")
                if left is not None:
                    name = node_text(left)
                    self.aliases[name] = rewrite_javascript_chain(f"{module}.{name}")

    def _index_definitions(self) -> None:
        """Record module constants and functions by name"""

        counts: dict[str, int] = {}
        statements = []
        for child in self.root.named_children:
            if child.type == "export_statement":
                declaration = child.child_by_field_name("declaration")
                if declaration is not None:
                    statements.append(declaration)
            else:
                statements.append(child)
        for statement in statements:
            if statement.type in DECLARATION_TYPES:
                for declarator in statement.named_children:
                    if declarator.type != "variable_declarator":
                        continue
                    name = declarator.child_by_field_name("name")
                    value = declarator.child_by_field_name("value")
                    if name is None or value is None or name.type != "identifier":
                        continue
                    key = node_text(name)
                    counts[key] = counts.get(key, 0) + 1
                    self.constants[key] = value
                    if value.type in FUNCTION_TYPES:
                        self.functions[key] = value
            elif statement.type in NAMED_FUNCTION_TYPES:
                name = statement.child_by_field_name("name")
                if name is not None:
                    self.functions[node_text(name)] = statement
        for key, count in counts.items():
            if count > 1:
                self.constants.pop(key, None)
        for declaration in self.nodes.get("enum_declaration", []):
            name = declaration.child_by_field_name("name")
            body = declaration.child_by_field_name("body")
            if name is None or body is None:
                continue
            for member in body.named_children:
                member_name = property_name(member.child_by_field_name("name"))
                value = member.child_by_field_name("value")
                if member.type == "enum_assignment" and member_name is not None and value is not None:
                    self.enum_members[f"{node_text(name)}.{member_name}"] = value

    def _index_functions(self) -> None:
        """Index every named function for the call graph"""

        for node in self.nodes["function_declaration"] + self.nodes["generator_function_declaration"]:
            name = node.child_by_field_name("name")
            if name is not None:
                self._add_function(node, node_text(name))
        for node in self.nodes["method_definition"]:
            body = node.parent
            name = property_name(node.child_by_field_name("name"))
            if body is None or body.parent is None or body.parent.type not in CLASS_TYPES or name is None:
                continue
            owner = class_name(body.parent)
            if owner is not None:
                self.class_names.add(owner)
                self._add_function(node, f"{owner}.{name}")
        for node in self.nodes["arrow_function"] + self.nodes["function_expression"] + self.nodes["generator_function"]:
            name = self._assigned_name(node)
            if name is not None:
                self._add_function(node, name)
        for node in self.nodes["export_statement"]:
            self._index_export(node)
        for node in self.nodes["assignment_expression"]:
            left = node.child_by_field_name("left")
            right = unwrap(node.child_by_field_name("right"))
            if left is None or right is None or right.type != "identifier":
                continue
            if node_text(left) == MODULE_EXPORTS:
                self.report.default_export = node_text(right)

    def _assigned_name(self, node: Node) -> str | None:
        """Return the name a function expression receives from a declaration or an assignment"""

        parent = node.parent
        if parent is None:
            return None
        if parent.type == "variable_declarator":
            name = parent.child_by_field_name("name")
            value = parent.child_by_field_name("value")
            if name is not None and name.type == "identifier" and value is not None and value.id == node.id:
                return node_text(name)
        if parent.type == "assignment_expression":
            left = parent.child_by_field_name("left")
            right = parent.child_by_field_name("right")
            if left is None or right is None or right.id != node.id:
                return None
            if left.type == "identifier":
                return node_text(left)
            if node_text(left) == MODULE_EXPORTS:
                return DEFAULT_EXPORT
            if left.type == "member_expression" and node_text(left.child_by_field_name("object") or left) in EXPORT_OBJECTS:
                return property_name(left.child_by_field_name("property"))
        return None

    def _index_export(self, node: Node) -> None:
        """Record default exports and re-exports of an export statement"""

        is_default = any(child.type == DEFAULT_EXPORT for child in node.children)
        if is_default:
            declaration = node.child_by_field_name("declaration")
            value = unwrap(node.child_by_field_name("value"))
            if declaration is not None and declaration.type in NAMED_FUNCTION_TYPES:
                self._add_function(declaration, DEFAULT_EXPORT)
            elif value is not None and value.type == "identifier":
                self.report.default_export = node_text(value)
            elif value is not None and value.type in FUNCTION_TYPES:
                self._add_function(value, DEFAULT_EXPORT)
        source = node.child_by_field_name("source")
        if source is None or source.type != "string":
            return
        file = self.internal_file(self._decode_string(source).value)
        if file is None:
            return
        self._note_file(file)
        clauses = [child for child in node.named_children if child.type == "export_clause"]
        if not clauses:
            self.report.star_exports.append(file)
            return
        for specifier in clauses[0].named_children:
            if specifier.type != "export_specifier":
                continue
            name = property_name(specifier.child_by_field_name("name"))
            alias = property_name(specifier.child_by_field_name("alias"))
            if name is not None:
                self.report.reexports[alias or name] = (file, name)

    def _add_function(self, node: Node, name: str) -> None:
        """Index one function with the scope where its name is visible"""

        scope_start, scope_end = 0, len(self.source.data) + 1
        module_level = True
        current = node.parent
        while current is not None:
            if current.type in FUNCTION_TYPES or current.type in NAMED_FUNCTION_TYPES:
                scope_start, scope_end = current.start_byte, current.end_byte
                module_level = False
                break
            current = current.parent
        self.function_names.add(name)
        self.report.functions.append(RawFunction(name, node.start_byte, node.end_byte, scope_start, scope_end, module_level))

    def call_target(self, node: Node | None, offset: int) -> RawCall | None:
        """Turn a called or referenced expression into a call graph edge"""

        current = unwrap(node)
        if current is None:
            return None
        if current.type == "identifier":
            name = node_text(current)
            if name in self.internal:
                file, member = self.internal[name]
                return RawCall(offset, member or DEFAULT_EXPORT, file)
            if name in self.function_names:
                return RawCall(offset, name)
            return None
        if current.type != "member_expression":
            return None
        target = unwrap(current.child_by_field_name("object"))
        member = property_name(current.child_by_field_name("property"))
        if target is None or member is None:
            return None
        if target.type == "this":
            owner = enclosing_class(current)
            if owner is None:
                return None
            return RawCall(offset, f"{owner}.{member}")
        if target.type == "identifier" and node_text(target) in self.internal:
            file, imported = self.internal[node_text(target)]
            if imported is None or imported == DEFAULT_EXPORT:
                return RawCall(offset, member, file)
            return None
        if target.type == "identifier" and node_text(target) in self.class_names:
            return RawCall(offset, f"{node_text(target)}.{member}")
        if target.type == "call_expression":
            internal = self._required_internal(target)
            if internal is not None and internal[1] is None:
                return RawCall(offset, member, internal[0])
        return None

    def _find_calls(self) -> None:
        """Record calls, side-effect loads and function references passed as arguments"""

        for call in self.nodes["call_expression"] + self.nodes["new_expression"]:
            callee = call.child_by_field_name("function") or call.child_by_field_name("constructor")
            target = self.call_target(callee, call.start_byte)
            if target is not None:
                self.report.calls.append(target)
            specifier = self._loader_specifier(call)
            if specifier is not None:
                file = self.internal_file(specifier)
                if file is not None:
                    self._note_file(file)
            for argument in call_arguments(call):
                current = unwrap(argument)
                if current is not None and current.type in REFERENCE_TYPES:
                    reference = self.call_target(current, current.start_byte)
                    if reference is not None:
                        self.report.calls.append(reference)

    def _handler(self, node: Node | None) -> tuple[list[tuple[int, int]], list[RawCall]]:
        """Return the body range of an inline handler, or a graph edge for a handler given by name"""

        handler_range = self._function_range(node)
        if handler_range is not None:
            return [handler_range], []
        current = unwrap(node)
        if current is not None and current.type in REFERENCE_TYPES:
            entry = self.call_target(current, current.start_byte)
            if entry is not None:
                return [], [entry]
        return [], []

    def resolve(self, node: Node | None) -> tuple[str, bool] | None:
        """Return the qualified name of a member chain and whether its root was imported"""

        parts: list[str] = []
        current = unwrap(node)
        while current is not None and current.type in ("member_expression", "subscript_expression"):
            if current.type == "member_expression":
                name = property_name(current.child_by_field_name("property"))
            else:
                index = unwrap(current.child_by_field_name("index"))
                name = None
                if index is not None and index.type == "string":
                    name = self._decode_string(index).value
            if name is None:
                return None
            parts.insert(0, name)
            current = unwrap(current.child_by_field_name("object"))
        if current is None:
            return None
        if current.type == "call_expression":
            module = self._required_module(current)
            if module is None:
                return None
            return rewrite_javascript_chain(".".join([module, *parts])), True
        if current.type not in ("identifier", "this"):
            return None
        head = node_text(current)
        if head in self.aliases:
            return rewrite_javascript_chain(".".join([self.aliases[head], *parts])), True
        return ".".join([head, *parts]), False

    def _decode_string(self, node: Node) -> TextValue:
        """Decode a string or template literal into its runtime value"""

        pieces: list[Piece] = []
        dynamic = False
        for child in node.named_children:
            if child.type == "string_fragment":
                pieces.append(Piece(node_text(child), child.start_byte, True))
            elif child.type == "escape_sequence":
                pieces.append(Piece(decode_escape(node_text(child)), child.start_byte, False))
            elif child.type == "template_substitution":
                dynamic = True
                pieces.append(Piece(DYNAMIC_PLACEHOLDER, child.start_byte, False))
        return text_from_pieces(pieces, dynamic, node)

    def static_text(self, node: Node | None, depth: int = 0) -> TextValue:
        """Return the string value of an expression when it is known statically"""

        current = unwrap(node)
        if current is None or depth > MAX_CONSTANT_DEPTH:
            return dynamic_text()
        kind = current.type
        if kind in TEXT_TYPES:
            return self._decode_string(current)
        if kind == "binary_expression":
            operands = self._concatenation_operands(current)
            if operands is None:
                return dynamic_text()
            return join_texts([self.static_text(operand, depth) for operand in operands])
        if kind == "identifier":
            constant = self.constants.get(node_text(current))
            if constant is not None:
                return self.static_text(constant, depth + 1)
            return dynamic_text()
        if kind == "call_expression":
            return self._computed_text(current, depth)
        if kind == "member_expression":
            return self._member_text(current, depth)
        return dynamic_text()

    def _member_text(self, member: Node, depth: int) -> TextValue:
        """Read Enum.MEMBER or CONSTANT_OBJECT.key when it holds a literal of this file"""

        target = unwrap(member.child_by_field_name("object"))
        key = property_name(member.child_by_field_name("property"))
        if target is None or key is None or target.type != "identifier":
            return dynamic_text()
        enum_value = self.enum_members.get(f"{node_text(target)}.{key}")
        if enum_value is not None:
            return self.static_text(enum_value, depth + 1)
        container = self._as_object(target, depth + 1)
        if container is None:
            return dynamic_text()
        value = self._object_value(container, key)
        if value is None:
            return dynamic_text()
        return self.static_text(value, depth + 1)

    def _concatenation_operands(self, node: Node) -> list[Node] | None:
        """Flatten a chain of + operations into its operands, left to right"""

        operands: list[Node] = []
        stack: list[Node] = [node]
        while stack:
            current = stack.pop()
            operator = current.child_by_field_name("operator")
            if current.type == "binary_expression" and operator is not None and operator.type == "+":
                left = unwrap(current.child_by_field_name("left"))
                right = unwrap(current.child_by_field_name("right"))
                if left is None or right is None:
                    return None
                stack.append(right)
                stack.append(left)
            elif current.type == "binary_expression":
                return None
            else:
                operands.append(current)
        return operands

    def _computed_text(self, call: Node, depth: int) -> TextValue:
        """Read the literal behind dedent-like helpers and array joins, flagged as computed"""

        function = call.child_by_field_name("function")
        arguments_node = call.child_by_field_name("arguments")
        if function is None:
            return dynamic_text()
        if arguments_node is not None and arguments_node.type == "template_string":
            return mark_dynamic(self._decode_string(arguments_node))
        arguments = call_arguments(call)
        if node_text(function) in TEXT_HELPERS and arguments:
            return mark_dynamic(self.static_text(arguments[0], depth + 1))
        if function.type == "member_expression" and property_name(function.child_by_field_name("property")) == "join":
            array = unwrap(function.child_by_field_name("object"))
            if array is not None and array.type == "array":
                separator = TextValue(",")
                if arguments:
                    separator = self.static_text(arguments[0], depth + 1)
                parts: list[TextValue] = []
                for index, element in enumerate(array.named_children):
                    if index:
                        parts.append(TextValue(separator.value))
                    parts.append(self.static_text(element, depth + 1))
                return mark_dynamic(join_texts(parts))
        return dynamic_text()

    def _object_value(self, obj: Node, key: str) -> Node | None:
        """Return the value stored under a key in an object literal"""

        for child in obj.named_children:
            if child.type == "pair" and property_name(child.child_by_field_name("key")) == key:
                return child.child_by_field_name("value")
            if child.type == "method_definition" and property_name(child.child_by_field_name("name")) == key:
                return child
            if child.type == "shorthand_property_identifier" and node_text(child) == key:
                return self.constants.get(key, child)
        return None

    def _as_object(self, node: Node | None, depth: int = 0) -> Node | None:
        """Follow constants until an object literal is reached"""

        current = unwrap(node)
        if current is None or depth > MAX_CONSTANT_DEPTH:
            return None
        if current.type == "object":
            return current
        if current.type == "identifier" and node_text(current) in self.constants:
            return self._as_object(self.constants[node_text(current)], depth + 1)
        return None

    def _function_range(self, node: Node | None) -> tuple[int, int] | None:
        """Return the source range of a handler given inline or by name"""

        current = unwrap(node)
        if current is None:
            return None
        if current.type in FUNCTION_TYPES or current.type in NAMED_FUNCTION_TYPES:
            return current.start_byte, current.end_byte
        if current.type == "identifier":
            function = self.functions.get(node_text(current))
            if function is not None:
                return function.start_byte, function.end_byte
        return None

    def _is_handler(self, node: Node) -> bool:
        """Tell whether an argument is a function or the name of one"""

        current = unwrap(node)
        if current is None:
            return False
        if current.type in FUNCTION_TYPES:
            return True
        if current.type == "identifier" and node_text(current) in self.functions:
            return True
        return current.type in REFERENCE_TYPES and self.call_target(current, current.start_byte) is not None

    def _schema_parameters(
        self, node: Node | None, depth: int = 0
    ) -> tuple[list[ToolParameter], bool, list[tuple[int, int]]]:
        """Read tool parameters from a zod shape, z.object(...) or a JSON schema"""

        current = unwrap(node)
        if current is None:
            return [], False, []
        if depth > MAX_CONSTANT_DEPTH:
            return [], True, []
        if current.type == "object":
            properties = self._object_value(current, "properties")
            if properties is not None and self._object_value(current, "type") is not None:
                properties_object = self._as_object(properties)
                if properties_object is None:
                    return [], True, []
                return self._json_parameters(properties_object)
            return self._shape_parameters(current)
        if current.type == "identifier" and node_text(current) in self.constants:
            return self._schema_parameters(self.constants[node_text(current)], depth + 1)
        if current.type == "member_expression" and property_name(current.child_by_field_name("property")) == "shape":
            return self._schema_parameters(current.child_by_field_name("object"), depth + 1)
        if current.type == "call_expression":
            arguments = call_arguments(current)
            if arguments:
                return self._schema_parameters(arguments[0], depth + 1)
        return [], True, []

    def _shape_parameters(self, shape: Node) -> tuple[list[ToolParameter], bool, list[tuple[int, int]]]:
        """Read parameters from a zod raw shape object"""

        parameters = []
        ranges: list[tuple[int, int]] = []
        dynamic = False
        for child in shape.named_children:
            if child.type == "pair":
                name = property_name(child.child_by_field_name("key"))
                if name is None:
                    dynamic = True
                    continue
                type_name, description = self._zod_details(child.child_by_field_name("value"))
                text = None
                if description is not None:
                    text = description.value
                    ranges.extend(description.ranges)
                parameters.append(ToolParameter(name=name, type=type_name, description=text))
            elif child.type == "shorthand_property_identifier":
                parameters.append(ToolParameter(name=node_text(child)))
            elif child.type == "spread_element":
                dynamic = True
        return parameters, dynamic, ranges

    def _zod_details(self, node: Node | None) -> tuple[str | None, TextValue | None]:
        """Return the base type and .describe() text of a zod chain"""

        type_name = None
        description = None
        current = unwrap(node)
        while current is not None and current.type == "call_expression":
            function = current.child_by_field_name("function")
            if function is None or function.type != "member_expression":
                break
            name = property_name(function.child_by_field_name("property"))
            arguments = call_arguments(current)
            if name == "describe" and arguments and description is None:
                description = self.static_text(arguments[0])
            target = unwrap(function.child_by_field_name("object"))
            if target is not None and target.type == "identifier":
                type_name = name
            current = target
        return type_name, description

    def _json_parameters(self, properties: Node) -> tuple[list[ToolParameter], bool, list[tuple[int, int]]]:
        """Read parameters from the properties object of a JSON schema"""

        parameters = []
        ranges: list[tuple[int, int]] = []
        for child in properties.named_children:
            if child.type != "pair":
                continue
            name = property_name(child.child_by_field_name("key"))
            if name is None:
                continue
            value = self._as_object(child.child_by_field_name("value"))
            type_name = None
            description = None
            if value is not None:
                type_node = self._object_value(value, "type")
                if type_node is not None:
                    type_name = self.static_text(type_node).value or None
                description_node = self._object_value(value, "description")
                if description_node is not None:
                    text = self.static_text(description_node)
                    description = text.value
                    ranges.extend(text.ranges)
            parameters.append(ToolParameter(name=name, type=type_name, description=description))
        return parameters, False, ranges

    def _add_tool(
        self,
        name_node: Node | None,
        description: TextValue,
        offset: int,
        declaration: DeclarationKind,
        schema: Node | None,
        bodies: list[tuple[int, int]],
        entries: list[RawCall] | None = None,
    ) -> RawTool:
        """Build and record one tool"""

        name_text = self.static_text(name_node)
        name = name_text.value
        if name_text.dynamic and name_node is not None:
            name = node_text(name_node)
        parameters, dynamic, ranges = self._schema_parameters(schema)
        tool = RawTool(
            name=name,
            name_is_dynamic=name_text.dynamic,
            description=description,
            offset=offset,
            declaration=declaration,
            parameters=parameters,
            parameters_are_dynamic=dynamic,
            bodies=bodies,
            entries=entries or [],
            text_ranges=description.ranges + ranges,
        )
        self.report.tools.append(tool)
        return tool

    def _find_tools(self) -> None:
        """Find every supported way of declaring a tool"""

        for call in self.nodes["call_expression"]:
            function = call.child_by_field_name("function")
            if function is None or function.type != "member_expression":
                continue
            method = property_name(function.child_by_field_name("property"))
            arguments = call_arguments(call)
            if method == "tool" and arguments and not self.static_text(arguments[0]).dynamic:
                self._server_tool(call, arguments)
            elif method == "registerTool" and len(arguments) >= 2:
                self._register_tool(call, arguments)
            elif method == "addTool" and arguments:
                config = self._as_object(arguments[0])
                if config is not None:
                    self._object_tool(config, call.start_byte, DeclarationKind.ADD_TOOL_OBJECT, "parameters")
            elif method == "setRequestHandler" and len(arguments) >= 2:
                self._request_handler(arguments)
        for definition in self.nodes["class_declaration"] + self.nodes["class"]:
            self._tool_class(definition)
        self._find_low_level_tools()
        self._find_dispatch_blocks()

    def _server_tool(self, call: Node, arguments: list[Node]) -> None:
        """Read server.tool(name, description?, schema?, annotations?, handler)"""

        rest = arguments[1:]
        bodies: list[tuple[int, int]] = []
        entries: list[RawCall] = []
        if rest and self._is_handler(rest[-1]):
            bodies, entries = self._handler(rest[-1])
            rest = rest[:-1]
        description = TextValue()
        schema = None
        if rest:
            first = rest[0]
            if self._as_object(first) is None and unwrap(first) is not None and unwrap(first).type != "call_expression":
                description = self.static_text(first)
                rest = rest[1:]
            if rest:
                schema = rest[0]
        self._add_tool(arguments[0], description, call.start_byte, DeclarationKind.SERVER_TOOL, schema, bodies, entries)

    def _register_tool(self, call: Node, arguments: list[Node]) -> None:
        """Read server.registerTool(name, { description, inputSchema }, handler)"""

        config = self._as_object(arguments[1])
        description = TextValue()
        schema = None
        if config is None:
            description = dynamic_text()
        else:
            description_node = self._object_value(config, "description")
            if description_node is not None:
                description = self.static_text(description_node)
            schema = self._object_value(config, "inputSchema")
        bodies: list[tuple[int, int]] = []
        entries: list[RawCall] = []
        if len(arguments) > 2:
            bodies, entries = self._handler(arguments[2])
        tool = self._add_tool(
            arguments[0], description, call.start_byte, DeclarationKind.REGISTER_TOOL, schema, bodies, entries
        )
        if config is None:
            tool.parameters_are_dynamic = True

    def _object_tool(self, config: Node, offset: int, declaration: DeclarationKind, schema_key: str) -> RawTool | None:
        """Read a tool described by an object with name, description and a handler"""

        if config.id in self.seen_objects:
            return None
        self.seen_objects.add(config.id)
        description = TextValue()
        description_node = self._object_value(config, "description")
        if description_node is not None:
            description = self.static_text(description_node)
        bodies, entries = self._handler(self._object_value(config, "execute"))
        return self._add_tool(
            self._object_value(config, "name"),
            description,
            offset,
            declaration,
            self._object_value(config, schema_key),
            bodies,
            entries,
        )

    def _request_handler(self, arguments: list[Node]) -> None:
        """Remember low-level tools/list and tools/call handlers"""

        schema = unwrap(arguments[0])
        if schema is None:
            return
        method = node_text(schema)
        if schema.type == "string":
            method = self._decode_string(schema).value
        if method == LIST_TOOLS_METHOD or method.endswith(LIST_TOOLS_SCHEMAS):
            self.list_handlers.append(arguments[1])
        elif method == CALL_TOOL_METHOD or method.endswith(CALL_TOOL_SCHEMAS):
            bodies, entries = self._handler(arguments[1])
            for start, end in bodies:
                self.report.call_handlers.append(RawHandler(start, end))
            for entry in entries:
                self.report.call_handlers.append(RawHandler(reference=entry))

    def _tool_class(self, definition: Node) -> None:
        """Read a class that extends MCPTool with name and description fields"""

        heritage = None
        for child in definition.named_children:
            if child.type == "class_heritage":
                heritage = child
        if heritage is None or not TOOL_CLASS_PATTERN.search(node_text(heritage)):
            return
        body = definition.child_by_field_name("body")
        if body is None:
            return
        fields: dict[str, Node] = {}
        for member in body.named_children:
            if member.type not in FIELD_TYPES:
                continue
            name = property_name(member.child_by_field_name("name") or member.child_by_field_name("property"))
            value = member.child_by_field_name("value")
            if name is not None and value is not None:
                fields[name] = value
        if "name" not in fields:
            return
        description = TextValue()
        if "description" in fields:
            description = self.static_text(fields["description"])
        self._add_tool(
            fields["name"],
            description,
            definition.start_byte,
            DeclarationKind.TOOL_CLASS,
            fields.get("schema"),
            [(definition.start_byte, definition.end_byte)],
        )

    def _find_low_level_tools(self) -> None:
        """Find tool objects returned by low-level tools/list handlers"""

        roots: list[tuple[int, int]] = []
        pending: list[Node] = []
        for handler in self.list_handlers:
            current = unwrap(handler)
            if current is not None and current.type == "identifier" and node_text(current) in self.functions:
                current = self.functions[node_text(current)]
            if current is not None:
                pending.append(current)
        visited: set[int] = set()
        while pending:
            node = pending.pop()
            if node.id in visited or len(visited) > 1000:
                continue
            visited.add(node.id)
            roots.append((node.start_byte, node.end_byte))
            stack = [node]
            while stack:
                current = stack.pop()
                if current.type == "identifier" and node_text(current) in self.constants:
                    pending.append(self.constants[node_text(current)])
                stack.extend(current.named_children)
        for obj in self.nodes["object"]:
            if not any(start <= obj.start_byte < end for start, end in roots):
                continue
            if self._object_value(obj, "name") is None:
                continue
            if self._object_value(obj, "description") is None and self._object_value(obj, "inputSchema") is None:
                continue
            self._object_tool(obj, obj.start_byte, DeclarationKind.LOW_LEVEL, "inputSchema")

    def _find_dispatch_blocks(self) -> None:
        """Record switch cases and if branches that run when a tool name equals a known value"""

        for switch in self.nodes["switch_statement"]:
            value = switch.child_by_field_name("value")
            body = switch.child_by_field_name("body")
            if value is None or body is None or not NAME_REFERENCE_PATTERN.search(node_text(value)):
                continue
            pending: list[str] = []
            for case in body.named_children:
                if case.type != "switch_case":
                    pending = []
                    continue
                label = case.child_by_field_name("value")
                text = self.static_text(label)
                if label is not None and not text.dynamic:
                    pending.append(text.value)
                statements = [
                    child for child in case.named_children if label is None or child.id != label.id
                ]
                if not statements:
                    continue
                for literal in pending:
                    self.report.dispatch_blocks.append(RawBlock(literal, case.start_byte, case.end_byte))
                pending = []
        for statement in self.nodes["if_statement"]:
            condition = unwrap(statement.child_by_field_name("condition"))
            consequence = statement.child_by_field_name("consequence")
            if condition is None or consequence is None or condition.type != "binary_expression":
                continue
            operator = condition.child_by_field_name("operator")
            if operator is None or operator.type not in EQUALITY_OPERATORS:
                continue
            literal = self._compared_literal(condition)
            if literal is not None:
                self.report.dispatch_blocks.append(RawBlock(literal, consequence.start_byte, consequence.end_byte))

    def _compared_literal(self, condition: Node) -> str | None:
        """Return the known value compared to a tool name in name === value"""

        left = unwrap(condition.child_by_field_name("left"))
        right = unwrap(condition.child_by_field_name("right"))
        if left is None or right is None:
            return None
        for literal, other in ((left, right), (right, left)):
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
        """Return the network client factory used by an expression, like axios.create"""

        current = unwrap(node)
        if current is not None and current.type == "await_expression" and current.named_children:
            current = unwrap(current.named_children[0])
        if current is None or current.type not in ("call_expression", "new_expression"):
            return None
        callee = current.child_by_field_name("function") or current.child_by_field_name("constructor")
        resolved = self.resolve(callee)
        if resolved is not None and resolved[1] and resolved[0] in JAVASCRIPT_NETWORK_CLIENTS:
            return resolved[0]
        return None

    def _index_clients(self) -> None:
        """Remember variables and this.x fields that hold a network client"""

        for declarator in self.nodes["variable_declarator"]:
            name = declarator.child_by_field_name("name")
            constructor = self._client_constructor(declarator.child_by_field_name("value"))
            if name is not None and name.type == "identifier" and constructor is not None:
                self._bind_client(node_text(name), declarator, constructor)
        for assignment in self.nodes["assignment_expression"]:
            left = assignment.child_by_field_name("left")
            constructor = self._client_constructor(assignment.child_by_field_name("right"))
            if left is not None and constructor is not None:
                self._bind_client(node_text(left), assignment, constructor)

    def _bind_client(self, name: str, node: Node, constructor: str) -> None:
        """Record a client variable with the range where it is visible"""

        start, end = 0, len(self.source.data) + 1
        wanted = FUNCTION_TYPES | NAMED_FUNCTION_TYPES
        if name.startswith("this."):
            wanted = CLASS_TYPES
        current = node.parent
        while current is not None:
            if current.type in wanted:
                start, end = current.start_byte, current.end_byte
                break
            current = current.parent
        self.clients.append((name, start, end, constructor))

    def _client_of(self, name: str, offset: int) -> str | None:
        """Return the client factory behind a variable name at an offset"""

        best = None
        best_size = 0
        for client_name, start, end, constructor in self.clients:
            if client_name == name and start <= offset < end and (best is None or end - start < best_size):
                best = constructor
                best_size = end - start
        return best

    def _url_kind(self, arguments: list[Node], keys: tuple[str, ...] = JAVASCRIPT_URL_KEYS) -> UrlKind:
        """Tell whether the URL given to a network call is a literal, dynamic or absent"""

        if not arguments:
            return UrlKind.UNKNOWN
        first = unwrap(arguments[0])
        options = self._as_object(first)
        if options is not None:
            first = None
            for key in keys:
                first = first or self._object_value(options, key)
        if first is None:
            return UrlKind.UNKNOWN
        if self.static_text(first).dynamic:
            return UrlKind.DYNAMIC
        return UrlKind.LITERAL

    def _network_url_kind(self, qualified: str, arguments: list[Node]) -> UrlKind:
        """Return the URL kind of a call to a network global, module or client factory"""

        if qualified in JAVASCRIPT_NETWORK_CLIENTS:
            return self._url_kind(arguments, JAVASCRIPT_CLIENT_URL_KEYS)
        method = qualified.rsplit(".", 1)[-1]
        if qualified in JAVASCRIPT_URL_GLOBALS or "." not in qualified or method in NETWORK_CLIENT_METHODS:
            return self._url_kind(arguments)
        return UrlKind.UNKNOWN

    def _find_capabilities(self) -> None:
        """Match calls and environment access against the capability table"""

        self._index_clients()
        for call in self.nodes["call_expression"] + self.nodes["new_expression"]:
            self._check_call(call)
        for member in self.nodes["member_expression"]:
            self._check_env(member)

    def _check_call(self, call: Node) -> None:
        """Match one call or new expression against the JavaScript rules"""

        callee = call.child_by_field_name("function") or call.child_by_field_name("constructor")
        if callee is None:
            return
        arguments = call_arguments(call)
        if callee.type == "import":
            if arguments and arguments[0].type != "string":
                self._add(Capability.DYNAMIC_CODE, call, "import()")
            return
        if callee.type == "member_expression":
            method = property_name(callee.child_by_field_name("property"))
            target = callee.child_by_field_name("object")
            if method in NETWORK_CLIENT_METHODS and target is not None:
                constructor = self._client_of(node_text(target), call.start_byte)
                if constructor is not None:
                    self._add(Capability.NETWORK, call, f"{constructor}.{method}", self._url_kind(arguments))
                    return
        resolved = self.resolve(callee)
        if resolved is not None:
            qualified, imported = resolved
            if not imported and qualified == "require":
                if arguments and arguments[0].type != "string":
                    self._add(Capability.DYNAMIC_CODE, call, "require()")
                return
            if qualified in JAVASCRIPT_BUFFER_DECODERS:
                if len(arguments) > 1 and self.static_text(arguments[1]).value in JAVASCRIPT_BASE64_ENCODINGS:
                    self._add(Capability.BASE64_DECODE, call, qualified)
                return
            if not imported and qualified in JAVASCRIPT_STRING_TIMERS:
                if arguments and arguments[0].type in TEXT_TYPES:
                    self._add(Capability.DYNAMIC_CODE, call, qualified)
                return
            if imported and qualified in JAVASCRIPT_OPEN_FUNCTIONS:
                self._open_call(call, arguments, qualified)
                return
            if qualified in JAVASCRIPT_ENV_GETTERS:
                key_node = None
                if arguments:
                    key_node = arguments[0]
                self._env_key(call, key_node)
                return
            kind = RuleKind.GLOBAL
            if imported:
                kind = RuleKind.MODULE
            rule = match_rule(JAVASCRIPT_RULES, qualified, kind)
            if rule is not None and rule.capability is Capability.NETWORK:
                self._add(rule.capability, call, qualified, self._network_url_kind(qualified, arguments))
                return
            if rule is not None:
                self._add(rule.capability, call, qualified)
                return
        if callee.type == "member_expression":
            method = property_name(callee.child_by_field_name("property"))
            if method is None:
                return
            rule = match_rule(JAVASCRIPT_RULES, method, RuleKind.METHOD)
            if rule is not None:
                self._add(rule.capability, call, "." + method)

    def _open_call(self, call: Node, arguments: list[Node], qualified: str) -> None:
        """Classify fs.open as a read or a write from its flags argument"""

        capability = Capability.FS_READ
        detail = qualified
        if len(arguments) > 1:
            flags = self.static_text(arguments[1])
            detail = f"{qualified} flags={flags.value or '?'}"
            if flags.dynamic or any(character in flags.value for character in JAVASCRIPT_WRITE_FLAG_CHARS):
                capability = Capability.FS_WRITE
        self._add(capability, call, detail)

    def _env_key(self, node: Node, key_node: Node | None) -> None:
        """Classify an environment read as a secret or a plain variable"""

        key = None
        if key_node is not None:
            text = self.static_text(key_node)
            if not text.dynamic:
                key = text.value
        self._env_name(node, key)

    def _env_name(self, node: Node, key: str | None) -> None:
        """Record an environment read for a known or unknown variable name"""

        if key is not None and is_secret_name(key):
            self._add(Capability.ENV_READ_SECRET, node, key)
            return
        self._add(Capability.ENV_READ, node, key)

    def _check_env(self, member: Node) -> None:
        """Classify uses of process.env and its equivalents"""

        resolved = self.resolve(member)
        if resolved is None or resolved[0] not in JAVASCRIPT_ENV_OBJECTS:
            return
        parent = member.parent
        while parent is not None and parent.type in WRAPPER_TYPES:
            parent = parent.parent
        if parent is None:
            self._env_name(member, None)
            return
        target = unwrap(parent.child_by_field_name("object"))
        if parent.type == "member_expression" and target is not None and target.id == member.id:
            self._env_name(parent, property_name(parent.child_by_field_name("property")))
            return
        if parent.type == "subscript_expression" and target is not None and target.id == member.id:
            self._env_key(parent, parent.child_by_field_name("index"))
            return
        if parent.type == "variable_declarator":
            pattern = parent.child_by_field_name("name")
            if pattern is not None and pattern.type == "object_pattern":
                self._env_pattern(parent, pattern)
                return
        self._env_name(member, None)

    def _env_pattern(self, declarator: Node, pattern: Node) -> None:
        """Classify each variable destructured from process.env"""

        for child in pattern.named_children:
            name = None
            if child.type == "shorthand_property_identifier_pattern":
                name = node_text(child)
            elif child.type == "pair_pattern":
                name = property_name(child.child_by_field_name("key"))
            elif child.type == "object_assignment_pattern":
                left = child.child_by_field_name("left")
                if left is not None:
                    name = node_text(left)
            if name is not None:
                self._env_name(child, name)

    def _find_strings(self) -> None:
        """Decode every literal for URLs, sensitive paths and invisible characters"""

        for node in self.nodes["string"] + self.nodes["template_string"]:
            value = self._decode_string(node)
            sensitive = find_sensitive_paths(value.value)
            if sensitive:
                detail = ", ".join(match for _, match in sensitive)
                self._add(Capability.SENSITIVE_PATH, node, detail)
            self.report.strings.append(RawString(value=value, offset=node.start_byte, sensitive=sensitive))


class JavaScriptAdapter(Adapter):
    """Class that analyzes JavaScript and TypeScript MCP servers"""

    language = "javascript"

    def accepts(self, path: Path) -> bool:
        """Accept JavaScript and TypeScript files, but not type declarations"""

        name = path.name.lower()
        if name.endswith(DECLARATION_SUFFIXES):
            return False
        return path.suffix.lower() in LANGUAGES_BY_SUFFIX

    def analyze_file(self, relative_path: str, source: SourceText, context: PackageContext) -> FileReport:
        """Analyze one JavaScript or TypeScript file with the matching grammar"""

        suffix = Path(relative_path).suffix.lower()
        language = LANGUAGES_BY_SUFFIX.get(suffix, JAVASCRIPT_LANGUAGE)
        return _JavaScriptFile(relative_path, source, language, context).run()

    def language_for(self, analyzed: list[str]) -> str:
        """Report typescript when at least one TypeScript file was analyzed"""

        if any(Path(path).suffix.lower() in TYPESCRIPT_SUFFIXES for path in analyzed):
            return "typescript"
        return "javascript"

    def install_scripts(self, server_dir: Path) -> list[InstallScript]:
        """Find npm install hooks and implicit node-gyp builds"""

        scripts = []
        manifest = load_json_object(server_dir / "package.json")
        text = read_text(server_dir / "package.json") or ""
        hooks = table(manifest, "scripts")
        for hook in INSTALL_HOOKS:
            command = hooks.get(hook)
            if not isinstance(command, str):
                continue
            line = 1
            for number, content in enumerate(text.splitlines(), start=1):
                if f'"{hook}"' in content:
                    line = number
                    break
            scripts.append(InstallScript(kind=f"npm_{hook}", file="package.json", line=line, command=command))
        if (server_dir / "binding.gyp").is_file() and "install" not in hooks and "preinstall" not in hooks:
            scripts.append(
                InstallScript(kind="npm_binding_gyp", file="binding.gyp", line=1, command="node-gyp rebuild")
            )
        return scripts
