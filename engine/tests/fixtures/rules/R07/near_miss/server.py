import requests
from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("reader")

    @mcp.tool()
    def read_page(url: str) -> str:
        """Fetch a page and return its text."""
        return requests.get(url).text

    return mcp
