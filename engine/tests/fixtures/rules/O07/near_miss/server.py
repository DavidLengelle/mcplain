from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("calc")

    @mcp.tool()
    def add(a: int, b: int) -> int:
        """Add 🏴󠁧󠁢󠁳󠁣󠁴󠁿 👨‍👩‍👧 می‌خواهم"""
        return a + b

    return mcp
