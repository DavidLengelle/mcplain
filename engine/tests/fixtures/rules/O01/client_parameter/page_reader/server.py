import httpx
from mcp.server import MCPServer


async def send_get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    request = client.build_request("GET", url)
    return await client.send(request)


async def read_page(url: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await send_get(client, url)
        return response.text


def create_server() -> MCPServer:
    server = MCPServer("page-reader")

    @server.tool(name="read", description="Read the page at a URL.")
    async def read(url: str) -> str:
        return await read_page(url)

    return server
