from mcp.server.fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("unit-notes")

    @mcp.tool()
    def miles_to_kilometers(miles: float) -> float:
        """Convert a distance in miles to kilometers"""
        return miles * 1.609344

    return mcp
