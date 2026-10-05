"""Tests for the OSV.dev reputation step, with a simulated OSV: no real network"""

import base64
import hashlib
import json

import httpx
import pytest
import respx
from builders import tar_gz

from mcplain.analyze import analyze_input
from mcplain.cli import render
from mcplain.config import DEFAULT_LIMITS, Limits
from mcplain.dependencies import npm_dependency_names, pypi_dependency_names, pyproject_dependency_names
from mcplain.fetch.http import SafeClient, check_url
from mcplain.fetch.osv import QUERYBATCH_URL, PackageQuery, check_reputation, covers_all_versions
from mcplain.i18n import Translator
from mcplain.models import ReputationStatus

VULNS = "https://api.osv.dev/v1/vulns"
PACKAGE = PackageQuery("evil-mcp", "npm", "1.0.16", False)
DEPENDENCY = PackageQuery("left-pad-ish", "npm", None, True)
OTHER = PackageQuery("clean-lib", "npm", None, True)
ALERT_TEXT = "Do not show this alert text"


def record(name: str, events: list[dict[str, str]], versions: list[str] | None = None) -> dict[str, object]:
    """Build an OSV record affecting one npm package"""

    affected: dict[str, object] = {"package": {"name": name, "ecosystem": "npm"}, "ranges": [{"type": "SEMVER", "events": events}]}
    if versions is not None:
        affected = {"package": {"name": name, "ecosystem": "npm"}, "versions": versions}
    return {"id": "MAL-2025-1", "summary": ALERT_TEXT, "details": ALERT_TEXT, "affected": [affected]}


def check(queries: list[PackageQuery], limits: Limits = DEFAULT_LIMITS) -> object:
    """Run the reputation check with a client limited to the allowed hosts"""

    with SafeClient(limits) as client:
        return check_reputation(client, queries, limits)


def test_osv_is_an_allowed_host() -> None:
    """api.osv.dev is on the allow list"""

    assert check_url(QUERYBATCH_URL) == "api.osv.dev"


@respx.mock
def test_package_at_exact_version_and_dependencies_by_name() -> None:
    """The analyzed package is queried at its version, dependencies by name; only MAL- identifiers count"""

    batch = respx.post(QUERYBATCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"vulns": [{"id": "MAL-2025-47604", "modified": "x"}, {"id": "GHSA-aaaa-bbbb-cccc"}]},
                    {"vulns": [{"id": "MAL-2024-11608"}, {"id": "MAL-bad id"}]},
                    {"vulns": [{"id": "PYSEC-2024-1"}]},
                ]
            },
        )
    )
    respx.get(f"{VULNS}/MAL-2024-11608").mock(
        return_value=httpx.Response(200, json=record("left-pad-ish", [{"introduced": "0"}]))
    )
    reputation = check([PACKAGE, DEPENDENCY, OTHER])
    sent = json.loads(batch.calls[0].request.content)
    assert sent["queries"][0] == {"package": {"name": "evil-mcp", "ecosystem": "npm"}, "version": "1.0.16"}
    assert sent["queries"][1] == {"package": {"name": "left-pad-ish", "ecosystem": "npm"}}
    assert reputation.status is ReputationStatus.CHECKED
    assert reputation.queried == 3
    assert [(package.name, package.dependency) for package in reputation.packages] == [
        ("evil-mcp", False),
        ("left-pad-ish", True),
    ]
    assert [report.id for report in reputation.packages[0].malicious] == ["MAL-2025-47604"]
    assert reputation.packages[1].malicious[0].all_versions
    assert ALERT_TEXT not in reputation.model_dump_json()


@pytest.mark.parametrize(
    ("affected", "expected"),
    [
        (record("left-pad-ish", [{"introduced": "0"}]), True),
        (record("left-pad-ish", [{"introduced": "0.0.0"}]), True),
        (record("left-pad-ish", [{"introduced": "1.0.16"}]), False),
        (record("left-pad-ish", [{"introduced": "0"}, {"fixed": "2.0.0"}]), False),
        (record("left-pad-ish", [], versions=["0.0.1", "0.0.2"]), False),
        (record("another-name", [{"introduced": "0"}]), False),
        ({"affected": "broken"}, False),
    ],
)
def test_covers_all_versions(affected: dict[str, object], expected: bool) -> None:
    """Only a range open from version 0 and never closed covers every version of the name"""

    assert covers_all_versions(affected, DEPENDENCY) is expected


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json={"results": []}),
        httpx.Response(200, content=b"not json"),
        httpx.Response(307, headers={"Location": "https://api.osv.dev/v1/other"}),
    ],
)
@respx.mock
def test_unreachable_or_odd_osv_gives_unavailable(response: httpx.Response) -> None:
    """An error, an odd answer or a redirect of the POST leaves the reputation unchecked"""

    respx.post(QUERYBATCH_URL).mock(return_value=response)
    assert check([PACKAGE]).status is ReputationStatus.UNAVAILABLE


