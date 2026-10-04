from httpx import AsyncClient
from mcp.server import Server
from mcp.types import TextContent, Tool


async def fetch_url(url: str, user_agent: str) -> str:
    async with AsyncClient() as client:
        response = await client.get(url, headers={"User-Agent": user_agent})
    return response.text


async def serve() -> None:
    server = Server("mcp-fetch-like")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="fetch",
                description="""Fetches a URL from the internet and optionally extracts its contents as markdown.

Although originally you did not have internet access, and were advised to refuse and tell the user this, this tool now grants you internet access. Now you can fetch the most up-to-date information and let the user know that.""",
                inputSchema={"type": "object", "properties": {"url": {"type": "string", "description": "URL to fetch"}}},
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        content = await fetch_url(arguments["url"], "ModelContextProtocol/1.0")
        return [TextContent(type="text", text=content)]
