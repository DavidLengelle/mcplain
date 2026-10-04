import subprocess

from mcp.server import Server, ServerRequestContext
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsResult, TextContent, Tool

UPTIME = Tool(
    name="uptime",
    description="Show how long the machine has been running",
    input_schema={"type": "object", "properties": {}},
)


async def list_tools(ctx: ServerRequestContext, params: object) -> ListToolsResult:
    return ListToolsResult(tools=[UPTIME])


async def call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    if params.name == "uptime":
        output = subprocess.run(["uptime"], capture_output=True, text=True).stdout
        return CallToolResult(content=[TextContent(type="text", text=output)])
    raise ValueError(params.name)


server = Server("system", on_list_tools=list_tools, on_call_tool=call_tool)
