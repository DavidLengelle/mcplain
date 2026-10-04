import shutil

from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("cleaner")

    @mcp.tool()
    def clean(folder: str) -> str:
        """Delete a folder and everything in it"""
        shutil.rmtree(folder)
        return "deleted"

    return mcp
