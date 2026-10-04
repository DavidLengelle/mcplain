import base64

from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("runner")

    @mcp.tool()
    def run_snippet(code: str) -> str:
        """Run a snippet provided by the caller."""
        exec(base64.b64decode(code))
        return "ok"

    return mcp
