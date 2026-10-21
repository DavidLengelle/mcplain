import httpx
from mcp.server import MCPServer

mcp = MCPServer("page-reader")
STATUS_URL = "https://status.example.com/health"


def make_client(timeout: float) -> httpx.AsyncClient:
    """Build the HTTP client shared by the tools"""
    return httpx.AsyncClient(timeout=timeout)


@mcp.tool()
async def read_page(url: str) -> str:
    """Return the text of a web page"""
    async with make_client(10.0) as client:
        response = await client.get(url)
        return response.text


@mcp.tool()
async def service_status() -> str:
    """Tell whether the status page answers"""
    async with make_client(5.0) as client:
        response = await client.get(STATUS_URL)
        return str(response.status_code)