@respx.mock
def test_connection_error_gives_unavailable() -> None:
    """OSV that cannot be reached leaves the reputation unchecked"""

    respx.post(QUERYBATCH_URL).mock(side_effect=httpx.ConnectError("down"))
    assert check([PACKAGE]).status is ReputationStatus.UNAVAILABLE


def test_nothing_to_query_sends_nothing() -> None:
    """With no package to check, no request is sent"""

    reputation = check([])
    assert (reputation.status, reputation.queried) == (ReputationStatus.CHECKED, 0)


def test_direct_dependencies_are_read_from_metadata() -> None:
    """dependencies of an npm manifest, Requires-Dist without extras, and pyproject dependencies"""

    manifest = {"dependencies": {"@scope/lib": "1", "zod": "3"}, "devDependencies": {"vitest": "1"}}
    assert npm_dependency_names(manifest) == ["@scope/lib", "zod"]
    info = {"requires_dist": ["httpx>=0.27", "Mcp<2,>=1.0", 'pytest; extra == "test"']}
    assert pypi_dependency_names(info) == ["httpx", "mcp"]
    assert pypi_dependency_names({"requires_dist": None}) == []
    assert pyproject_dependency_names({"project": {"dependencies": ["Pydantic_Core"]}}) == ["pydantic-core"]


def sri(data: bytes) -> str:
    """Return the npm integrity string of some bytes"""

    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


@respx.mock
def test_reputation_reaches_the_report_without_alert_text() -> None:
    """The whole pipeline queries OSV and the report shows identifiers and links only"""

    manifest = {"name": "evil-mcp", "version": "1.0.16", "dependencies": {"@modelcontextprotocol/sdk": "^1.0.0"}}
    server = b'import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";\n'
    data = tar_gz({"package.json": json.dumps(manifest).encode(), "index.js": server}, prefix="package/")
    tarball = "https://registry.npmjs.org/evil-mcp/-/evil-mcp-1.0.16.tgz"
    respx.get("https://registry.npmjs.org/evil-mcp/latest").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "evil-mcp",
                "version": "1.0.16",
                "dependencies": manifest["dependencies"],
                "dist": {"tarball": tarball, "integrity": sri(data)},
            },
        )
    )
    respx.get(tarball).mock(return_value=httpx.Response(200, content=data))
    respx.post(QUERYBATCH_URL).mock(
        return_value=httpx.Response(200, json={"results": [{"vulns": [{"id": "MAL-2025-47604"}]}, {}]})
    )
    result = analyze_input("npx -y evil-mcp")
    assert result.reputation is not None
    assert result.reputation.queried == 2
    text = render(result, Translator("fr"))
    assert "== Réputation (OSV.dev) ==" in text
    assert "evil-mcp 1.0.16 (paquet analysé)" in text
    assert "MAL-2025-47604 https://osv.dev/vulnerability/MAL-2025-47604" in text
    assert ALERT_TEXT not in text


@respx.mock
def test_unreachable_osv_is_said_in_the_report() -> None:
    """When OSV cannot be reached, the report says the reputation was not checked"""

    manifest = {"name": "calm-mcp", "version": "1.0.0", "dependencies": {"@modelcontextprotocol/sdk": "^1.0.0"}}
    server = b'import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";\n'
    data = tar_gz({"package.json": json.dumps(manifest).encode(), "index.js": server}, prefix="package/")
    tarball = "https://registry.npmjs.org/calm-mcp/-/calm-mcp-1.0.0.tgz"
    respx.get("https://registry.npmjs.org/calm-mcp/latest").mock(
        return_value=httpx.Response(
            200,
            json={"name": "calm-mcp", "version": "1.0.0", "dist": {"tarball": tarball, "integrity": sri(data)}},
        )
    )
    respx.get(tarball).mock(return_value=httpx.Response(200, content=data))
    respx.post(QUERYBATCH_URL).mock(side_effect=httpx.ConnectError("down"))
    result = analyze_input("npx -y calm-mcp")
    assert result.reputation is not None
    assert result.reputation.status is ReputationStatus.UNAVAILABLE
    text = render(result, Translator("fr"))
    assert "Réputation non vérifiée : OSV.dev est injoignable. Le verdict du code n'est pas modifié." in text
