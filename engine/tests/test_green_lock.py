"""Tests for the green lock: a network library imported and used, with no request recognized, is never green"""

from pathlib import Path

import pytest

from mcplain.adapters.javascript import JavaScriptAdapter
from mcplain.adapters.python import PythonAdapter
from mcplain.analyze import analyze_directory
from mcplain.capabilities import Capability, is_request, javascript_network_library, python_network_library
from mcplain.lamps import LampId, LampState
from mcplain.models import (
    AnalysisResult,
    AnalysisStatus,
    DeclarationKind,
    Finding,
    GrayCase,
    LocationKind,
    NetworkImport,
    ServerAnalysis,
    Tool,
    UrlKind,
    Verdict,
    VerdictColor,
)
from mcplain.verdict import apply_verdict, network_not_followed


def internet_lamp(result: AnalysisResult) -> tuple[LampState, str | None]:
    """Return the state and the note of the Internet lamp of the first server"""

    lamp = next(lamp for lamp in result.servers[0].lamps if lamp.id is LampId.INTERNET)
    return lamp.state, lamp.note


def python_imports(tmp_path: Path, source: str) -> list[str]:
    """Analyze one Python file and return the network libraries it imports and uses"""

    (tmp_path / "server.py").write_text(source, encoding="utf-8")
    return [item.library for item in PythonAdapter().analyze(tmp_path).network_imports]


def javascript_imports(tmp_path: Path, source: str, name: str = "index.ts") -> list[str]:
    """Analyze one JavaScript or TypeScript file and return the network libraries it imports and uses"""

    (tmp_path / name).write_text(source, encoding="utf-8")
    return [item.library for item in JavaScriptAdapter().analyze(tmp_path).network_imports]


@pytest.mark.parametrize("fixture", ["python_network_elsewhere", "js_network_elsewhere"])
def test_a_client_built_in_another_module_then_used_is_gray(fixtures: Path, fixture: str) -> None:
    """The client comes from a factory in another file, so its request is not recognized: gray, never green"""

    result = analyze_directory(fixtures / fixture)
    assert result.verdict.color is VerdictColor.GRAY
    assert result.verdict.gray_case is GrayCase.NETWORK_UNRESOLVED
    assert "caveat.network_unresolved" in result.verdict.reasons
    assert result.verdict.title is not None
    assert result.verdict.title.code == "gray.network_unresolved.reason"
    library = result.servers[0].network_not_followed[0]
    assert result.verdict.title.params == {"library": library}
    assert internet_lamp(result) == (LampState.ON, "lamp.internet.note_not_followed")
    assert result.servers[0].internet_domains is None


@pytest.mark.parametrize("fixture", ["python_network_types", "ts_network_types"])
def test_imports_used_only_as_types_keep_the_green(fixtures: Path, fixture: str) -> None:
    """Exceptions, annotations, TYPE_CHECKING, isinstance, import type and instanceof do not count"""

    result = analyze_directory(fixtures / fixture)
    assert result.servers[0].network_imports == []
    assert result.verdict.color is VerdictColor.GREEN
    assert internet_lamp(result) == (LampState.OFF, None)


