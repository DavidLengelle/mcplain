import subprocess

from fastmcp import FastMCP


ALLOWED = {"status", "diff", "log"}


def build() -> FastMCP:
    mcp = FastMCP("git-menu")

    @mcp.tool()
    def git(command: str) -> str:
        """Run one of a fixed set of git commands."""
        if command not in ALLOWED:
            return "not allowed"
        subprocess.run(command, shell=True)
        return "ok"

    return mcp
