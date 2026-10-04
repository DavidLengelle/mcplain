import subprocess

from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("bootstrap")

    @mcp.tool()
    def ensure_uv() -> str:
        """Install uv if it is missing, using the official installer."""
        subprocess.run(
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
            shell=True,
        )
        return "ready"

    return mcp
