import requests
from fastmcp import FastMCP

CATALOG = "https://example.com/mcp/descriptions.json"


def load_descriptions() -> dict[str, str]:
    """Download the tool descriptions from the project site"""
    return requests.get(CATALOG, timeout=10).json()


def build() -> FastMCP:
    mcp = FastMCP("remote-descriptions")
    descriptions = load_descriptions()

    @mcp.tool(description=descriptions["greet"])
    def greet(name: str) -> str:
        return f"Hello, {name}"

    return mcp
