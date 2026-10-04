from pathlib import Path

import httpx
from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("reader")

    @mcp.tool()
    def read(path: str) -> str:
        """Read a text file"""
        return Path(path).read_text()

    @mcp.tool()
    def status() -> str:
        """Read the status page"""
        return httpx.get("https://example.com/status").text

    return mcp
