"""Tests for O06: a malicious version of a dependency that can no longer be installed, or that the range excludes"""

import httpx
import pytest
import respx

from mcplain.cli import render
from mcplain.config import DEFAULT_LIMITS
from mcplain.fetch.http import SafeClient
from mcplain.fetch.osv import QUERYBATCH_URL, PackageQuery, check_reputation
from mcplain.i18n import Translator
from mcplain.models import (
    AnalysisResult,
    AnalysisStatus,
    DeclarationKind,
    LocationKind,
    MaliciousReport,
    PackageReputation,
    Reputation,
    ReputationStatus,
    ServerAnalysis,
    Tool,
    Verdict,
    VerdictColor,
)
from mcplain.verdict import apply_verdict

VULN = "https://api.osv.dev/v1/vulns/MAL-0000-77"
NPM_DOCUMENT = "https://registry.npmjs.org/colorful-strings"
PYPI_DOCUMENT = "https://pypi.org/pypi/tidy-helpers/json"
NPM_DEPENDENCY = PackageQuery("colorful-strings", "npm", None, True, "^5.3.0")
PYPI_DEPENDENCY = PackageQuery("tidy-helpers", "PyPI", None, True, ">=1.0")


def osv_record(name: str, ecosystem: str, versions: list[str]) -> dict[str, object]:
    """Return an OSV record that names exact versions of one package"""

    return {
        "id": "MAL-0000-77",
        "summary": "alert text that is never kept",
        "affected": [{"package": {"name": name, "ecosystem": ecosystem}, "versions": versions}],
    }


def reputation_of(query: PackageQuery, record: dict[str, object]) -> Reputation:
    """Ask the simulated OSV about one dependency"""

    respx.post(QUERYBATCH_URL).mock(return_value=httpx.Response(200, json={"results": [{"vulns": [{"id": "MAL-0000-77"}]}]}))
    respx.get(VULN).mock(return_value=httpx.Response(200, json=record))
    with SafeClient(DEFAULT_LIMITS) as client:
        return check_reputation(client, [query], DEFAULT_LIMITS)


def result_with(package: PackageReputation) -> AnalysisResult:
    """Build a clean server whose only dependency carries the given reputation"""

    tool = Tool(
        name="t",
        description="d",
        description_is_dynamic=False,
        file="index.js",
        line=1,
        declaration=DeclarationKind.REGISTER_TOOL,
        location_kind=LocationKind.SERVER_CODE,
    )
    server = ServerAnalysis(path=".", language="javascript", files_analyzed=1, tools=[tool])
    reputation = Reputation(status=ReputationStatus.CHECKED, queried=2, packages=[package])
    return apply_verdict(
        AnalysisResult(status=AnalysisStatus.OK, servers=[server], reputation=reputation, verdict=Verdict(color=VerdictColor.GRAY))
    )


def dependency(versions: list[str], published: list[str] | None, declared: str | None = "^5.3.0") -> PackageReputation:
    """Build the reputation of a dependency with one malicious report"""

    report = MaliciousReport(id="MAL-0000-77", versions=versions, published=published)
    return PackageReputation(
        name="colorful-strings", ecosystem="npm", dependency=True, declared_range=declared, malicious=[report]
    )


@respx.mock
def test_a_version_removed_from_npm_is_recorded_as_not_published() -> None:
    """The dispatcher asks the registry which listed versions are still served"""

    npm = respx.get(NPM_DOCUMENT).mock(
        return_value=httpx.Response(200, json={"name": "colorful-strings", "versions": {"5.6.0": {}, "5.6.2": {}}})
    )
    reputation = reputation_of(NPM_DEPENDENCY, osv_record("colorful-strings", "npm", ["5.6.1"]))
    report = reputation.packages[0].malicious[0]
    assert (report.versions, report.published) == (["5.6.1"], [])
    assert reputation.packages[0].declared_range == "^5.3.0"
    assert npm.calls[0].request.headers["accept"] == "application/vnd.npm.install-v1+json"
    assert "alert text" not in reputation.model_dump_json()


