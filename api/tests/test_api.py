"""Tests of the HTTP API with a TestClient and an in-memory SQLite database"""

import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from helpers import ENGINE_FIXTURES, make_settings
from mcplain.analyze import analyze_directory
from mcplain.i18n import load_catalog
from mcplain.models import AnalysisResult, VerdictColor
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from mcplain_api.app import create_app
from mcplain_api.db import Analysis, AnalysisState, Base, make_engine, make_sessions
from mcplain_api.outcomes import failure_result

SOURCE = Path(__file__).resolve().parents[1] / "src" / "mcplain_api"
CODE_PATTERN = re.compile(r"[\"']((?:api|job)\.[a-z_]+)[\"']")
VALID_INPUTS: list[tuple[str, str | None, str | None]] = [
    ("npx -y @modelcontextprotocol/server-filesystem", None, None),
    ("uvx mcp-server-fetch", None, None),
    ("https://github.com/modelcontextprotocol/servers", "src/fetch/", "src/fetch"),
]
INVALID_INPUTS: list[tuple[str, str | None, str]] = [
    ("pip install requests", None, "input.unexpected_arguments"),
    ("ssh://github.com/demo/servers", None, "input.unsupported_scheme"),
    ("", None, "input.empty"),
    ("https://gitlab.com/demo/servers", None, "input.unsupported_host"),
    ("npx -y left-pad@^1.0.0", None, "input.version_range_unsupported"),
    ("https://github.com/" + "a" * 500, None, "input.too_long"),
    ("uvx mcp-server-fetch", "../etc", "input.invalid_selection"),
]
JSON_HEADERS = {"Content-Type": "application/json"}


@pytest.fixture
def sessions() -> sessionmaker:
    """Return sessions on a fresh in-memory database"""

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_sessions(engine)


@pytest.fixture
def client(sessions: sessionmaker) -> Iterator[TestClient]:
    """Return a test client of the API on the in-memory database, with a queue of 3"""

    app = create_app(make_settings(max_queued=3), sessions.kw["bind"])
    with TestClient(app) as test_client:
        yield test_client


def add_row(sessions: sessionmaker, **values: object) -> uuid.UUID:
    """Insert an analysis directly in the database"""

    with sessions.begin() as session:
        row = Analysis(input_raw="uvx mcp-server-fetch", **values)
        session.add(row)
        session.flush()
        return row.id


@pytest.mark.parametrize(("text", "selection", "stored"), VALID_INPUTS)
def test_valid_input_is_queued(client: TestClient, sessions: sessionmaker, text: str, selection: str | None, stored: str | None) -> None:
    """A valid input gives 202 with an id and the queued state, and is stored as given"""

    response = client.post("/api/analyses", json={"input": text, "select": selection})
    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "queued"
    with sessions() as session:
        row = session.get(Analysis, uuid.UUID(body["id"]))
    assert row is not None
    assert (row.input_raw, row.select, row.state) == (text, stored, "queued")


@pytest.mark.parametrize(("text", "selection", "code"), INVALID_INPUTS)
def test_invalid_input_is_refused_with_a_code(client: TestClient, sessions: sessionmaker, text: str, selection: str | None, code: str) -> None:
    """An invalid input gives 400 with the engine code and its parameters, and nothing is queued"""

    response = client.post("/api/analyses", json={"input": text, "select": selection})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == code
    assert isinstance(error["params"], dict)
    with sessions() as session:
        assert session.scalars(select(Analysis)).all() == []


def test_too_long_input_says_the_limit(client: TestClient) -> None:
    """The limit of 500 characters is given as a parameter"""

    response = client.post("/api/analyses", json={"input": "x" * 501})
    assert response.json() == {"error": {"code": "input.too_long", "params": {"limit": "500"}}}


