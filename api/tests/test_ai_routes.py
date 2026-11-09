"""Tests of the notice and translation routes, of the cache and of what the public answer never holds"""

import json
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from helpers import lamps_of, make_settings, report, tool_report
from sqlalchemy.orm import sessionmaker

from mcplain_api.ai_client import API_URL, build_body, call_api
from mcplain_api.ai_prompts import NOTICE_SYSTEM
from mcplain_api.ai_view import _insert
from mcplain_api.app import create_app
from mcplain_api.db import AiState, AiText, Analysis, Base, make_engine, make_sessions, utc_now
from mcplain_api.outcomes import failure_result
from mcplain_api.redacteur import Redacteur

KEY = "sk-ant-test-CANARY"
GOOD_NOTICE = {
    "summary": "Ce serveur donne l'heure.",
    "use_cases": ["Demander l'heure."],
    "tool_titles": [{"name": "get_time", "title": "Donner l'heure", "sentence": "Il donne l'heure."}],
    "mismatch": True,
    "alert": "Donner l'heure avec tes secrets, c'est étonnant.",
}
PUBLIC_KEYS = {"id", "kind", "lang", "status", "source", "fallback", "content", "model", "date", "reject_reason", "resume"}


def answer(payload: Any) -> httpx.Response:
    """Return a good answer of the API"""

    return httpx.Response(
        200,
        headers={"request-id": "req_SECRET"},
        json={
            "content": [{"type": "text", "text": json.dumps(payload)}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    )


@pytest.fixture
def sessions() -> sessionmaker:
    """Return sessions on a fresh in-memory database"""

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_sessions(engine)


@pytest.fixture
def client(sessions: sessionmaker) -> Iterator[TestClient]:
    """Return a test client of the API on the same database"""

    with TestClient(create_app(make_settings(), sessions.kw["bind"])) as test_client:
        yield test_client


@pytest.fixture
def writer(sessions: sessionmaker) -> Redacteur:
    """Return a started writer with a key"""

    redacteur = Redacteur(make_settings(anthropic_api_key=KEY), sessions, sleep=lambda seconds: None)
    redacteur.start()
    return redacteur


def add_analysis(sessions: sessionmaker, tools: list[dict[str, Any]] | None = None, state: str = "done") -> str:
    """Insert an analysis and return its identifier"""

    result = None
    if state in ("done", "failed"):
        result = report(tools if tools is not None else [tool_report("get_time", "Gives the time.", lamps_of("internet"))])
    with sessions.begin() as session:
        row = Analysis(input_raw="uvx demo", state=state, result=result)
        session.add(row)
        session.flush()
        return str(row.id)


@pytest.mark.parametrize("route", ["notice", "translation"])
def test_unknown_or_malformed_analysis_gives_404(client: TestClient, route: str) -> None:
    """Both verbs, a valid identifier that does not exist and a text that is not one"""

    for identifier in (str(uuid.uuid4()), "abc"):
        assert client.post(f"/api/analyses/{identifier}/{route}", json={"lang": "fr"}).status_code == 404
        assert client.get(f"/api/analyses/{identifier}/{route}?lang=fr").status_code == 404


@pytest.mark.parametrize("route", ["notice", "translation"])
@pytest.mark.parametrize("state", ["queued", "fetching", "analyzing"])
def test_an_analysis_not_finished_gives_409(client: TestClient, sessions: sessionmaker, route: str, state: str) -> None:
    """Nothing is asked before the report is ready"""

    identifier = add_analysis(sessions, state=state)
    response = client.post(f"/api/analyses/{identifier}/{route}", json={"lang": "fr"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "api.analysis_not_finished"
    assert client.get(f"/api/analyses/{identifier}/{route}?lang=fr").status_code == 409
    with sessions() as session:
        assert session.query(AiText).count() == 0


def test_no_tool_gives_the_template_without_any_row(client: TestClient, sessions: sessionmaker) -> None:
    """Without a recognized tool: 200, source template, the no_tools variant, and no call possible"""

    identifier = add_analysis(sessions, tools=[])
    response = client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    assert response.status_code == 200
    body = response.json()
    assert (body["source"], body["status"], body["content"]) == ("template", "template", None)
    assert body["fallback"]["variant"] == "no_tools"
    assert client.post(f"/api/analyses/{identifier}/translation", json={"lang": "fr"}).json()["source"] == "template"
    with sessions() as session:
        assert session.query(AiText).count() == 0


def test_a_failed_analysis_never_asks_the_ai(client: TestClient, sessions: sessionmaker) -> None:
    """A failed analysis has a gray result and no call, whatever it holds"""

    with sessions.begin() as session:
        row = Analysis(input_raw="uvx demo", state="failed", result=failure_result("fetch_error").model_dump(mode="json"))
        session.add(row)
        session.flush()
        identifier = str(row.id)
    assert client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"}).json()["source"] == "template"
    with sessions() as session:
        assert session.query(AiText).count() == 0


def test_a_description_free_report_has_no_translation(client: TestClient, sessions: sessionmaker) -> None:
    """Nothing to translate means no call"""

    identifier = add_analysis(sessions, tools=[tool_report("get_time", "")])
    assert client.post(f"/api/analyses/{identifier}/translation", json={"lang": "fr"}).json()["status"] == "template"


@pytest.mark.parametrize(
    "body", [{"lang": "de"}, {"lang": 1}, {}, {"lang": "fr", "other": 1}, []],
)
def test_invalid_body_gives_400(client: TestClient, sessions: sessionmaker, body: Any) -> None:
    """An unknown language or a wrong shape is refused"""

    identifier = add_analysis(sessions)
    assert client.post(f"/api/analyses/{identifier}/notice", json=body).status_code == 400


def test_translation_only_to_french(client: TestClient, sessions: sessionmaker) -> None:
    """en gives 400 on both verbs"""

    identifier = add_analysis(sessions)
    assert client.post(f"/api/analyses/{identifier}/translation", json={"lang": "en"}).status_code == 400
    assert client.get(f"/api/analyses/{identifier}/translation?lang=en").status_code == 400
    assert client.post(f"/api/analyses/{identifier}/translation", json={"lang": "fr"}).status_code == 202


def test_get_needs_a_language_and_asks_for_nothing(client: TestClient, sessions: sessionmaker) -> None:
    """GET never queues"""

    identifier = add_analysis(sessions)
    assert client.get(f"/api/analyses/{identifier}/notice").status_code == 400
    assert client.get(f"/api/analyses/{identifier}/notice?lang=de").status_code == 400
    answer_body = client.get(f"/api/analyses/{identifier}/notice?lang=fr").json()
    assert answer_body["status"] == "none"
    assert answer_body["fallback"]["variant"] == "tools"
    with sessions() as session:
        assert session.query(AiText).count() == 0


def test_a_body_that_is_not_json_gives_415_or_400(client: TestClient, sessions: sessionmaker) -> None:
    """The same rules as the analyses route"""

    identifier = add_analysis(sessions)
    assert client.post(f"/api/analyses/{identifier}/notice", content="x", headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.post(f"/api/analyses/{identifier}/notice", content="x", headers={"Content-Type": "application/json"}).status_code == 400


def test_fallback_is_built_from_the_lamps_as_codes_and_parameters(client: TestClient, sessions: sessionmaker) -> None:
    """Text codes only, the same in every language, and the server lamps give what it can do"""

    data = report([tool_report("a"), tool_report("b")])
    data["servers"][0]["lamps"] = lamps_of("files_read", danger=("internet",))
    with sessions.begin() as session:
        row = Analysis(input_raw="uvx demo", state="done", result=data)
        session.add(row)
        session.flush()
        identifier = str(row.id)
    fallback = client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"}).json()["fallback"]
    assert fallback == {
        "variant": "tools",
        "messages": [
            {"code": "ai.notice.fallback.count", "params": {"count": "2"}},
            {"code": "ai.notice.fallback.can", "params": {}},
            {"code": "ai.notice.fallback.unavailable", "params": {}},
        ],
        "actions": ["lamp.files_read.phrase", "lamp.internet.phrase"],
    }
    texts = client.get("/api/messages/fr").json()
    for message in fallback["messages"]:
        assert message["code"] in texts
    for code in fallback["actions"]:
        assert code in texts
    assert "MCPlain n'a pas pu écrire de résumé automatique pour ce serveur." in texts.values()


@pytest.mark.parametrize("language", ["en", "fr"])
def test_every_fallback_text_exists_in_both_languages(client: TestClient, language: str) -> None:
    """The variant without a tool and the one without a lamp too"""

    texts = client.get(f"/api/messages/{language}").json()
    for code in ("count", "can", "nothing", "unavailable", "no_tools"):
        assert f"ai.notice.fallback.{code}" in texts


@respx.mock
def test_the_full_path_from_request_to_ready(client: TestClient, sessions: sessionmaker, writer: Redacteur) -> None:
    """Queued with 202, written once, then served with its source, model and date, and never its cost"""

    route = respx.post(API_URL).mock(return_value=answer(GOOD_NOTICE))
    identifier = add_analysis(sessions)
    first = client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    assert first.status_code == 202
    assert first.json()["status"] == "pending"
    assert first.json()["fallback"]["variant"] == "tools"
    writer.run_once()
    second = client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    assert second.status_code == 200
    body = second.json()
    assert set(body) == PUBLIC_KEYS
    assert (body["status"], body["source"], body["model"]) == ("ready", "ai", "claude-sonnet-5-5")
    assert body["date"].endswith("+00:00")
    assert body["content"]["tool_titles"] == [{"tool_index": 0, "title": "Donner l'heure", "sentence": "Il donne l'heure."}]
    assert body["content"]["alert"] == GOOD_NOTICE["alert"]
    assert body["fallback"]["variant"] == "tools"
    assert client.get(f"/api/analyses/{identifier}/notice?lang=fr").json() == body
    text = second.text
    assert "req_SECRET" not in text
    assert "cost" not in text
    assert "token" not in text
    assert route.call_count == 1


@respx.mock
def test_two_analyses_of_the_same_version_share_the_notice(client: TestClient, sessions: sessionmaker, writer: Redacteur) -> None:
    """Same form, language, prompt and model: 0 token the second time"""

    route = respx.post(API_URL).mock(return_value=answer(GOOD_NOTICE))
    first = add_analysis(sessions)
    second = add_analysis(sessions)
    client.post(f"/api/analyses/{first}/notice", json={"lang": "fr"})
    writer.run_once()
    response = client.post(f"/api/analyses/{second}/notice", json={"lang": "fr"})
    assert response.status_code == 200
    assert response.json()["source"] == "ai"
    assert response.json()["id"] == second
    assert route.call_count == 1


def test_each_language_prompt_and_model_has_its_own_row(client: TestClient, sessions: sessionmaker) -> None:
    """The language and the model are parts of the key"""

    identifier = add_analysis(sessions)
    client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    client.post(f"/api/analyses/{identifier}/notice", json={"lang": "en"})
    other = TestClient(create_app(make_settings(ai_model="another-model"), sessions.kw["bind"]))
    other.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    with sessions() as session:
        keys = {(row.lang, row.model) for row in session.query(AiText).all()}
    assert keys == {("fr", "claude-sonnet-5-5"), ("en", "claude-sonnet-5-5"), ("fr", "another-model")}


@respx.mock
def test_ten_visitors_make_one_row_and_one_call(client: TestClient, sessions: sessionmaker, writer: Redacteur) -> None:
    """Ten requests give one waiting row and one call; the two writers on PostgreSQL are in test_compose.py"""

    route = respx.post(API_URL).mock(return_value=answer(GOOD_NOTICE))
    identifier = add_analysis(sessions)
    codes = [client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"}).status_code for _ in range(10)]
    assert codes == [202] * 10
    with sessions() as session:
        assert session.query(AiText).count() == 1
    assert writer.run_once() is True
    assert writer.run_once() is False
    assert route.call_count == 1


def test_two_visitors_at_the_same_moment_share_one_row(sessions: sessionmaker) -> None:
    """When the row appears between the look-up and the insert, the unique key decides and both get the same row"""

    identifier = uuid.UUID(add_analysis(sessions))
    first = _insert(sessions, identifier, "notice", "fr", "claude-sonnet-5-5")
    second = _insert(sessions, identifier, "notice", "fr", "claude-sonnet-5-5")
    assert (first[0], second[0]) == (202, 202)
    with sessions() as session:
        assert session.query(AiText).count() == 1


@respx.mock
def test_failure_is_never_ready_and_comes_back_after_ten_minutes(client: TestClient, sessions: sessionmaker, writer: Redacteur) -> None:
    """A failed text answers 200 with the fallback, then can be asked again once its wait is over"""

    respx.post(API_URL).mock(return_value=httpx.Response(500))
    identifier = add_analysis(sessions)
    client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    writer.run_once()
    body = client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    assert body.status_code == 200
    assert (body.json()["status"], body.json()["source"], body.json()["content"]) == ("failed", "template", None)
    assert body.json()["fallback"]["variant"] == "tools"
    with sessions.begin() as session:
        session.query(AiText).update({"retry_at": utc_now() - timedelta(seconds=1)})
    assert client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"}).status_code == 202


@respx.mock
def test_a_rejected_text_stays_rejected_without_a_new_call(client: TestClient, sessions: sessionmaker, writer: Redacteur) -> None:
    """A rejection is final for this form and prompt: no second bill, the reason code only"""

    route = respx.post(API_URL).mock(return_value=answer({**GOOD_NOTICE, "summary": "Ce serveur est fiable."}))
    identifier = add_analysis(sessions)
    client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    writer.run_once()
    response = client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    body = response.json()
    assert response.status_code == 200
    assert (body["status"], body["reject_reason"], body["content"]) == ("rejected", "forbidden_word", None)
    assert "fiable" not in response.text
    assert writer.run_once() is False
    assert route.call_count == 1
    with sessions() as session:
        assert session.query(AiText).one().content is None


@pytest.mark.parametrize(
    ("reason", "resume"), [("daily_fuse", "tomorrow"), ("monthly_budget", "next_month"), ("usage_limit", "later")]
)
def test_a_paused_text_says_when_it_comes_back(client: TestClient, sessions: sessionmaker, reason: str, resume: str) -> None:
    """The site says tomorrow or next month, and the text is asked again once that moment has passed"""

    identifier = add_analysis(sessions)
    client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    with sessions.begin() as session:
        session.query(AiText).update(
            {"status": "paused", "reject_reason": reason, "retry_at": utc_now() + timedelta(hours=1)}
        )
    body = client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"}).json()
    assert (body["status"], body["resume"], body["source"]) == ("paused", resume, "template")
    assert client.get(f"/api/analyses/{identifier}/notice?lang=fr").json()["resume"] == resume
    with sessions.begin() as session:
        session.query(AiText).update({"retry_at": utc_now() - timedelta(seconds=1)})
    assert client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"}).status_code == 202


def test_disabled_function_queues_nothing(client: TestClient, sessions: sessionmaker) -> None:
    """Cut off: the fallback at once, and no row"""

    with sessions.begin() as session:
        session.add(AiState(id=1, disabled_reason="no_key"))
    identifier = add_analysis(sessions)
    response = client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    assert response.status_code == 200
    assert (response.json()["status"], response.json()["source"]) == ("disabled", "template")
    with sessions() as session:
        assert session.query(AiText).count() == 0


def test_global_pause_queues_nothing(client: TestClient, sessions: sessionmaker) -> None:
    """Paused for everyone: the fallback at once, and no row"""

    with sessions.begin() as session:
        session.add(AiState(id=1, paused_until=utc_now() + timedelta(minutes=5)))
    identifier = add_analysis(sessions)
    body = client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"}).json()
    assert (body["status"], body["resume"]) == ("paused", "later")
    with sessions() as session:
        assert session.query(AiText).count() == 0


@respx.mock
def test_a_ready_text_stays_served_when_the_function_is_cut(client: TestClient, sessions: sessionmaker, writer: Redacteur) -> None:
    """Texts in the cache remain shown, whatever happens to the key"""

    respx.post(API_URL).mock(return_value=answer(GOOD_NOTICE))
    identifier = add_analysis(sessions)
    client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    writer.run_once()
    with sessions.begin() as session:
        session.get(AiState, 1).disabled_reason = "auth"
    assert client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"}).json()["source"] == "ai"


@respx.mock
def test_a_verdict_never_changes_with_the_ai(client: TestClient, sessions: sessionmaker, writer: Redacteur) -> None:
    """The stored report and the public view of the analysis are the same before and after a notice"""

    respx.post(API_URL).mock(return_value=answer(GOOD_NOTICE))
    identifier = add_analysis(sessions)
    before = client.get(f"/api/analyses/{identifier}").json()
    client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
    writer.run_once()
    assert client.get(f"/api/analyses/{identifier}").json() == before


@respx.mock
def test_titles_map_to_the_position_of_each_tool(client: TestClient, sessions: sessionmaker, writer: Redacteur) -> None:
    """Filtered names lead back to the right tool of this report"""

    notice = {
        **GOOD_NOTICE,
        "tool_titles": [{"name": "get_time_2", "title": "Second", "sentence": "B."}, {"name": "get_time", "title": "First", "sentence": "A."}],
    }
    respx.post(API_URL).mock(return_value=answer(notice))
    identifier = add_analysis(sessions, tools=[tool_report("get-time"), tool_report("get.time")])
    client.post(f"/api/analyses/{identifier}/notice", json={"lang": "en"})
    writer.run_once()
    titles = client.get(f"/api/analyses/{identifier}/notice?lang=en").json()["content"]["tool_titles"]
    assert sorted((item["tool_index"], item["title"]) for item in titles) == [(0, "First"), (1, "Second")]


@respx.mock
def test_translation_route_full_path(client: TestClient, sessions: sessionmaker, writer: Redacteur) -> None:
    """Ids come back as they are; the notice fallback is not part of this answer"""

    respx.post(API_URL).mock(return_value=answer({"items": [{"id": "tool_0", "text": "Donne l'heure."}]}))
    identifier = add_analysis(sessions)
    assert client.post(f"/api/analyses/{identifier}/translation", json={"lang": "fr"}).status_code == 202
    writer.run_once()
    body = client.get(f"/api/analyses/{identifier}/translation?lang=fr").json()
    assert body["content"] == {"items": [{"id": "tool_0", "text": "Donne l'heure."}]}
    assert (body["source"], body["kind"], body["fallback"]) == ("ai", "translation", None)


FRENCH = "À l'été, ça coûte : « œuvre », hôtel, fenêtre."


@pytest.mark.parametrize("content_type", ["application/json", "application/json; charset=iso-8859-1", "text/plain"])
def test_french_text_crosses_the_chain_unchanged(
    client: TestClient, sessions: sessionmaker, writer: Redacteur, content_type: str
) -> None:
    """UTF-8 bytes of the API reach the database and the public answer unchanged, whatever charset the header claims"""

    payload = {**GOOD_NOTICE, "summary": FRENCH, "use_cases": [FRENCH], "mismatch": False, "alert": ""}
    payload["tool_titles"] = [{"name": "get_time", "title": "Donner l'heure à Paris", "sentence": FRENCH}]
    raw = json.dumps(
        {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "stop_reason": "end_turn", "usage": {}},
        ensure_ascii=False,
    ).encode("utf-8")
    with respx.mock() as router:
        router.post(API_URL).mock(return_value=httpx.Response(200, content=raw, headers={"content-type": content_type}))
        identifier = add_analysis(sessions)
        client.post(f"/api/analyses/{identifier}/notice", json={"lang": "fr"})
        writer.run_once()
    body = client.get(f"/api/analyses/{identifier}/notice?lang=fr").json()
    assert body["status"] == "ready"
    assert body["content"]["summary"] == FRENCH
    assert body["content"]["tool_titles"][0]["title"] == "Donner l'heure à Paris"
    with sessions() as session:
        assert session.query(AiText).one().content["summary"] == FRENCH


def test_the_request_carries_french_as_utf8(sessions: sessionmaker) -> None:
    """The system prompt and the body leave as UTF-8 bytes, never in another encoding"""

    with respx.mock() as router:
        route = router.post(API_URL).mock(return_value=answer(GOOD_NOTICE))
        call_api(make_settings(anthropic_api_key=KEY), build_body(make_settings(), NOTICE_SYSTEM, FRENCH, 10))
    raw = route.calls.last.request.content
    assert "sécurisé".encode("utf-8") in raw
    assert FRENCH.encode("utf-8") in raw
    assert json.loads(raw.decode("utf-8"))["messages"][0]["content"] == FRENCH
