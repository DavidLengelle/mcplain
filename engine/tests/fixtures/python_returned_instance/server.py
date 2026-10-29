from pathlib import Path

from mcp.server import MCPServer

mcp = MCPServer("reports")


class Report:
    """A report read from the reports folder"""

    def __init__(self, name: str) -> None:
        self.name = name

    def to_tool_result(self) -> str:
        """Return the text of the report"""
        return (Path("reports") / self.name).read_text(encoding="utf-8")


async def load_report(name: str) -> Report:
    """Find a report by name"""
    if not name:
        return Report("index.txt")
    return Report(name)


@mcp.tool()
async def show_report(name: str) -> str:
    """Show one report"""
    report = await load_report(name)
    return report.to_tool_result()
