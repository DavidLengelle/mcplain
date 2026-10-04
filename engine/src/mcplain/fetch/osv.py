"""Reputation of packages on OSV.dev: only malicious package identifiers (MAL-) are kept, never the alert text"""

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from mcplain.config import Limits
from mcplain.errors import FetchError
from mcplain.fetch.http import SafeClient
from mcplain.models import MaliciousReport, PackageReputation, Reputation, ReputationStatus

OSV_ROOT = "https://api.osv.dev/v1"
QUERYBATCH_URL = f"{OSV_ROOT}/querybatch"
OSV_HOST = "api.osv.dev"
MALICIOUS_PATTERN = re.compile(r"^MAL-\d{4}-\d{1,10}$")
OPEN_VERSIONS: frozenset[str] = frozenset({"0", "0.0.0"})
CLOSING_EVENTS: tuple[str, ...] = ("fixed", "last_affected", "limit")
PYPI_ECOSYSTEM = "PyPI"


@dataclass(frozen=True)
class PackageQuery:
    """Class that names a package to check: the analyzed one at its exact version, or a dependency by name"""

    name: str
    ecosystem: str
    version: str | None
    dependency: bool

    def payload(self) -> dict[str, Any]:
        """Return the OSV query of this package"""

        query: dict[str, Any] = {"package": {"name": self.name, "ecosystem": self.ecosystem}}
        if self.version is not None:
            query["version"] = self.version
        return query


def vulnerability_url(identifier: str) -> str:
    """Return the public osv.dev page of one identifier"""

    return f"https://osv.dev/vulnerability/{quote(identifier, safe='')}"


def check_reputation(client: SafeClient, queries: list[PackageQuery], limits: Limits) -> Reputation:
    """Ask OSV.dev which packages are known to be malicious; an unreachable OSV gives an unavailable status"""

    if not queries:
        return Reputation(status=ReputationStatus.CHECKED)
    selected = queries[: limits.max_reputation_queries]
    try:
        document = client.post_json(QUERYBATCH_URL, {"queries": [query.payload() for query in selected]})
        results = _results(document, len(selected))
        packages = []
        details = 0
        for query, result in zip(selected, results):
            identifiers = _malicious_ids(result)
            if not identifiers:
                continue
            reports = []
            for identifier in identifiers:
                all_versions = False
                if query.dependency and details < limits.max_reputation_details:
                    details += 1
                    record = client.get_json(f"{OSV_ROOT}/vulns/{quote(identifier, safe='')}")
                    all_versions = covers_all_versions(record, query)
                reports.append(MaliciousReport(id=identifier, all_versions=all_versions))
            packages.append(
                PackageReputation(
                    name=query.name,
                    ecosystem=query.ecosystem,
                    version=query.version,
                    dependency=query.dependency,
                    malicious=reports,
                )
            )
    except FetchError:
        return Reputation(status=ReputationStatus.UNAVAILABLE)
    return Reputation(status=ReputationStatus.CHECKED, queried=len(selected), packages=packages)


def _results(document: Any, count: int) -> list[dict[str, Any]]:
    """Check the shape of a querybatch answer"""

    if not isinstance(document, dict) or not isinstance(document.get("results"), list):
        raise FetchError("fetch.unexpected_response", host=OSV_HOST)
    results = document["results"]
    if len(results) != count or not all(isinstance(item, dict) for item in results):
        raise FetchError("fetch.unexpected_response", host=OSV_HOST)
    return results


def _malicious_ids(result: dict[str, Any]) -> list[str]:
    """Return the well-formed MAL- identifiers of one query result"""

    vulnerabilities = result.get("vulns")
    if not isinstance(vulnerabilities, list):
        return []
    identifiers = set()
    for vulnerability in vulnerabilities:
        if isinstance(vulnerability, dict) and isinstance(vulnerability.get("id"), str):
            if MALICIOUS_PATTERN.match(vulnerability["id"]):
                identifiers.add(vulnerability["id"])
    return sorted(identifiers)


def _normalize(name: str, ecosystem: str) -> str:
    """Compare package names the way the ecosystem does"""

    if ecosystem == PYPI_ECOSYSTEM:
        return re.sub(r"[-_.]+", "-", name).lower()
    return name


def covers_all_versions(record: Any, query: PackageQuery) -> bool:
    """Tell whether an OSV record affects every version of the package: a range open from 0 and never closed"""

    if not isinstance(record, dict) or not isinstance(record.get("affected"), list):
        return False
    wanted = _normalize(query.name, query.ecosystem)
    for affected in record["affected"]:
        if not isinstance(affected, dict):
            continue
        package = affected.get("package")
        if not isinstance(package, dict) or package.get("ecosystem") != query.ecosystem:
            continue
        if _normalize(str(package.get("name", "")), query.ecosystem) != wanted:
            continue
        for version_range in affected.get("ranges") or []:
            if isinstance(version_range, dict) and _open_range(version_range.get("events")):
                return True
    return False


def _open_range(events: Any) -> bool:
    """Tell whether range events start at version 0 and have no fix, last version or limit"""

    if not isinstance(events, list):
        return False
    opened = False
    for event in events:
        if not isinstance(event, dict):
            return False
        if any(key in event for key in CLOSING_EVENTS):
            return False
        if event.get("introduced") in OPEN_VERSIONS:
            opened = True
    return opened
