from mcp.server import MCPServer

mcp = MCPServer("b")


@mcp.tool()
def echo(text: str) -> str:
    """Return the text unchanged"""
    return text
