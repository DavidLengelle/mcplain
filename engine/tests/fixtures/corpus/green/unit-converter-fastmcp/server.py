from fastmcp import FastMCP

KM_PER_MILE = 1.609344


def build() -> FastMCP:
    mcp = FastMCP("unit-converter")

    @mcp.tool()
    def km_to_miles(km: float) -> float:
        """Convert a distance from kilometers to miles"""
        return km / KM_PER_MILE

    @mcp.tool()
    def celsius_to_fahrenheit(celsius: float) -> float:
        """Convert a temperature from Celsius to Fahrenheit"""
        return celsius * 9 / 5 + 32

    return mcp