@pytest.mark.parametrize(
    "body",
    ['{"select": "src"}', '{"input": 3}', '{"input": "uvx a", "extra": 1}', "not json", "[]"],
    ids=["missing", "not_text", "extra_field", "not_json", "list"],
)
def test_malformed_body_is_refused(client: TestClient, body: str) -> None:
    """A body that is not the expected object gives 400 api.invalid_request"""

    response = client.post("/api/analyses", content=body, headers=JSON_HEADERS)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "api.invalid_request"


def test_body_over_two_kilobytes_is_refused(client: TestClient) -> None:
    """A body over 2 KB gives 413, before it is parsed"""

    response = client.post("/api/analyses", content='{"input": "' + "x" * 3000 + '"}', headers=JSON_HEADERS)
    assert response.status_code == 413
    assert response.json() == {"error": {"code": "api.body_too_large", "params": {"limit": "2048"}}}


def test_streamed_body_over_two_kilobytes_is_refused(client: TestClient) -> None:
    """A body sent in chunks without a length is cut as soon as it passes 2 KB"""

    def chunks() -> Iterator[bytes]:
        """Yield a body of 4 KB in small chunks"""

        for _ in range(64):
            yield b"x" * 64

    response = client.post("/api/analyses", content=chunks(), headers=JSON_HEADERS)
    assert response.status_code == 413


def test_other_content_type_is_refused(client: TestClient) -> None:
    """Only JSON bodies are accepted, so that another web site cannot post a simple form"""

    response = client.post("/api/analyses", content='{"input": "uvx a"}', headers={"Content-Type": "text/plain"})
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "api.unsupported_media_type"


def test_full_queue_gives_503(client: TestClient, sessions: sessionmaker) -> None:
    """With MCPLAIN_MAX_QUEUED analyses waiting, a new request gives 503; finished ones do not count"""

    add_row(sessions, state=AnalysisState.DONE.value)
    add_row(sessions, state=AnalysisState.FAILED.value)
    for _ in range(3):
        assert client.post("/api/analyses", json={"input": "uvx mcp-server-fetch"}).status_code == 202
    response = client.post("/api/analyses", json={"input": "uvx mcp-server-fetch"})
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "api.queue_full", "params": {}}}


