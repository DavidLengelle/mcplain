import shlex
import subprocess

from mcp.server.fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("terminal")

    @mcp.tool()
    def run(command: str = "echo hello") -> str:
        """Run a command chosen by the assistant, for example echo hello, and return what it prints"""
        completed = subprocess.run(shlex.split(command), capture_output=True, text=True, timeout=30)
        return completed.stdout + completed.stderr

    return mcp
