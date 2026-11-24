"""Small helpers shared by the routes of the API: errors as codes, answers never kept by a cache, bodies read with a limit"""

from fastapi import Request
from fastapi.responses import JSONResponse

NO_STORE = "no-store"


def error_response(status: int, code: str, params: dict[str, str] | None = None) -> JSONResponse:
    """Return an error as a code and its parameters, without any language"""

    return JSONResponse({"error": {"code": code, "params": params or {}}}, status_code=status)


def no_store(response: JSONResponse) -> JSONResponse:
    """Forbid any cache to keep an answer of the admin routes"""

    response.headers["Cache-Control"] = NO_STORE
    return response


async def read_body(request: Request, limit: int) -> bytes | None:
    """Read the request body, or return None as soon as it is longer than the limit"""

    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > limit):
        return None
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            return None
    return bytes(data)
