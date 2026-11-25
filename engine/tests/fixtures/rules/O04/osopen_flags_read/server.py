import os
from os import O_NOFOLLOW as NO_FOLLOW
from os import O_RDONLY

from mcp.server.fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("journal")

    @mcp.tool(annotations={"readOnlyHint": True})
    def read_note(path: str) -> str:
        """Read the start of a note"""
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        data = os.read(fd, 4096)
        os.close(fd)
        return data.decode("utf-8", errors="replace")

    @mcp.tool(annotations={"readOnlyHint": True})
    def read_imported(path: str) -> str:
        """Read a note with imported flags"""
        fd = os.open(path, (O_RDONLY | NO_FOLLOW))
        data = os.read(fd, 4096)
        os.close(fd)
        return data.decode("utf-8", errors="replace")

    @mcp.tool(annotations={"readOnlyHint": True})
    def note_size(path: str) -> int:
        """Tell the size of a note"""
        if not os.path.isfile(path):
            return 0
        return os.path.getsize(path)

    return mcp
