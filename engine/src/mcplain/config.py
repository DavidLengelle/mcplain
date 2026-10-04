"""Every limit and setting of MCPlain, gathered in one place"""

import os
from dataclasses import dataclass

from mcplain import __version__

MEGABYTE = 1024 * 1024

ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "api.github.com",
        "codeload.github.com",
        "registry.npmjs.org",
        "pypi.org",
        "files.pythonhosted.org",
    }
)

GITHUB_TOKEN_ENV = "GITHUB_TOKEN"

USER_AGENT = f"mcplain/{__version__} (+https://github.com/DavidLengelle/mcplain)"


@dataclass(frozen=True)
class Limits:
    """Class that groups every size, count and time limit"""

    max_download_bytes: int = 50 * MEGABYTE
    max_json_bytes: int = 10 * MEGABYTE
    max_extract_total_bytes: int = 200 * MEGABYTE
    max_extract_files: int = 20_000
    max_extract_file_bytes: int = 10 * MEGABYTE
    max_compression_ratio: int = 100
    compression_ratio_floor_bytes: int = 1 * MEGABYTE
    max_source_file_bytes: int = 5 * MEGABYTE
    request_timeout_seconds: float = 30.0
    fetch_timeout_seconds: float = 90.0
    max_redirects: int = 5
    max_listed_servers: int = 50
    max_snippet_chars: int = 200
    max_call_depth: int = 5
    minified_line_length: int = 1000


DEFAULT_LIMITS = Limits()


def github_token() -> str | None:
    """Return the optional GitHub token read from the environment"""

    value = os.environ.get(GITHUB_TOKEN_ENV, "").strip()
    if value:
        return value
    return None
