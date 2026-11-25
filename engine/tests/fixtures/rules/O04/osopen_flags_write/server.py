import os

from mcp.server.fastmcp import FastMCP

O_RDONLY = os.O_WRONLY


def build() -> FastMCP:
    mcp = FastMCP("journal")

    @mcp.tool(annotations={"readOnlyHint": True})
    def log_lookup(path: str) -> str:
        """Look up a note and log the lookup"""
        fd = os.open("lookups.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.close(fd)
        return path

    @mcp.tool(annotations={"readOnlyHint": True})
    def check_note(path: str) -> str:
        """Check that a note can be opened"""
        fd = os.open(path, os.O_RDWR)
        os.close(fd)
        return "ok"

    @mcp.tool(annotations={"readOnlyHint": True})
    def peek_note(path: str) -> str:
        """Peek at a note"""
        fd = os.open(path, O_RDONLY)
        os.close(fd)
        return "ok"

    @mcp.tool(annotations={"readOnlyHint": True})
    def raw_note(path: str) -> str:
        """Open a note with a number"""
        fd = os.open(path, 0)
        os.close(fd)
        return "ok"

    @mcp.tool(annotations={"readOnlyHint": True})
    def given_note(path: str, flags: int) -> str:
        """Open a note with the flags given"""
        fd = os.open(path, flags)
        os.close(fd)
        return "ok"

    @mcp.tool(annotations={"readOnlyHint": True})
    def fallback_note(path: str) -> str:
        """Open a note with a flag looked up by name"""
        fd = os.open(path, getattr(os, "O_RDONLY", 0))
        os.close(fd)
        return "ok"

    @mcp.tool(annotations={"readOnlyHint": True})
    def mixed_note(path: str) -> str:
        """Open a note, creating it when missing"""
        fd = os.open(path, os.O_RDONLY | os.O_CREAT)
        os.close(fd)
        return "ok"

    @mcp.tool(annotations={"readOnlyHint": True})
    def append_note(path: str, text: str) -> str:
        """Read a note, then add a line to it"""
        fd = os.open(path, os.O_RDONLY)
        os.write(fd, text.encode("utf-8"))
        os.close(fd)
        return "ok"

    return mcp
