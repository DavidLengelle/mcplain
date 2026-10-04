import tempfile
from pathlib import Path

from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("summary")

    @mcp.tool()
    def summarize(text: str) -> str:
        """Summarize a text; keeps a scratch copy in a temporary folder"""
        scratch = Path(tempfile.gettempdir()) / "summary-scratch.txt"
        scratch.write_text(text)
        return text[:100]

    return mcp
