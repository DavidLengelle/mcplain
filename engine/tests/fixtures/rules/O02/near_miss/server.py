import subprocess

from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("lister")

    @mcp.tool()
    def list_dir(path: str) -> str:
        """List a directory."""
        subprocess.run(["ls", "-la", path])
        return "ok"

    return mcp
