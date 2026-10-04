from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("local")
    verb = "Add"
    text = verb + " two numbers together"

    @mcp.tool(description=text)
    def add(a: int, b: int) -> int:
        return a + b

    return mcp
