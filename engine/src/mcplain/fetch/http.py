"""Network client restricted to the allowed hosts, with streaming limits"""

import hashlib
import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from mcplain.config import ALLOWED_HOSTS, DEFAULT_LIMITS, MEGABYTE, USER_AGENT, Limits
from mcplain.errors import FetchError

REDIRECT_STATUSES: frozenset[int] = frozenset({301, 302, 303, 307, 308})
RATE_LIMIT_STATUSES: frozenset[int] = frozenset({403, 429})
CHUNK_SIZE = 64 * 1024


class Deadline:
    """Class that tracks the overall time budget of a fetch"""

    def __init__(self, seconds: float) -> None:
        """Start the countdown"""

        self._end = time.monotonic() + seconds

    def remaining(self) -> float:
        """Return the seconds left or raise when the budget is spent"""

        left = self._end - time.monotonic()
        if left <= 0:
            raise FetchError("fetch.timeout")
        return left


@dataclass(frozen=True)
class Download:
    """Class that describes a file downloaded to disk"""

    path: Path
    size: int
    sha256: str
    sha512: bytes
    url: str


def check_url(url: str) -> str:
    """Return the host of a URL after checking HTTPS and the allow list"""

    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as error:
        raise FetchError("fetch.host_not_allowed", host=url) from error
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        raise FetchError("fetch.insecure_url", url=url)
    if host not in ALLOWED_HOSTS or port not in (None, 443):
        raise FetchError("fetch.host_not_allowed", host=host)
    if parts.username is not None or parts.password is not None:
        raise FetchError("fetch.host_not_allowed", host=host)
    return host


class SafeClient:
    """Class that performs GET requests limited to the allowed hosts"""

    def __init__(
        self,
        limits: Limits = DEFAULT_LIMITS,
        host_headers: dict[str, dict[str, str]] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create the underlying client without automatic redirects"""

        self.limits = limits
        self.deadline = Deadline(limits.fetch_timeout_seconds)
        self._host_headers = host_headers or {}
        self._client = httpx.Client(
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={"User-Agent": USER_AGENT},
        )

    def __enter__(self) -> "SafeClient":
        """Return the client for use in a with block"""

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the client at the end of a with block"""

        self.close()

    def close(self) -> None:
        """Close the underlying connections"""

        self._client.close()

    @contextmanager
    def _open(
        self, url: str, headers: dict[str, str] | None, payload: object | None = None
    ) -> Iterator[httpx.Response]:
        """Open a streamed response, following GET redirects one checked hop at a time"""

        current = url
        method = "GET"
        if payload is not None:
            method = "POST"
        for _ in range(self.limits.max_redirects + 1):
            host = check_url(current)
            request_headers = dict(self._host_headers.get(host, {}))
            request_headers.update(headers or {})
            timeout = min(self.limits.request_timeout_seconds, self.deadline.remaining())
            request = self._client.build_request(
                method, current, headers=request_headers, timeout=timeout, json=payload
            )
            try:
                response = self._client.send(request, stream=True)
            except httpx.TimeoutException as error:
                raise FetchError("fetch.timeout") from error
            except httpx.HTTPError as error:
                raise FetchError("fetch.network_error", host=host) from error
            if response.status_code in REDIRECT_STATUSES:
                location = response.headers.get("location", "")
                response.close()
                if not location or payload is not None:
                    raise FetchError("fetch.bad_redirect", host=host)
                current = urljoin(current, location)
                continue
            try:
                self._check_status(response, host)
                yield response
            finally:
                response.close()
            return
        raise FetchError("fetch.too_many_redirects")

    def _check_status(self, response: httpx.Response, host: str) -> None:
        """Turn unexpected HTTP statuses into FetchError"""

        status = response.status_code
        if status == 200:
            return
        if status == 404:
            raise FetchError("fetch.not_found", url=str(response.url))
        if status in RATE_LIMIT_STATUSES and response.headers.get("x-ratelimit-remaining") == "0":
            raise FetchError("fetch.github_rate_limited")
        raise FetchError("fetch.http_error", status=status, host=host)

    def _read_stream(self, response: httpx.Response, max_bytes: int) -> Iterator[bytes]:
        """Yield response chunks and stop as soon as the size limit is passed"""

        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            raise FetchError("fetch.too_large", limit_mb=max(1, max_bytes // MEGABYTE))
        size = 0
        for chunk in response.iter_bytes(CHUNK_SIZE):
            size += len(chunk)
            if size > max_bytes:
                raise FetchError("fetch.too_large", limit_mb=max(1, max_bytes // MEGABYTE))
            self.deadline.remaining()
            yield chunk

    def get_bytes(self, url: str, max_bytes: int, headers: dict[str, str] | None = None) -> bytes:
        """Download a small response fully into memory"""

        with self._open(url, headers) as response:
            return b"".join(self._read_stream(response, max_bytes))

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        """Download and decode a JSON document"""

        body = self.get_bytes(url, self.limits.max_json_bytes, headers)
        try:
            return json.loads(body)
        except ValueError as error:
            raise FetchError("fetch.invalid_json", host=urlsplit(url).hostname or "") from error

    def post_json(self, url: str, payload: object) -> Any:
        """Send a JSON document and decode the JSON answer; redirects are refused"""

        with self._open(url, None, payload) as response:
            body = b"".join(self._read_stream(response, self.limits.max_json_bytes))
        try:
            return json.loads(body)
        except ValueError as error:
            raise FetchError("fetch.invalid_json", host=urlsplit(url).hostname or "") from error

    def download(self, url: str, destination: Path, headers: dict[str, str] | None = None) -> Download:
        """Stream a file to disk while hashing it and enforcing the size limit"""

        request_headers = {"Accept-Encoding": "identity"}
        request_headers.update(headers or {})
        sha256 = hashlib.sha256()
        sha512 = hashlib.sha512()
        size = 0
        with self._open(url, request_headers) as response, destination.open("xb") as handle:
            for chunk in self._read_stream(response, self.limits.max_download_bytes):
                size += len(chunk)
                sha256.update(chunk)
                sha512.update(chunk)
                handle.write(chunk)
            final_url = str(response.url)
        return Download(destination, size, sha256.hexdigest(), sha512.digest(), final_url)
