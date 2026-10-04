"""Tests for network client tracking and the kind of URL given to network calls"""

from pathlib import Path

import pytest

from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.adapters.python import PythonAdapter
from mcplain.analyze import analyze_directory
from mcplain.capabilities import Capability
from mcplain.cli import render
from mcplain.i18n import Translator
from mcplain.models import Finding, UrlKind


def python_network(tmp_path: Path, source: str) -> list[Finding]:
    """Analyze one Python file and return its network findings"""

    (tmp_path / "server.py").write_text(source, encoding="utf-8")
    analysis = PythonAdapter().analyze(tmp_path)
    return [finding for finding in analysis.findings if finding.capability is Capability.NETWORK]


def javascript_network(tmp_path: Path, source: str) -> list[Finding]:
    """Analyze one JavaScript file and return its network findings"""

    (tmp_path / "index.js").write_text(source, encoding="utf-8")
    analysis = JavaScriptAdapter().analyze(tmp_path)
    return [finding for finding in analysis.findings if finding.capability is Capability.NETWORK]


@pytest.mark.parametrize(
    ("call", "kind"),
    [
        ('httpx.get("https://api.example.com/x")', UrlKind.LITERAL),
        ("httpx.get(url)", UrlKind.DYNAMIC),
        ('httpx.get(BASE + "/x")', UrlKind.LITERAL),
        ('httpx.get(f"{BASE}/x")', UrlKind.DYNAMIC),
        ('httpx.request("GET", "https://api.example.com/x")', UrlKind.LITERAL),
        ("httpx.request('GET', url=url)", UrlKind.DYNAMIC),
        ("socket.create_connection((host, 80))", UrlKind.UNKNOWN),
    ],
)
def test_python_url_kind(tmp_path: Path, call: str, kind: UrlKind) -> None:
    """Literals, constant concatenations and dynamic values are told apart"""

    source = f'import socket\n\nimport httpx\n\nBASE = "https://api.example.com"\n\n\ndef work(url, host):\n    {call}\n'
    [finding] = python_network(tmp_path, source)
    assert finding.url_kind is kind


def test_python_clients_from_assignments_and_with(tmp_path: Path) -> None:
    """Client variables created by assignment, with, async with and self.x are followed"""

    findings = python_network(
        tmp_path,
        '''import httpx
import requests
from aiohttp import ClientSession


def one(url):
    session = requests.Session()
    session.post("https://api.example.com/upload")


async def two(url):
    async with ClientSession() as session:
        await session.get(url)


def three():
    with httpx.Client(base_url="https://api.example.com") as client:
        client.get("/status")


class Api:
    def __init__(self):
        self.client = httpx.AsyncClient()

    async def fetch(self, url):
        return await self.client.get(url)


def unrelated(session):
    session.get("not a client")
''',
    )
    calls = [(finding.detail, finding.url_kind) for finding in findings]
    assert ("requests.Session.post", UrlKind.LITERAL) in calls
    assert ("aiohttp.ClientSession.get", UrlKind.DYNAMIC) in calls
    assert ("httpx.Client", UrlKind.LITERAL) in calls
    assert ("httpx.Client.get", UrlKind.LITERAL) in calls
    assert ("httpx.AsyncClient.get", UrlKind.DYNAMIC) in calls
    assert all(finding.function != "unrelated" for finding in findings)


@pytest.mark.parametrize(
    ("call", "kind"),
    [
        ('fetch("https://api.example.com/x")', UrlKind.LITERAL),
        ("fetch(url)", UrlKind.DYNAMIC),
        ('fetch(BASE + "/x")', UrlKind.LITERAL),
        ("fetch(`${BASE}/x`)", UrlKind.DYNAMIC),
        ("fetch(`https://api.example.com/x`)", UrlKind.LITERAL),
        ('axios({ url: "https://api.example.com/x" })', UrlKind.LITERAL),
        ("https.request({ hostname: host })", UrlKind.DYNAMIC),
        ("new WebSocket(url)", UrlKind.DYNAMIC),
        ("net.connect(80)", UrlKind.UNKNOWN),
    ],
)
def test_javascript_url_kind(tmp_path: Path, call: str, kind: UrlKind) -> None:
    """fetch, axios, https and WebSocket URLs are classified"""

    source = (
        'import axios from "axios";\nimport https from "https";\nimport net from "net";\n\n'
        f'const BASE = "https://api.example.com";\n\nexport function work(url, host) {{\n  {call};\n}}\n'
    )
    [finding] = javascript_network(tmp_path, source)
    assert finding.url_kind is kind


def test_javascript_clients(tmp_path: Path) -> None:
    """axios.create() results and this.client fields are followed"""

    findings = javascript_network(
        tmp_path,
        """import axios from "axios";

const api = axios.create({ baseURL: "https://api.example.com" });

export async function load(id) {
  return api.get(`/items/${id}`);
}

class Service {
  constructor() {
    this.http = axios.create();
  }

  send(url) {
    return this.http.post(url);
  }
}
""",
    )
    calls = [(finding.detail, finding.url_kind) for finding in findings]
    assert ("axios.create", UrlKind.LITERAL) in calls
    assert ("axios.create.get", UrlKind.DYNAMIC) in calls
    assert ("axios.create", UrlKind.UNKNOWN) in calls
    assert ("axios.create.post", UrlKind.DYNAMIC) in calls


def test_lowlevel_single_tool_network_through_client(fixtures: Path) -> None:
    """The only tool reaches client.get(url) inside async with AsyncClient() as client, via fetch_url"""

    analysis = PythonAdapter().analyze(fixtures / "python_lowlevel_single")
    [fetch] = analysis.tools
    get = [finding for finding in fetch.findings if finding.detail == "httpx.AsyncClient.get"]
    assert len(get) == 1
    assert get[0].url_kind is UrlKind.DYNAMIC
    assert [step.function for step in get[0].call_chain] == ["fetch_url"]
    text = render(analyze_directory(fixtures / "python_lowlevel_single"), Translator("en"))
    assert "        - network (network access):\n            via fetch_url (server.py:8), URL dynamic\n" in text
