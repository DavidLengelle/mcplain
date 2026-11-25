from fastmcp import FastMCP


read_note = lambda path: open(path, encoding="utf-8").read()


def build() -> FastMCP:
    mcp = FastMCP("notes")

    @mcp.tool()
    def show_note(path: str) -> str:
        """Show the text of a note"""
        return read_note(path)

    return mcp
