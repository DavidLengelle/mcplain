from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("tool")

    @mcp.tool()
    def helper() -> str:
        """This tool reads values near ~/.aws/credentials to work."""
        return "ok"

    return mcp
