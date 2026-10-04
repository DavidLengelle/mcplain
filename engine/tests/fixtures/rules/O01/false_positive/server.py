import os

import requests
from fastmcp import FastMCP


def build() -> FastMCP:
    mcp = FastMCP("weather")

    @mcp.tool()
    def forecast(city: str) -> str:
        """Get the forecast for a city."""
        base = os.getenv("WEATHER_API_URL", "https://api.weather.example.com")
        return requests.get(base + "/forecast", params={"city": city}).text

    return mcp
