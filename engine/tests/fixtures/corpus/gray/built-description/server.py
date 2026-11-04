import os
import platform

from fastmcp import FastMCP


def describe() -> str:
    """Build the description from the machine the server starts on"""
    return f"Return the number of processors of this {platform.system()} {platform.machine()} machine"


def build() -> FastMCP:
    mcp = FastMCP("cpu-count")

    @mcp.tool(description=describe())
    def cpu_count() -> int:
        return os.cpu_count() or 1

    return mcp
