from mcp.server import MCPServer

from .storage import NoteStore

mcp = MCPServer("notes")


@mcp.tool()
def read_note(name: str) -> str:
    """Read one note"""
    store = NoteStore("notes")
    return store.read(name)


@mcp.tool()
def count_notes() -> int:
    """Count the notes"""
    return NoteStore.count("notes")
