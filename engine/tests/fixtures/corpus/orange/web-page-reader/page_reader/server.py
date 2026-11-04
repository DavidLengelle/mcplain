import httpx
from mcp.server.fastmcp import FastMCP

MAX_CHARS = 20000


def fetch_text(url: str) -> str:
    """Download a page and keep its first characters"""
    response = httpx.get(url, follow_redirects=True, timeout=10)
    return response.text[:MAX_CHARS]


def build() -> FastMCP:
    mcp = FastMCP("page-reader")

    @mcp.tool()
    def read_page(url: str) -> str:
        """Download a web page and return its text"""
        return fetch_text(url)

    return mcp
