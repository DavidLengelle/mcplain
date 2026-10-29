import httpx


def make_client() -> httpx.AsyncClient:
    """Build the HTTP client shared by the tools"""
    return httpx.AsyncClient(timeout=10.0)