@pytest.mark.parametrize("identifier", [str(uuid.uuid4()), "not-a-uuid", "1"])
def test_unknown_analysis_gives_404(client: TestClient, identifier: str) -> None:
    """An unknown or malformed id gives 404 api.analysis_not_found"""

    response = client.get(f"/api/analyses/{identifier}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "api.analysis_not_found"


def test_queued_analysis_has_no_result_yet(client: TestClient) -> None:
    """A queued analysis has its creation time and no result"""

    identifier = client.post("/api/analyses", json={"input": "uvx mcp-server-fetch"}).json()["id"]
    body = client.get(f"/api/analyses/{identifier}").json()
    assert body["id"] == identifier
    assert (body["state"], body["result"], body["finished_at"], body["error_code"]) == ("queued", None, None, None)
    assert body["created_at"].endswith("+00:00")


def test_analysis_gives_back_what_was_asked(client: TestClient) -> None:
    """The view repeats the input and the selection, so the site can ask again with another selection"""

    sent = {"input": "npx -y @modelcontextprotocol/server-filesystem", "select": "src/a"}
    identifier = client.post("/api/analyses", json=sent).json()["id"]
    body = client.get(f"/api/analyses/{identifier}").json()
    assert (body["input"], body["select"]) == (sent["input"], sent["select"])


def test_failed_analysis_always_has_a_gray_result(client: TestClient, sessions: sessionmaker) -> None:
    """A failed analysis gives a gray verdict and the code of its reason"""

    stored = failure_result("atelier_timeout").model_dump(mode="json")
    identifier = add_row(sessions, state=AnalysisState.FAILED.value, error_code="atelier_timeout", result=stored)
    body = client.get(f"/api/analyses/{identifier}").json()
    assert body["error_code"] == "atelier_timeout"
    result = AnalysisResult.model_validate(body["result"])
    assert result.verdict.color is VerdictColor.GRAY
    assert result.error is not None and result.error.code == "job.atelier_timeout"


@pytest.mark.parametrize("stored", [None, {"broken": True}], ids=["missing", "unreadable"])
def test_failed_analysis_without_a_usable_result_still_is_gray(client: TestClient, sessions: sessionmaker, stored: object) -> None:
    """Even a failed row without a usable result is shown with a gray verdict"""

    identifier = add_row(sessions, state=AnalysisState.FAILED.value, error_code="interrupted", result=stored)
    result = AnalysisResult.model_validate(client.get(f"/api/analyses/{identifier}").json()["result"])
    assert result.verdict.color is VerdictColor.GRAY
    assert result.error is not None and result.error.code == "job.interrupted"


def test_failed_analysis_cannot_show_another_color(client: TestClient, sessions: sessionmaker) -> None:
    """A failed row that holds a green result is shown gray"""

    green = analyze_directory(ENGINE_FIXTURES / "python_fastmcp_clean").model_dump(mode="json")
    assert green["verdict"]["color"] == "green"
    identifier = add_row(sessions, state=AnalysisState.FAILED.value, error_code="internal_error", result=green)
    result = client.get(f"/api/analyses/{identifier}").json()["result"]
    assert result["verdict"]["color"] == "gray"


def test_texts_from_analyzed_code_are_returned_as_they_are(client: TestClient, sessions: sessionmaker) -> None:
    """A description with markup and invisible characters comes back unchanged, as JSON text, never as HTML"""

    result = analyze_directory(ENGINE_FIXTURES / "python_fastmcp_poisoned").model_dump(mode="json")
    description = '<img src=x onerror="alert(1)">\u200b'
    result["servers"][0]["tools"][0]["description"] = description
    identifier = add_row(sessions, state=AnalysisState.DONE.value, result=result)
    response = client.get(f"/api/analyses/{identifier}")
    assert response.headers["content-type"] == "application/json"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.json()["result"]["servers"][0]["tools"][0]["description"] == description


@pytest.mark.parametrize("language", ["en", "fr"])
def test_messages_are_the_engine_texts(client: TestClient, language: str) -> None:
    """The site gets exactly the texts of the command line"""

    response = client.get(f"/api/messages/{language}")
    assert response.status_code == 200
    assert response.json() == load_catalog(language)


def test_unknown_language_gives_404(client: TestClient) -> None:
    """Only en and fr exist"""

    response = client.get("/api/messages/de")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "api.unknown_language"


def test_every_api_code_has_texts() -> None:
    """Each api. and job. code written in the API code has a message in English and French"""

    english = load_catalog("en")
    french = load_catalog("fr")
    codes = {code for path in SOURCE.rglob("*.py") for code in CODE_PATTERN.findall(path.read_text(encoding="utf-8"))}
    codes |= {f"job.{code}" for code in ("fetch_error", "internal_error", "interrupted", "atelier_timeout", "atelier_invalid_result", "atelier_error")}
    assert codes
    assert sorted(code for code in codes if code not in english or code not in french) == []


def test_health_says_the_database_answers(client: TestClient) -> None:
    """The health check runs a query"""

    assert client.get("/api/health").json() == {"status": "ok"}


def test_health_without_database_gives_503(tmp_path: Path) -> None:
    """A database that cannot be opened gives 503"""

    engine = make_engine(f"sqlite:///{tmp_path / 'missing' / 'db.sqlite'}")
    with TestClient(create_app(make_settings(), engine)) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "api.database_unavailable"


def test_cors_allows_only_the_configured_origin(client: TestClient) -> None:
    """The site origin gets CORS headers, another origin does not"""

    allowed = client.options(
        "/api/analyses",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    other = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_unknown_route_and_method_use_the_error_format(client: TestClient) -> None:
    """Unknown routes and methods answer with a code"""

    assert client.get("/api/nothing").json()["error"]["code"] == "api.not_found"
    assert client.delete("/api/health").json()["error"]["code"] == "api.method_not_allowed"
