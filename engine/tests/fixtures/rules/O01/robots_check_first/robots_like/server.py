from urllib.parse import urlparse, urlunparse

from httpx import AsyncClient
from mcp.server.fastmcp import FastMCP


def get_robots_txt_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))


async def check_robots(url: str) -> None:
    robots_url = get_robots_txt_url(url)
    async with AsyncClient() as client:
        await client.get(robots_url)


async def fetch_url(url: str) -> str:
    async with AsyncClient() as client:
        response = await client.get(url)
    return response.text


def build() -> FastMCP:
    mcp = FastMCP("reader")

    @mcp.tool()
    async def read_page(url: str) -> str:
        """Read a web page, for example https://example.com/page"""
        await check_robots(url)
        return await fetch_url(url)

    return mcp
