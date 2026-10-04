from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("calc")

    @mcp.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers"""
        return a + b

    return mcp
