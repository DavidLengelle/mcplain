from pathlib import Path

from mcp.server.fastmcp import FastMCP

NOTES = Path("notes")


def keep(target: Path, text: str) -> None:
    with target.open("w", encoding="utf-8") as handle:
        handle.write(text)


def build() -> FastMCP:
    mcp = FastMCP("notes-keeper")

    @mcp.tool()
    def save_note(name: str, text: str) -> str:
        """Save a note in the notes folder"""
        keep(NOTES / name, text)
        return "saved"

    @mcp.tool()
    def rename_note(old: str, new: str) -> str:
        """Rename a note"""
        source = NOTES / old
        source.rename(NOTES / new)
        return "renamed"

    return mcp
