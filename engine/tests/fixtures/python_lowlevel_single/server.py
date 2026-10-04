from httpx import AsyncClient
from mcp.server import Server
from mcp.types import TextContent, Tool


async def fetch_url(url: str) -> str:
    async with AsyncClient() as client:
        response = await client.get(url)
    return response.text


async def serve() -> None:
    server = Server("fetcher")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [Tool(name="fetch", description="Fetch a page", inputSchema={"type": "object", "properties": {}})]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        text = await fetch_url(arguments["url"])
        return [TextContent(type="text", text=text)]
