from typing import TYPE_CHECKING
from urllib.parse import quote

import httpx
from mcp.server import MCPServer

if TYPE_CHECKING:
    import requests

mcp = MCPServer("unit-converter")


def describe(client: httpx.Client | None = None, session: "requests.Session | None" = None) -> str:
    """Name the converter"""
    return "unit converter"


@mcp.tool()
def to_meters(feet: float) -> str:
    """Convert feet to meters"""
    try:
        return quote(str(round(feet * 0.3048, 4)))
    except httpx.TimeoutException:
        return "timeout"


@mcp.tool()
def explain(value: object) -> str:
    """Tell what kind of value was given"""
    if isinstance(value, (httpx.Response, httpx.Request)):
        return "an HTTP message"
    return describe()
