import functools

from fastmcp import FastMCP


def read_note(path: str, encoding: str) -> str:
    with open(path, encoding=encoding) as handle:
        return handle.read()


def build() -> FastMCP:
    mcp = FastMCP("notes")
    reader = functools.partial(read_note, encoding="utf-8")

    @mcp.tool()
    def show_note(path: str) -> str:
        """Show the text of a note"""
        return reader(path)

    return mcp
