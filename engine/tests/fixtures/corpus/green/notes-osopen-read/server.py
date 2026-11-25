import os

from mcp.server.fastmcp import FastMCP

NOTES = "notes"


def build() -> FastMCP:
    mcp = FastMCP("notes-reader")

    @mcp.tool()
    def read_note(name: str) -> str:
        """Read the start of a note"""
        path = os.path.join(NOTES, name)
        if not os.path.exists(path):
            return ""
        fd = os.open(path, os.O_RDONLY)
        data = os.read(fd, 4096)
        os.close(fd)
        return data.decode("utf-8", errors="replace")

    return mcp
