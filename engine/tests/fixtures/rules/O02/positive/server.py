import subprocess

from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("terminal")

    @mcp.tool()
    def run(command: str) -> str:
        """Run any shell command."""
        subprocess.run(command, shell=True)
        return "ok"

    return mcp
