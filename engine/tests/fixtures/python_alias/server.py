import subprocess as sp
from os import system as run_shell

from mcp.server import MCPServer

mcp = MCPServer("alias")


@mcp.tool()
def list_files(folder: str) -> str:
    """List the files of a folder"""
    return sp.run(["ls", folder], capture_output=True, text=True).stdout


@mcp.tool()
def clear_screen() -> str:
    """Clear the terminal"""
    run_shell("clear")
    return "done"
