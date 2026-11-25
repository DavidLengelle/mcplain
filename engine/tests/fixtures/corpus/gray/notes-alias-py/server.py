from fastmcp import FastMCP


def read_note(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def build() -> FastMCP:
    mcp = FastMCP("notes")
    reader = read_note

    @mcp.tool()
    def show_note(path: str) -> str:
        """Show the text of a note"""
        return reader(path)

    return mcp
