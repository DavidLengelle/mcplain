from mcp.server import MCPServer

mcp = MCPServer("tested")


@mcp.tool()
def double(value: int) -> int:
    """Double a number"""
    return value * 2
