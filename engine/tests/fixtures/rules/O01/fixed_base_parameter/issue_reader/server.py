import httpx
from mcp.server import MCPServer

API_BASE = "https://api.example.com/v1/"


async def read_issue(client: httpx.AsyncClient, issue_id: str) -> str:
    response = await client.get(f"issues/{issue_id}/")
    return response.text


def create_server() -> MCPServer:
    server = MCPServer("issue-reader")
    client = httpx.AsyncClient(base_url=API_BASE)

    @server.tool(name="issue", description="Read one issue by its number.")
    async def issue(issue_id: str) -> str:
        return await read_issue(client, issue_id)

    return server
