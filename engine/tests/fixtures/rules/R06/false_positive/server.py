import base64

from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("agent")

    @mcp.tool()
    def start_agent() -> str:
        """Start the bundled bootstrap routine."""
        bootstrap = base64.b64decode("cHJpbnQoJ3JlYWR5Jyk=")
        exec(bootstrap)
        return "started"

    return mcp
