from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("tool")

    @mcp.tool()
    def helper() -> str:
        """A simple helper that adds things up."""
        return "ok"

    return mcp
