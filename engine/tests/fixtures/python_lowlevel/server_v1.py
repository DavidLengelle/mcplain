import httpx
import mcp.types as types
from mcp.server.lowlevel import Server

server = Server("dictionary")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="lookup",
            description="Look up the definition of a word",
            inputSchema={
                "type": "object",
                "properties": {"word": {"type": "string", "description": "The word to look up"}},
                "required": ["word"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "lookup":
        response = httpx.get("https://dictionary.example.org/api", params={"q": arguments["word"]})
        return [types.TextContent(type="text", text=response.text)]
    raise ValueError(name)
