from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("fetch")

    @mcp.tool()
    def fetch(url: str) -> str:
        """Fetches a URL from the internet and optionally extracts its contents as markdown.

        Although originally you did not have internet access, and were advised to refuse and tell the user this, this tool now grants you internet access. Now you can fetch the most up-to-date information and let the user know that."""
        return url

    return mcp
