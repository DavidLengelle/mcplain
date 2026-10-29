from mcp.server import MCPServer

from clients import make_client

mcp = MCPServer("status-reader")


@mcp.tool()
async def service_status() -> str:
    """Tell whether the status page answers"""
    client = make_client()
    response = await client.get("https://status.example.com/health")
    return str(response.status_code)
