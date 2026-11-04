import mcp.types as types
from mcp.server.lowlevel import Server


def word_count(text: str) -> int:
    """Count the words of a text"""
    return len(text.split())


def build() -> Server:
    server = Server("text-tools")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="count_words",
                description="Count the words of a text",
                inputSchema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
            ),
            types.Tool(
                name="shout",
                description="Return the text in capital letters",
                inputSchema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        if name == "count_words":
            return [types.TextContent(type="text", text=str(word_count(arguments["text"])))]
        if name == "shout":
            return [types.TextContent(type="text", text=arguments["text"].upper())]
        raise ValueError(name)

    return server
