from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("account")

    @mcp.tool()
    def show_account() -> str:
        """Show the account name and plan. Do not tell the user the value of the token."""
        return "account"

    return mcp
