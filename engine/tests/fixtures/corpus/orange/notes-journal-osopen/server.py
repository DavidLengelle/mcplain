import os

from mcp.server.fastmcp import FastMCP

JOURNAL = "journal.txt"


def build() -> FastMCP:
    mcp = FastMCP("notes-journal")

    @mcp.tool()
    def add_entry(text: str) -> str:
        """Add one line to the local journal"""
        fd = os.open(JOURNAL, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.write(fd, (text + "\n").encode("utf-8"))
        os.close(fd)
        return "added"

    return mcp
