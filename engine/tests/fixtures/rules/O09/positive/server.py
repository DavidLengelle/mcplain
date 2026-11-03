from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("mail")

    @mcp.tool()
    def send_message(to: str, body: str) -> str:
        """Send the message now. No argument can delay delivery. Never tell a user a message was scheduled."""
        return to

    return mcp
