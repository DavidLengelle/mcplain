import tempfile
import zipfile

from mcp.server.fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("notes-export")

    @mcp.tool()
    def export_notes(text: str) -> str:
        """Pack a note into a zip archive in a temporary folder"""
        folder = tempfile.mkdtemp(prefix="notes-")
        archive = folder + "/notes.zip"
        with zipfile.ZipFile(archive, "w") as packed:
            packed.writestr("note.txt", text)
        return archive

    return mcp
