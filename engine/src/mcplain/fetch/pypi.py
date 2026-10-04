"""PyPI JSON API metadata and verified file download"""

import hmac
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from mcplain.errors import FetchError
from mcplain.fetch.http import Download, SafeClient

PYPI_ROOT = "https://pypi.org/pypi"
PYPI_HOST = "pypi.org"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
WHEEL_ARTIFACT = "wheel"
PLATFORM_WHEEL_ARTIFACT = "platform_wheel"
SDIST_ARTIFACT = "sdist"


@dataclass(frozen=True)
class PypiRelease:
    """Class that holds the chosen file of one PyPI release"""

    name: str
    version: str
    url: str
    filename: str
    sha256: str
    artifact: str
    info: dict[str, Any]


def is_pure_wheel(filename: str) -> bool:
    """Tell whether a wheel file name is pure Python for Python 3"""

    if not filename.endswith(".whl"):
        return False
    parts = filename[: -len(".whl")].split("-")
    if len(parts) < 5:
        return False
    python_tag, abi_tag, platform_tag = parts[-3], parts[-2], parts[-1]
    return "py3" in python_tag.split(".") and abi_tag == "none" and platform_tag == "any"


def choose_file(files: list[dict[str, Any]]) -> tuple[dict[str, Any], str] | None:
    """Prefer a pure Python wheel, then the sdist, then any other wheel"""

    usable = [entry for entry in files if isinstance(entry, dict) and not entry.get("yanked")]
    for entry in usable:
        if entry.get("packagetype") == "bdist_wheel" and is_pure_wheel(str(entry.get("filename", ""))):
            return entry, WHEEL_ARTIFACT
    for entry in usable:
        if entry.get("packagetype") == "sdist":
            return entry, SDIST_ARTIFACT
    for entry in usable:
        if entry.get("packagetype") == "bdist_wheel":
            return entry, PLATFORM_WHEEL_ARTIFACT
    return None


def fetch_release(client: SafeClient, name: str, version: str | None) -> PypiRelease:
    """Read the requested or latest release and choose the file to analyze"""

    url = f"{PYPI_ROOT}/{quote(name, safe='')}/json"
    if version is not None:
        url = f"{PYPI_ROOT}/{quote(name, safe='')}/{quote(version, safe='')}/json"
    try:
        document = client.get_json(url)
    except FetchError as error:
        if error.code == "fetch.not_found":
            raise FetchError("fetch.pypi_not_found", package=name, version=version or "latest") from error
        raise
    if not isinstance(document, dict):
        raise FetchError("fetch.unexpected_response", host=PYPI_HOST)
    info = document.get("info")
    files = document.get("urls")
    if not isinstance(info, dict) or not isinstance(files, list):
        raise FetchError("fetch.unexpected_response", host=PYPI_HOST)
    choice = choose_file(files)
    if choice is None:
        raise FetchError("fetch.pypi_no_files", package=name)
    entry, artifact = choice
    digests = entry.get("digests")
    sha256 = ""
    if isinstance(digests, dict) and isinstance(digests.get("sha256"), str):
        sha256 = digests["sha256"].lower()
    file_url = entry.get("url")
    if not isinstance(file_url, str):
        raise FetchError("fetch.unexpected_response", host=PYPI_HOST)
    return PypiRelease(
        name=str(info.get("name") or name),
        version=str(info.get("version") or version or ""),
        url=file_url,
        filename=str(entry.get("filename", "")),
        sha256=sha256,
        artifact=artifact,
        info=info,
    )


def download_release(client: SafeClient, release: PypiRelease, destination: Path) -> Download:
    """Download the chosen file and refuse it unless its sha256 matches"""

    if not SHA256_PATTERN.match(release.sha256):
        raise FetchError("fetch.integrity_missing")
    download = client.download(release.url, destination)
    if not hmac.compare_digest(release.sha256, download.sha256):
        raise FetchError("fetch.integrity_mismatch", package=release.name)
    return download
