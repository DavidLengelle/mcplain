import requests
from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("items")

    @mcp.tool()
    def get_item(item_id: str) -> str:
        """Get an item by id from the fixed API."""
        return requests.get("https://api.example.com/items/" + item_id).text

    return mcp
