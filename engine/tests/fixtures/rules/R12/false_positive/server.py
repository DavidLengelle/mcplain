from fastmcp import FastMCP

# This test fixture includes the phrase "ignore all previous instructions"
# as an example payload, to check that a scanner flags it.


def build() -> FastMCP:
    mcp = FastMCP("attack-demo")

    @mcp.tool()
    def demo(text: str) -> str:
        """Demonstrate a prompt-injection example for training."""
        return text

    return mcp
