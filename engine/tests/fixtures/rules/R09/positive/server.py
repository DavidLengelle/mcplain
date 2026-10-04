import subprocess

from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("git-tools")

    @mcp.tool()
    def git_log(branch: str) -> str:
        """Show the git log for a branch."""
        subprocess.run(f"git log {branch}", shell=True)
        return "ok"

    return mcp
