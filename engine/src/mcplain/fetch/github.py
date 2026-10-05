"""GitHub metadata through the API and source archives through codeload"""

import re
from dataclasses import dataclass
from urllib.parse import quote

from mcplain.config import github_token
from mcplain.errors import FetchError
from mcplain.fetch.http import SafeClient

API_ROOT = "https://api.github.com"
CODELOAD_ROOT = "https://codeload.github.com"
API_HOST = "api.github.com"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
API_HEADERS: dict[str, str] = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
SHA_HEADERS: dict[str, str] = {
    "Accept": "application/vnd.github.sha",
    "X-GitHub-Api-Version": "2022-11-28",
}
RAW_HEADERS: dict[str, str] = {
    "Accept": "application/vnd.github.raw+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
FILE_ENTRY = "file"
MAX_SHA_RESPONSE_BYTES = 1024
MISSING_REF_STATUSES: frozenset[str] = frozenset({"404", "409", "422"})


@dataclass(frozen=True)
class RepositoryInfo:
    """Class that holds the GitHub metadata MCPlain needs"""

    owner: str
    repo: str
    default_branch: str
    size_kb: int


def github_host_headers() -> dict[str, dict[str, str]]:
    """Return the Authorization header for the GitHub API when a token is set"""

    token = github_token()
    if token is None:
        return {}
    return {API_HOST: {"Authorization": f"Bearer {token}"}}


class GitHubSource:
    """Class that reads GitHub metadata and downloads source archives"""

    def __init__(self, client: SafeClient) -> None:
        """Keep the client and a cache of resolved commits"""

        self.client = client
        self._commits: dict[tuple[str, str, str], str | None] = {}

    def repository(self, owner: str, repo: str) -> RepositoryInfo:
        """Read repository metadata: canonical name, default branch and size"""

        url = f"{API_ROOT}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
        try:
            data = self.client.get_json(url, API_HEADERS)
        except FetchError as error:
            if error.code == "fetch.not_found":
                raise FetchError("fetch.github_repo_not_found", repository=f"{owner}/{repo}") from error
            raise
        if not isinstance(data, dict):
            raise FetchError("fetch.unexpected_response", host=API_HOST)
        full_name = data.get("full_name")
        default_branch = data.get("default_branch")
        size = data.get("size")
        if not isinstance(full_name, str) or "/" not in full_name or not isinstance(default_branch, str):
            raise FetchError("fetch.unexpected_response", host=API_HOST)
        canonical_owner, canonical_repo = full_name.split("/", 1)
        size_kb = 0
        if isinstance(size, int):
            size_kb = size
        return RepositoryInfo(canonical_owner, canonical_repo, default_branch, size_kb)

    def resolve_commit(self, owner: str, repo: str, ref: str) -> str | None:
        """Return the commit SHA a reference points to, or None if it does not exist"""

        key = (owner.lower(), repo.lower(), ref)
        if key in self._commits:
            return self._commits[key]
        url = (
            f"{API_ROOT}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
            f"/commits/{quote(ref, safe='')}"
        )
        try:
            body = self.client.get_bytes(url, MAX_SHA_RESPONSE_BYTES, SHA_HEADERS)
        except FetchError as error:
            if error.code == "fetch.not_found" or (
                error.code == "fetch.http_error" and error.params.get("status") in MISSING_REF_STATUSES
            ):
                self._commits[key] = None
                return None
            raise
        sha = body.decode("ascii", errors="replace").strip()
        if not SHA_PATTERN.match(sha):
            raise FetchError("fetch.unexpected_response", host=API_HOST)
        self._commits[key] = sha
        return sha

    def folder_files(self, owner: str, repo: str, sha: str, folder: str) -> dict[str, int] | None:
        """Return the regular files of one folder at one commit with their sizes, or None if it is not a folder"""

        try:
            data = self.client.get_json(contents_url(owner, repo, sha, folder), API_HEADERS)
        except FetchError as error:
            if error.code == "fetch.not_found":
                return None
            raise
        if not isinstance(data, list):
            return None
        files: dict[str, int] = {}
        for entry in data:
            if not isinstance(entry, dict) or entry.get("type") != FILE_ENTRY:
                continue
            name = entry.get("name")
            size = entry.get("size")
            if isinstance(name, str) and isinstance(size, int):
                files[name] = size
        return files

    def file_text(self, owner: str, repo: str, sha: str, path: str, max_bytes: int) -> str:
        """Read one small file of one commit as text, without downloading the repository"""

        body = self.client.get_bytes(contents_url(owner, repo, sha, path), max_bytes, RAW_HEADERS)
        return body.decode("utf-8", errors="replace")


def contents_url(owner: str, repo: str, sha: str, path: str) -> str:
    """Return the contents API URL of a file or folder at one commit; an empty path is the root"""

    url = f"{API_ROOT}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/contents"
    if path:
        url = f"{url}/{quote(path, safe='/')}"
    return f"{url}?ref={quote(sha, safe='')}"


def archive_url(owner: str, repo: str, sha: str) -> str:
    """Return the codeload URL of the tar.gz archive of one commit"""

    return f"{CODELOAD_ROOT}/{quote(owner, safe='')}/{quote(repo, safe='')}/tar.gz/{sha}"
