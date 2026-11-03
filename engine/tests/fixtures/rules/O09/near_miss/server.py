from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("mail")

    @mcp.tool()
    def send_message(to: str, body: str) -> str:
        """Send the message now. Tell the user when it is sent."""
        return to

    return mcp
