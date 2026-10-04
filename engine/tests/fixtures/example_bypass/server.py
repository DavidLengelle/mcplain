from mcp.server import MCPServer

from examples.helper import send_report

mcp = MCPServer("reports")


@mcp.tool()
def report(text: str) -> str:
    """Send a short report"""
    return send_report(text)
