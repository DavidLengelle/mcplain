from fastmcp import FastMCP


def make_reader():
    def read(path: str) -> str:
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    return read


def build() -> FastMCP:
    mcp = FastMCP("notes")
    reader = make_reader()

    @mcp.tool()
    def show_note(path: str) -> str:
        """Show the text of a note"""
        return reader(path)

    return mcp
