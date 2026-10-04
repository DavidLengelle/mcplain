from fastmcp import FastMCP

from notes_server import shell

from .runner import run_command

mcp = FastMCP("notes")


@mcp.tool
def run(command: str) -> str:
    """Run a command"""
    return run_command(command)


@mcp.tool
def disk() -> str:
    """Show the disk usage"""
    return shell.disk_usage()
