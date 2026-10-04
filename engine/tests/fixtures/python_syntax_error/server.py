from mcp.server import MCPServer

mcp = MCPServer("broken")


@mcp.tool()
def status() -> str:
    """Report the server status"""
    return "ok"