@pytest.mark.parametrize("fixture", ["python_client_factory", "official_fetch_like"])
def test_a_client_followed_in_its_own_module_stays_orange(fixtures: Path, fixture: str) -> None:
    """The fetch case: the client is made by make_client() or in the tool, its request is recognized"""

    result = analyze_directory(fixtures / fixture)
    assert result.verdict.color is VerdictColor.ORANGE
    assert [item.library for item in result.servers[0].network_imports] == ["httpx"]
    assert result.servers[0].network_not_followed == []
    assert internet_lamp(result)[1] is None


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import httpx\n\ndef f():\n    return httpx.AsyncClient()\n", ["httpx"]),
        ("import httpx\n\ndef f(c: httpx.Client) -> httpx.Response:\n    return c\n", []),
        ("import httpx\n\ndef f():\n    try:\n        return 1\n    except (httpx.TimeoutException, ValueError):\n        return 0\n", []),
        ("import httpx\n\ndef f():\n    try:\n        return 1\n    except ValueError:\n        return httpx\n", ["httpx"]),
        ("import httpx\n\ndef f(x):\n    return isinstance(x, httpx.Response)\n", []),
        ("import httpx\n\ndef f(x):\n    return isinstance(httpx, object)\n", ["httpx"]),
        ("from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    import requests\n\ndef f(s: 'requests.Session'):\n    return s\n", []),
        ("from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    pass\nelse:\n    import requests\n\ndef f():\n    return requests.get\n", ["requests"]),
        ("import requests\n", []),
        ("from urllib.parse import quote\nimport urllib.parse\n\ndef f(x):\n    return quote(x) + urllib.parse.quote(x)\n", []),
        ("from urllib.request import urlopen\n\ndef f(url):\n    return urlopen\n", ["urllib.request"]),
        ("from http import HTTPStatus\n\ndef f():\n    return HTTPStatus.OK\n", []),
        ("import socket\n\ndef f():\n    return socket.gethostname()\n", ["socket"]),
        ("import asyncio\n\ndef f():\n    return asyncio.sleep(1)\n", []),
        ("import httpx as h\n\ndef f(url):\n    raise h.HTTPError(url)\n", ["httpx"]),
        ("from aiohttp import ClientSession\n\ndef f():\n    return ClientSession\n", ["aiohttp"]),
    ],
    ids=[
        "call",
        "annotations",
        "except",
        "except_body",
        "isinstance",
        "isinstance_first",
        "type_checking",
        "type_checking_else",
        "unused",
        "urllib_parse",
        "urllib_request",
        "http_status",
        "socket",
        "asyncio",
        "alias_raise",
        "from_import",
    ],
)
def test_python_network_imports(tmp_path: Path, source: str, expected: list[str]) -> None:
    """Only a use beyond types, exceptions and isinstance makes an import count"""

    assert python_imports(tmp_path, source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('import axios from "axios";\nexport const get = (u: string) => axios.get(u);\n', ["axios"]),
        ('import type { AxiosInstance } from "axios";\nexport function f(c: AxiosInstance) { return c; }\n', []),
        ('import { type AxiosInstance } from "axios";\nexport function f(c: AxiosInstance) { return c; }\n', []),
        ('import { AxiosError } from "axios";\nexport function f(e: unknown) { return e instanceof AxiosError; }\n', []),
        ('import * as ax from "axios";\nexport function f(e: unknown) { return e instanceof ax.AxiosError; }\n', []),
        ('import { AxiosError } from "axios";\nexport function f() { return new AxiosError("x"); }\n', ["axios"]),
        ('import https from "node:https";\nexport function f() { return https.globalAgent; }\n', ["https"]),
        ('const http = require("http");\nfunction f() { return http.createServer(); }\nmodule.exports = { f };\n', ["http"]),
        ('const { request } = require("https");\nfunction f() { return request; }\nmodule.exports = { f };\n', ["https"]),
        ('import axios from "axios";\nexport const tools = { axios };\n', ["axios"]),
        ('import axios from "axios";\nexport type C = typeof axios;\n', []),
        ('import path from "node:path";\nexport const f = () => path.join("a", "b");\n', []),
    ],
    ids=[
        "call",
        "import_type",
        "inline_type",
        "instanceof",
        "instanceof_namespace",
        "new_error",
        "node_prefix",
        "require",
        "require_pattern",
        "shorthand",
        "typeof_type",
        "not_network",
    ],
)
def test_javascript_network_imports(tmp_path: Path, source: str, expected: list[str]) -> None:
    """Only a value use beyond types and instanceof makes an import count"""

    assert javascript_imports(tmp_path, source) == expected


def test_library_names() -> None:
    """Network libraries come from the network tables of the engine, plus the standard modules"""

    assert python_network_library("httpx.AsyncClient") == "httpx"
    assert python_network_library("urllib.request.urlopen") == "urllib.request"
    assert python_network_library("http.client.HTTPSConnection") == "http.client"
    assert python_network_library("asyncio.open_connection") == "asyncio.open_connection"
    assert python_network_library("urllib.parse") is None
    assert python_network_library("asyncio") is None
    assert python_network_library("httpxx") is None
    assert javascript_network_library("node:https") == "https"
    assert javascript_network_library("net") == "net"
    assert javascript_network_library("@sendgrid/mail") == "@sendgrid/mail"
    assert javascript_network_library("path") is None


