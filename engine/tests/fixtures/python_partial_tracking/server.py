from mcp.server import MCPServer


class WordIndex:
    """Words kept in memory"""

    def __init__(self) -> None:
        self.words: list[str] = []

    def search(self, text: str) -> list[str]:
        """Return the words that contain the text"""
        return [word for word in self.words if text in word]


def build(index: WordIndex) -> MCPServer:
    """Build the server around an index given by the caller"""
    mcp = MCPServer("word-index")

    @mcp.tool()
    def find(text: str) -> str:
        """Find the words that contain a text"""
        return ", ".join(index.search(text))

    @mcp.tool()
    def count(text: str) -> int:
        """Count the words of a text"""
        return len(text.split())

    return mcp
