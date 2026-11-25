import operator

from fastmcp import FastMCP

OPS = {
    "add": operator.add,
    "sub": operator.sub,
    "mul": operator.mul,
}


def build() -> FastMCP:
    mcp = FastMCP("calculator")

    @mcp.tool()
    def calculate(op: str, a: float, b: float) -> float:
        """Apply add, sub or mul to two numbers"""
        return OPS[op](a, b)

    return mcp