@pytest.mark.parametrize(
    ("detail", "address", "expected"),
    [
        ("httpx.get", False, True),
        ("httpx.AsyncClient.get", True, True),
        ("httpx.AsyncClient", True, False),
        ("httpx.Timeout", False, False),
        ("ws.WebSocket", True, True),
        ("undici.Agent", False, False),
        ("axios", True, True),
        ("axios.create", True, False),
        ("axios.isAxiosError", False, False),
        ("socket.socket", False, False),
        ("smtplib.SMTP", False, False),
        ("https.request", False, True),
        (None, True, False),
    ],
)
def test_is_request(detail: str | None, address: bool, expected: bool) -> None:
    """Building a client or a settings object is not a request; a call that talks is"""

    assert is_request(detail, address) is expected


def built(findings: list[Finding], imports: list[NetworkImport]) -> AnalysisResult:
    """Build a result with one server holding one tool, its findings and its network imports"""

    tool = Tool(
        name="t",
        description="d",
        description_is_dynamic=False,
        file="server.py",
        line=1,
        declaration=DeclarationKind.DECORATOR,
        location_kind=LocationKind.SERVER_CODE,
        findings=findings,
    )
    server = ServerAnalysis(path=".", language="python", files_analyzed=1, tools=[tool], network_imports=imports)
    return AnalysisResult(status=AnalysisStatus.OK, servers=[server], verdict=Verdict(color=VerdictColor.GRAY))


def network_import(library: str = "httpx", location: LocationKind = LocationKind.SERVER_CODE) -> NetworkImport:
    """Build a network import"""

    return NetworkImport(library=library, file="server.py", line=1, location_kind=location)


def network_finding(detail: str, kind: UrlKind = UrlKind.LITERAL) -> Finding:
    """Build a network finding"""

    return Finding(
        capability=Capability.NETWORK,
        file="server.py",
        line=2,
        column=1,
        snippet="x",
        location_kind=LocationKind.SERVER_CODE,
        detail=detail,
        url_kind=kind,
        url_host="api.example.com",
    )


def test_the_lock_never_changes_an_orange_or_a_red() -> None:
    """An orange or red verdict keeps its color; the lamp still says the network was not followed"""

    write = Finding(
        capability=Capability.FS_WRITE,
        file="server.py",
        line=3,
        column=1,
        snippet="x",
        location_kind=LocationKind.SERVER_CODE,
    )
    result = apply_verdict(built([write], [network_import()]))
    assert result.verdict.color is VerdictColor.ORANGE
    assert result.verdict.gray_case is None
    assert internet_lamp(result) == (LampState.ON, "lamp.internet.note_not_followed")


def test_a_recognized_request_of_the_same_library_unlocks_the_green() -> None:
    """A request of the imported library is recognized: the code was followed"""

    result = apply_verdict(built([network_finding("httpx.get")], [network_import()]))
    assert result.verdict.color is VerdictColor.GREEN
    assert internet_lamp(result) == (LampState.ON, None)


def test_a_request_of_another_library_does_not_unlock_the_green() -> None:
    """Each imported library needs its own recognized request"""

    result = apply_verdict(built([network_finding("requests.get")], [network_import("httpx")]))
    assert result.verdict.color is VerdictColor.GRAY
    assert result.servers[0].network_not_followed == ["httpx"]


def test_a_client_construction_alone_does_not_unlock_the_green() -> None:
    """Building a client says nothing about where it sends data"""

    result = apply_verdict(built([network_finding("httpx.AsyncClient", UrlKind.UNKNOWN)], [network_import()]))
    assert result.verdict.gray_case is GrayCase.NETWORK_UNRESOLVED


def test_imports_in_tests_or_examples_do_not_count() -> None:
    """Only server code counts, as for every rule"""

    result = apply_verdict(built([], [network_import(location=LocationKind.TEST_OR_EXAMPLE)]))
    assert result.verdict.color is VerdictColor.GREEN
    assert network_not_followed(result.servers[0]) == []
