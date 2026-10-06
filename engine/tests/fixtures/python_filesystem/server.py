from pathlib import Path

from mcp.server import MCPServer

mcp = MCPServer("notes-files")
ROOT = Path("notes")


@mcp.tool()
def read_note(name: str) -> str:
    """Read one note from the notes folder"""
    return (ROOT / name).read_text(encoding="utf-8")


@mcp.tool()
def write_note(name: str, text: str) -> str:
    """Write one note into the notes folder"""
    (ROOT / name).write_text(text, encoding="utf-8")
    return "saved"


@mcp.tool()
def count_words(text: str) -> int:
    """Count the words of a text"""
    return len(text.split())
