import requests
from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("fetcher")

    @mcp.tool()
    def fetch(url: str) -> str:
        """Fetch any URL and return its text."""
        return requests.get(url).text

    return mcp
