from mcp.server import MCPServer

mcp = MCPServer("clean")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


@mcp.tool()
async def greet(name: str) -> str:
    """Return a friendly greeting"""
    return f"Hello, {name}!"