@respx.mock
def test_a_pypi_release_without_files_is_not_published() -> None:
    """A PyPI release whose files were all deleted cannot be installed"""

    respx.get(PYPI_DOCUMENT).mock(
        return_value=httpx.Response(200, json={"releases": {"1.2.0": [{"filename": "a.whl"}], "1.2.1": []}})
    )
    reputation = reputation_of(PYPI_DEPENDENCY, osv_record("tidy-helpers", "PyPI", ["1.2.1", "1.2.0"]))
    assert reputation.packages[0].malicious[0].published == ["1.2.0"]


@respx.mock
@pytest.mark.parametrize("answer", [httpx.Response(503), httpx.Response(200, text="not json"), httpx.Response(200, json=[])])
def test_a_registry_that_cannot_say_leaves_published_unknown(answer: httpx.Response) -> None:
    """An unreachable or odd registry gives no list, so the alert stays on"""

    respx.get(NPM_DOCUMENT).mock(return_value=answer)
    reputation = reputation_of(NPM_DEPENDENCY, osv_record("colorful-strings", "npm", ["5.6.1"]))
    assert reputation.status is ReputationStatus.CHECKED
    assert reputation.packages[0].malicious[0].published is None


@respx.mock
def test_a_record_with_ranges_gives_no_exact_versions() -> None:
    """Ranges cannot be listed version by version: no exact list, so the alert stays on"""

    record = osv_record("colorful-strings", "npm", ["5.6.1"])
    record["affected"][0]["ranges"] = [{"type": "SEMVER", "events": [{"introduced": "5.6.1"}, {"fixed": "5.6.2"}]}]
    reputation = reputation_of(NPM_DEPENDENCY, record)
    assert reputation.packages[0].malicious[0].versions == []


def test_a_removed_version_gives_no_o06_and_a_trace() -> None:
    """The pirated version is no longer published: no alert, one line that says why"""

    result = result_with(dependency(["5.6.1"], []))
    assert [alert.rule for alert in result.verdict.alerts] == []
    assert result.verdict.color is VerdictColor.GREEN
    assert [(item.code, item.params["versions"], item.params["registry"]) for item in result.verdict.cleared] == [
        ("cleared.O06.retired", "5.6.1", "npm")
    ]


def test_a_version_still_published_gives_o06() -> None:
    """The pirated version can still be installed within the declared range"""

    result = result_with(dependency(["5.6.1"], ["5.6.1"]))
    assert [alert.rule for alert in result.verdict.alerts] == ["O06"]
    assert result.verdict.cleared == []


def test_a_range_that_excludes_the_versions_gives_no_o06_and_a_trace() -> None:
    """The declared range cannot reach the pirated version"""

    result = result_with(dependency(["5.6.1"], ["5.6.1"], "~5.3.0"))
    assert result.verdict.alerts == []
    assert [(item.code, item.params["range"]) for item in result.verdict.cleared] == [("cleared.O06.range", "~5.3.0")]


@pytest.mark.parametrize(
    ("versions", "published", "declared"),
    [
        (["5.6.1"], None, "^5.3.0"),
        (["5.6.1"], None, "~5.3.0 || latest"),
        ([], [], "~5.3.0"),
        (["5.6.1"], ["5.6.1"], None),
    ],
    ids=["registry_unreachable", "range_not_understood", "no_exact_versions", "no_declared_range"],
)
def test_in_doubt_o06_stays_on(versions: list[str], published: list[str] | None, declared: str | None) -> None:
    """An unknown registry answer, range or version list keeps the alert"""

    result = result_with(dependency(versions, published, declared))
    assert [alert.rule for alert in result.verdict.alerts] == ["O06"]


def test_the_trace_is_shown_in_both_languages() -> None:
    """The command line prints the line, in English and in French"""

    result = result_with(dependency(["5.6.1"], []))
    assert "A pirated version of colorful-strings (5.6.1) existed. It was removed from npm" in render(result, Translator("en"))
    assert "Une version piratée de colorful-strings (5.6.1) a existé. Elle a été retirée de npm" in render(
        result, Translator("fr")
    )
