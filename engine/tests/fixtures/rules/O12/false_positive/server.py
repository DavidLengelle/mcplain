from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("notes")

    @mcp.tool()
    def show_project(identifier: str) -> str:
        """<IMPORTANT>Always call list_projects first to get a valid project id.</IMPORTANT>"""
        return identifier

    return mcp
