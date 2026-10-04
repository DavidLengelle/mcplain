"""npm registry metadata and verified tarball download"""

import base64
import binascii
import hmac
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from mcplain.errors import FetchError
from mcplain.fetch.http import Download, SafeClient

REGISTRY_ROOT = "https://registry.npmjs.org"
REGISTRY_HOST = "registry.npmjs.org"
LATEST_TAG = "latest"
SHA512_PREFIX = "sha512-"


@dataclass(frozen=True)
class NpmRelease:
    """Class that holds one published npm version"""

    name: str
    version: str
    tarball: str
    integrity: str
    manifest: dict[str, Any]


def release_url(name: str, version: str) -> str:
    """Return the registry URL of one version or dist-tag of a package"""

    return f"{REGISTRY_ROOT}/{quote(name, safe='@')}/{quote(version, safe='')}"


def fetch_release(client: SafeClient, name: str, version: str | None) -> NpmRelease:
    """Read the metadata of the requested version, or of dist-tags.latest"""

    target = version or LATEST_TAG
    try:
        document = client.get_json(release_url(name, target))
    except FetchError as error:
        if error.code == "fetch.not_found":
            raise FetchError("fetch.npm_not_found", package=name, version=target) from error
        raise
    if not isinstance(document, dict) or document.get("name") != name:
        raise FetchError("fetch.unexpected_response", host=REGISTRY_HOST)
    dist = document.get("dist")
    resolved_version = document.get("version")
    if not isinstance(dist, dict) or not isinstance(resolved_version, str):
        raise FetchError("fetch.unexpected_response", host=REGISTRY_HOST)
    tarball = dist.get("tarball")
    if not isinstance(tarball, str):
        raise FetchError("fetch.unexpected_response", host=REGISTRY_HOST)
    integrity = dist.get("integrity")
    if not isinstance(integrity, str):
        integrity = ""
    return NpmRelease(name, resolved_version, tarball, integrity, document)


def expected_sha512(integrity: str) -> bytes:
    """Return the sha512 digest announced in an SRI integrity string"""

    for entry in integrity.split():
        if entry.startswith(SHA512_PREFIX):
            try:
                return base64.b64decode(entry[len(SHA512_PREFIX):], validate=True)
            except (binascii.Error, ValueError) as error:
                raise FetchError("fetch.integrity_missing") from error
    raise FetchError("fetch.integrity_missing")


def download_release(client: SafeClient, release: NpmRelease, destination: Path) -> Download:
    """Download the tarball and refuse it unless its sha512 matches"""

    expected = expected_sha512(release.integrity)
    download = client.download(release.tarball, destination)
    if not hmac.compare_digest(expected, download.sha512):
        raise FetchError("fetch.integrity_mismatch", package=release.name)
    return download
