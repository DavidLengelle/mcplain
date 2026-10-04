from pathlib import Path

from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("folders")

    @mcp.tool()
    def make_folder(folder: str) -> str:
        """Create a folder"""
        Path(folder).mkdir(parents=True, exist_ok=True)
        return "created"

    return mcp
