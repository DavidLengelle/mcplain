from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("mailer")

    @mcp.tool()
    def send_email(to: str, subject: str, body: str, bcc: str | None = None) -> str:
        """Send an email."""
        message = {"to": to, "subject": subject, "body": body, "bcc": bcc}
        return str(message)

    return mcp
