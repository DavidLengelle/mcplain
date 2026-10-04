import os

import requests
from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("weather")

    @mcp.tool()
    def weather(city: str) -> str:
        """Get the weather for a city."""
        key = os.environ["API_KEY"]
        requests.get(
            "https://api.weather.invalid/forecast",
            headers={"Authorization": key},
            params={"city": city},
        )
        return "ok"

    return mcp
