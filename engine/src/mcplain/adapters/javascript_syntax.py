"""Small helpers that read JavaScript and TypeScript syntax trees, shared by the adapter and its flow lowering"""

from tree_sitter import Node

from mcplain.adapters.common import node_text

WRAPPER_TYPES: frozenset[str] = frozenset(
    {"parenthesized_expression", "as_expression", "satisfies_expression", "non_null_expression"}
)


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
