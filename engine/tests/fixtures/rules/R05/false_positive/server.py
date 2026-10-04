from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("mailer")

    @mcp.tool()
    def send_email(to: str, subject: str, body: str) -> str:
        """Send an email, archiving a copy for legal records."""
        message = {"to": to, "subject": subject, "body": body, "bcc": "archive@company.invalid"}
        return str(message)

    return mcp
