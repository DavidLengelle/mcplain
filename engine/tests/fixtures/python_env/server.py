import os

from mcp.server import MCPServer

mcp = MCPServer("env")


@mcp.tool()
def show_port() -> str:
    """Show the port the server listens on"""
    return os.environ["PORT"]


@mcp.tool()
def call_api() -> str:
    """Call the remote API"""
    return os.environ["API_KEY"][:4]
