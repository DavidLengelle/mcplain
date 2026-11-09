from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("notes")

    @mcp.tool()
    def remove_note(identifier: str) -> str:
        """IMPORTANT: this deletes the file permanently, ask the user to confirm first."""
        return identifier

    return mcp
