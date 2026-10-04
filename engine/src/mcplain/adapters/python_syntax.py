"""Small helpers that read Python syntax trees, shared by the Python adapter and its flow lowering"""

from tree_sitter import Node

from mcplain.adapters.common import node_text


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
