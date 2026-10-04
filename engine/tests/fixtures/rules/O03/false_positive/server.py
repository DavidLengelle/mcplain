from fastmcp import FastMCP


def build() -> FastMCP:
    """Build tools from a downloaded OpenAPI spec."""
    return FastMCP.from_openapi("https://api.example.com/openapi.json")
