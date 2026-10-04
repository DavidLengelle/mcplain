from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("ssh-manager")

    @mcp.tool()
    def list_hosts() -> str:
        """Read ~/.ssh/config to list the hosts you can connect to."""
        return "host list"

    return mcp
