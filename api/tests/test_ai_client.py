"""Tests of the Anthropic client with respx: the exact request, every error, and how the writer reacts to each"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx
from helpers import lamps_of, make_settings, report, tool_report
from mcplain.models import AnalysisResult
from sqlalchemy.orm import sessionmaker

from mcplain_api.ai_client import API_URL, CallKind, call_api, call_cost, notice_body, translation_body
from mcplain_api.ai_form import build_form, content_hash, translation_items
from mcplain_api.ai_logging import SecretFilter
from mcplain_api.ai_prompts import (
    NOTICE_PROMPT_VERSION,
    NOTICE_SCHEMA,
    NOTICE_SYSTEM,
    TRANSLATION_PROMPT_VERSION,
    TRANSLATION_SCHEMA,
    notice_message,
)
from mcplain_api.db import AiAdminAlert, AiCall, AiState, AiText, Analysis, Base, make_engine, make_sessions
from mcplain_api.redacteur import Redacteur, next_day, next_month

KEY = "sk-ant-test-CANARY"
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
USAGE_LIMIT_BODY = {
    "type": "error",
    "error": {"type": "invalid_request_error", "message": "You have reached your specified workspace API USAGE LIMITS."},
}
GOOD_NOTICE = {
    "summary": "Ce serveur donne l'heure.",
    "use_cases": ["Demander l'heure."],
    "tool_titles": [{"name": "get_time", "title": "Donner l'heure", "sentence": "Il donne l'heure."}],
    "mismatch": False,
    "alert": "",
}


def answer(payload: Any, stop_reason: str = "end_turn", request_id: str = "req_1") -> httpx.Response:
    """Return an answer of the API holding a JSON text"""

    return httpx.Response(
        200,
        headers={"request-id": request_id},
        json={
            "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": json.dumps(payload)}],
            "stop_reason": stop_reason,
            "usage": {"input_tokens": 1000, "output_tokens": 500},
        },
    )


class Clock:
    """Class that gives a time the tests can move"""

    def __init__(self) -> None:
        """Start at the fixed moment of the tests"""

        self.now = NOW

    def __call__(self) -> datetime:
        """Return the current time of the test"""

        return self.now


class Bench:
    """Class that holds a writer on an in-memory database, with what it slept and its fixed clock"""

    def __init__(self, **settings: Any) -> None:
        """Build the database, the settings and the writer"""

        engine = make_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.sessions: sessionmaker = make_sessions(engine)
        self.slept: list[float] = []
        self.clock = Clock()
        self.settings = make_settings(anthropic_api_key=KEY, **settings)
        self.redacteur = Redacteur(self.settings, self.sessions, sleep=self.slept.append, clock=self.clock)
        self.redacteur.start()

    def queue(self, kind: str = "notice", lang: str = "fr", tools: list[Any] | None = None) -> None:
        """Add a finished analysis and its waiting text"""

        data = report(tools or [tool_report("get_time")])
        result = AnalysisResult.model_validate(data)
        text_hash = content_hash(build_form(result))
        version = NOTICE_PROMPT_VERSION
        if kind == "translation":
            text_hash = content_hash(translation_items(result))
            version = TRANSLATION_PROMPT_VERSION
        with self.sessions.begin() as session:
            analysis = Analysis(input_raw="uvx demo", state="done", result=data)
            session.add(analysis)
            session.flush()
            session.add(
                AiText(
                    kind=kind,
                    lang=lang,
                    hash=text_hash,
                    prompt_version=version,
                    model=self.settings.ai_model,
                    status="pending",
                    analysis_id=analysis.id,
                    created_at=self.clock.now,
                    updated_at=self.clock.now,
                )
            )

    def row(self) -> AiText:
        """Return the only text"""

        with self.sessions() as session:
            return session.query(AiText).one()

    def alerts(self) -> list[str]:
        """Return the codes of the alerts for the admin"""

        with self.sessions() as session:
            return [alert.code for alert in session.query(AiAdminAlert).all()]

    def state(self) -> AiState:
        """Return the state of the writer"""

        with self.sessions() as session:
            return session.get(AiState, 1)


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    """Simulate the API; a request to anything else fails"""

    with respx.mock(assert_all_called=False) as router:
        yield router


def test_request_body_is_exactly_the_expected_one(api: respx.MockRouter) -> None:
    """Fixed address and headers; the body has these fields only: no sampling setting, no tool"""

    route = api.post(API_URL).mock(return_value=answer(GOOD_NOTICE))
    settings = make_settings(anthropic_api_key=KEY)
    form = build_form(AnalysisResult.model_validate(report([tool_report("get_time")])))
    message = notice_message(form, "fr")
    body = notice_body(settings, form, "fr")
    reply = call_api(settings, body)
    request = route.calls.last.request
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == KEY
    assert request.headers["anthropic-version"] == "2026-10-21"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "model": "claude-sonnet-5-5",
        "max_tokens": 3500,
        "system": NOTICE_SYSTEM,
        "messages": [{"role": "user", "content": message}],
        "output_config": {"effort": "low"},
        "thinking": {"type": "between_tools"},
    }
    assert "Answer with this JSON object only" in body["system"]
    assert reply.kind is CallKind.ANSWERED
    assert json.loads(reply.text) == GOOD_NOTICE
    assert (reply.input_tokens, reply.output_tokens, reply.request_id) == (1000, 500, "req_1")


def test_versions_leave_the_broken_texts_out_of_the_cache() -> None:
    """Without the imposed output, the prompts changed: new versions"""

    assert (NOTICE_PROMPT_VERSION, TRANSLATION_PROMPT_VERSION) == ("notice-v3", "translation-v3")


def test_with_format_only_adds_the_schema() -> None:
    """The diagnosis mode sends the same request plus output_config.format, nothing else"""

    settings = make_settings()
    form = build_form(AnalysisResult.model_validate(report([tool_report("get_time")])))
    current = notice_body(settings, form, "fr")
    checked = notice_body(settings, form, "fr", with_format=True)
    assert checked["output_config"].pop("format") == {"type": "json_schema", "schema": NOTICE_SCHEMA}
    assert checked == current
    items = [{"id": "tool_0", "text": "Gives the time."}]
    assert "format" not in translation_body(settings, items)["output_config"]
    assert translation_body(settings, items, with_format=True)["output_config"]["format"]["schema"] == TRANSLATION_SCHEMA


def raw_answer(text: str) -> httpx.Response:
    """Return an answer of the API whose text block is exactly this text"""

    return httpx.Response(
        200,
        content=json.dumps(
            {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1}},
            ensure_ascii=False,
        ).encode("utf-8"),
    )


CLEAN_FRENCH = {**GOOD_NOTICE, "summary": "Il lit à l'été, ça, très « simple » et è."}


@pytest.mark.parametrize(
    ("text", "status", "reason"),
    [
        (json.dumps(GOOD_NOTICE), "ready", None),
        ("  \n" + json.dumps(GOOD_NOTICE, indent=2) + "\n ", "ready", None),
        ("```json\n" + json.dumps(GOOD_NOTICE) + "\n```", "ready", None),
        (json.dumps(CLEAN_FRENCH, ensure_ascii=False), "ready", None),
        ("Voici la notice :\n" + json.dumps(GOOD_NOTICE), "rejected", "bad_json"),
        (json.dumps(GOOD_NOTICE) + "\nVoilà.", "rejected", "bad_json"),
        (json.dumps(GOOD_NOTICE) + json.dumps(GOOD_NOTICE), "rejected", "bad_json"),
        ("```json\n" + json.dumps(GOOD_NOTICE) + "\n```\n```json\n{}\n```", "rejected", "bad_json"),
        ("```\n" + json.dumps(GOOD_NOTICE) + "\n```", "rejected", "bad_json"),
        (json.dumps(GOOD_NOTICE)[:-20], "rejected", "bad_json"),
        ("[" + json.dumps(GOOD_NOTICE) + "]", "rejected", "bad_json"),
        (json.dumps({**GOOD_NOTICE, "summary": "Il lit \u0102\u00a0Paris."}, ensure_ascii=False), "failed", "encoding"),
    ],
)
def test_reading_the_answer_without_imposed_output(api: respx.MockRouter, text: str, status: str, reason: str | None) -> None:
    """One JSON object alone, or in one json fence; anything else is bad_json, and every check stays"""

    api.post(API_URL).mock(return_value=raw_answer(text))
    bench = Bench()
    bench.queue()
    bench.redacteur.run_once()
    row = bench.row()
    assert (row.status, row.reject_reason) == (status, reason)
    if status == "ready" and "été" in text:
        assert row.content["summary"] == CLEAN_FRENCH["summary"]


def test_output_schema_closes_every_object() -> None:
    """Everything is required and nothing else is allowed"""

    assert NOTICE_SCHEMA["additionalProperties"] is False
    assert set(NOTICE_SCHEMA["required"]) == set(NOTICE_SCHEMA["properties"]) == {
        "summary", "use_cases", "tool_titles", "mismatch", "alert",
    }
    entry = NOTICE_SCHEMA["properties"]["tool_titles"]["items"]
    assert entry["additionalProperties"] is False
    assert set(entry["required"]) == {"name", "title", "sentence"}


def test_a_redirect_is_never_followed(api: respx.MockRouter) -> None:
    """A redirect is a bad request: its target gets nothing"""

    api.post(API_URL).mock(return_value=httpx.Response(302, headers={"location": "https://other.example.com/"}))
    settings = make_settings(anthropic_api_key=KEY)
    assert call_api(settings, {}).kind is CallKind.BAD_REQUEST
    assert api.calls.call_count == 1


def test_cost_uses_the_prices_of_the_settings() -> None:
    """Tokens are multiplied by the price per million"""

    assert call_cost(make_settings(), 1000, 500) == pytest.approx(0.007)
    assert call_cost(make_settings(ai_price_output_per_mtok=20), 0, 1000) == pytest.approx(0.02)


def test_good_answer_is_ready_with_its_cost_and_request_id(api: respx.MockRouter) -> None:
    """The checked text, the tokens, the cost and the request identifier are recorded"""

    api.post(API_URL).mock(return_value=answer(GOOD_NOTICE))
    bench = Bench()
    bench.queue()
    assert bench.redacteur.run_once() is True
    row = bench.row()
    assert row.status == "ready"
    assert row.content["tool_titles"][0]["title"] == "Donner l'heure"
    assert (row.input_tokens, row.output_tokens, row.request_id) == (1000, 500, "req_1")
    assert row.cost_usd == pytest.approx(0.007)
    assert bench.redacteur.run_once() is False


@pytest.mark.parametrize(
    ("stop_reason", "reason"), [("refusal", "refusal"), ("max_tokens", "max_tokens"), ("pause_turn", "bad_json")]
)
def test_an_answer_that_did_not_end_normally_is_rejected(api: respx.MockRouter, stop_reason: str, reason: str) -> None:
    """Only end_turn gives a text; the tokens are still paid and recorded, the text is not kept"""

    api.post(API_URL).mock(return_value=answer(GOOD_NOTICE, stop_reason))
    bench = Bench()
    bench.queue()
    bench.redacteur.run_once()
    row = bench.row()
    assert (row.status, row.reject_reason, row.content) == ("rejected", reason, None)
    assert row.cost_usd == pytest.approx(0.007)


def test_json_out_of_shape_is_rejected(api: respx.MockRouter) -> None:
    """The JSON is checked on this side too"""

    api.post(API_URL).mock(return_value=answer({"summary": "Only this."}))
    bench = Bench()
    bench.queue()
    bench.redacteur.run_once()
    assert (bench.row().status, bench.row().reject_reason) == ("rejected", "bad_json")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, json=USAGE_LIMIT_BODY),
        httpx.Response(402, json={"type": "error", "error": {"type": "billing_error", "message": "Top up."}}),
    ],
)
def test_usage_limit_pauses_everything_for_one_hour(api: respx.MockRouter, response: httpx.Response) -> None:
    """Paused for one hour, the next waiting text goes without a call, then one single try, one alert in 24 hours"""

    route = api.post(API_URL).mock(return_value=response)
    bench = Bench()
    bench.queue()
    assert bench.redacteur.run_once() is True
    row = bench.row()
    assert (row.status, row.reject_reason) == ("paused", "usage_limit")
    assert bench.alerts() == ["usage_limit"]
    assert route.call_count == 1
    assert bench.slept == []
    paused_until = bench.state().paused_until.replace(tzinfo=UTC)
    assert paused_until == NOW + timedelta(hours=1)
    bench.queue(tools=[tool_report("other_tool")])
    assert bench.redacteur.run_once() is False
    assert route.call_count == 1
    with bench.sessions() as session:
        assert {text.status for text in session.query(AiText).all()} == {"paused"}
    bench.clock.now = NOW + timedelta(hours=1, seconds=1)
    with bench.sessions.begin() as session:
        for text in session.query(AiText).all():
            text.status = "pending"
    assert bench.redacteur.run_once() is True
    assert route.call_count == 2
    assert bench.redacteur.run_once() is False
    assert route.call_count == 2
    assert bench.alerts() == ["usage_limit"]
    bench.clock.now = NOW + timedelta(hours=26)
    with bench.sessions.begin() as session:
        session.query(AiText).update({"status": "pending"})
    bench.redacteur.run_once()
    assert bench.alerts() == ["usage_limit", "usage_limit"]


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_key_cuts_the_function_until_restart(api: respx.MockRouter, status: int) -> None:
    """401 or 403: no more call, one alert; a restart with a key tries again"""

    route = api.post(API_URL).mock(return_value=httpx.Response(status, json={"error": {"type": "authentication_error"}}))
    bench = Bench()
    bench.queue()
    bench.redacteur.run_once()
    assert bench.row().status == "disabled"
    assert bench.state().disabled_reason == "auth"
    assert bench.alerts() == ["auth_refused"]
    bench.queue(tools=[tool_report("other_tool")])
    assert bench.redacteur.run_once() is False
    assert route.call_count == 1
    bench.redacteur.start()
    assert bench.state().disabled_reason is None


def test_another_400_alerts_the_admin_and_does_not_try_again(api: respx.MockRouter) -> None:
    """A malformed request is not retried at once; it leaves an alert without the text of the error"""

    route = api.post(API_URL).mock(
        return_value=httpx.Response(400, json={"error": {"type": "invalid_request_error", "message": "thinking.type bad"}})
    )
    bench = Bench()
    bench.queue()
    bench.redacteur.run_once()
    row = bench.row()
    assert (row.status, row.reject_reason) == ("failed", "bad_request")
    assert bench.alerts() == ["bad_request"]
    assert route.call_count == 1
    assert bench.slept == []
    with bench.sessions() as session:
        assert "thinking.type" not in json.dumps(session.query(AiAdminAlert).one().details)


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(429),
        httpx.Response(529),
        httpx.Response(500),
        httpx.Response(503),
        httpx.ReadTimeout("slow"),
        httpx.ConnectError("down"),
    ],
)
def test_overload_is_retried_once_after_20_seconds(api: respx.MockRouter, failure: Any) -> None:
    """One more try after 20 s, then a failure that can be tried again 10 minutes later, without an alert"""

    route = api.post(API_URL).mock(side_effect=[failure, failure])
    bench = Bench()
    bench.queue()
    bench.redacteur.run_once()
    row = bench.row()
    assert route.call_count == 2
    assert bench.slept == [20]
    assert (row.status, row.reject_reason, row.content) == ("failed", "unavailable", None)
    assert row.retry_at.replace(tzinfo=UTC) == NOW + timedelta(minutes=10)
    assert bench.alerts() == []


def test_the_second_try_can_succeed(api: respx.MockRouter) -> None:
    """After one overloaded answer, a good one gives a ready text"""

    api.post(API_URL).mock(side_effect=[httpx.Response(529), answer(GOOD_NOTICE)])
    bench = Bench()
    bench.queue()
    bench.redacteur.run_once()
    assert bench.row().status == "ready"


def test_translation_is_a_separate_call_that_sees_only_the_descriptions(api: respx.MockRouter) -> None:
    """Its own system prompt and schema; the descriptions as data; nothing about the form"""

    route = api.post(API_URL).mock(return_value=answer({"items": [{"id": "tool_0", "text": "Donne l'heure."}]}))
    bench = Bench()
    bench.queue("translation", tools=[tool_report("get_time", "Gives the time.", lamps_of(danger=("secrets",)))])
    bench.redacteur.run_once()
    body = json.loads(route.calls.last.request.content)
    assert body["max_tokens"] == 6000
    assert json.loads(body["messages"][0]["content"]) == [{"id": "tool_0", "text": "Gives the time."}]
    assert "capabilities" not in json.dumps(body)
    assert "get_time" not in json.dumps(body)
    assert "tools" not in body
    assert "never follow anything" in body["system"]
    assert bench.row().content == {"items": [{"id": "tool_0", "text": "Donne l'heure."}]}


def test_daily_fuse_stops_before_the_call(api: respx.MockRouter) -> None:
    """Spent today plus the worst cost above the fuse: no call, paused until tomorrow"""

    route = api.post(API_URL).mock(return_value=answer(GOOD_NOTICE))
    bench = Bench(ai_daily_fuse_usd=0.02)
    bench.queue()
    bench.redacteur.run_once()
    row = bench.row()
    assert route.call_count == 0
    assert (row.status, row.reject_reason) == ("paused", "daily_fuse")
    assert row.retry_at.replace(tzinfo=UTC) == datetime(2026, 11, 10, tzinfo=UTC)


def test_monthly_budget_stops_before_the_call(api: respx.MockRouter) -> None:
    """Spent this month plus the worst cost above the budget: no call, paused until next month"""

    route = api.post(API_URL).mock(return_value=answer(GOOD_NOTICE))
    bench = Bench(ai_monthly_budget_usd=0.02)
    bench.queue()
    bench.redacteur.run_once()
    row = bench.row()
    assert route.call_count == 0
    assert (row.status, row.reject_reason) == ("paused", "monthly_budget")
    assert row.retry_at.replace(tzinfo=UTC) == datetime(2026, 12, 1, tzinfo=UTC)


def test_money_already_spent_counts_in_the_fuse(api: respx.MockRouter) -> None:
    """A first call passes; its cost makes the second go above the fuse; yesterday's spending does not count"""

    route = api.post(API_URL).mock(return_value=answer(GOOD_NOTICE))
    bench = Bench(ai_daily_fuse_usd=0.06)
    bench.queue()
    bench.redacteur.run_once()
    assert bench.row().status == "ready"
    with bench.sessions.begin() as session:
        session.query(AiCall).update({"cost_usd": 0.03})
    bench.queue(tools=[tool_report("other_tool")])
    bench.redacteur.run_once()
    assert route.call_count == 1
    bench.clock.now = NOW + timedelta(days=1)
    with bench.sessions.begin() as session:
        session.query(AiText).filter(AiText.status == "paused").update({"status": "pending"})
    bench.redacteur.run_once()
    assert route.call_count == 2


def test_next_day_and_next_month_are_in_utc() -> None:
    """The fuses come back at the start of the next UTC day or month, December included"""

    moment = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
    assert next_day(moment) == datetime(2027, 1, 1, tzinfo=UTC)
    assert next_month(moment) == datetime(2027, 1, 1, tzinfo=UTC)


def test_a_form_that_changed_makes_no_call(api: respx.MockRouter) -> None:
    """The writer builds the form again from the report: a different hash stops it"""

    route = api.post(API_URL).mock(return_value=answer(GOOD_NOTICE))
    bench = Bench()
    bench.queue()
    with bench.sessions.begin() as session:
        session.query(AiText).update({"hash": "f" * 64})
    bench.redacteur.run_once()
    assert route.call_count == 0
    assert (bench.row().status, bench.row().reject_reason) == ("failed", "no_report")


def test_the_key_comes_out_nowhere(api: respx.MockRouter, caplog: pytest.LogCaptureFixture) -> None:
    """Even when the API repeats the key, it reaches neither a log line, nor the database"""

    caplog.handler.addFilter(SecretFilter(KEY))
    api.post(API_URL).mock(
        side_effect=[
            httpx.Response(401, json={"error": {"type": "authentication_error", "message": f"bad key {KEY}"}}),
            httpx.Response(400, json={"error": {"type": "invalid_request_error", "message": f"bad {KEY}"}}),
            httpx.ConnectError(f"cannot connect with {KEY}"),
            httpx.ConnectError(f"cannot connect with {KEY}"),
        ]
    )
    bench = Bench()
    bench.queue()
    with caplog.at_level("INFO"):
        bench.redacteur.run_once()
        bench.redacteur.start()
        with bench.sessions.begin() as session:
            session.query(AiText).update({"status": "pending"})
        bench.redacteur.run_once()
        with bench.sessions.begin() as session:
            session.query(AiText).update({"status": "pending"})
        bench.redacteur.run_once()
    assert KEY not in caplog.text
    assert "CANARY" not in repr(bench.settings)
    with bench.sessions() as session:
        stored = [repr(vars(row)) for model in (AiText, AiAdminAlert, AiState, AiCall) for row in session.query(model).all()]
    assert stored
    assert "CANARY" not in "".join(stored)


BROKEN_NOTICE = {**GOOD_NOTICE, "summary": "Ce serveur donne \u0102\u00a0ton assistant l'heure."}


def calls(bench: Bench) -> list[tuple[str, str | None]]:
    """Return the outcome and the rejection code of every logged call, oldest first"""

    with bench.sessions() as session:
        return [(call.outcome, call.reject_reason) for call in session.query(AiCall).order_by(AiCall.created_at).all()]


def requeue(bench: Bench) -> None:
    """Ask the text again, as the API does when a visitor opens the report"""

    with bench.sessions.begin() as session:
        session.query(AiText).update({"status": "pending", "retry_at": None})


def test_encoding_then_clean_gives_a_ready_text_in_two_calls(api: respx.MockRouter) -> None:
    """A broken answer is retried at once, and the clean second one is kept; both calls are logged and paid"""

    route = api.post(API_URL).mock(side_effect=[answer(BROKEN_NOTICE), answer(GOOD_NOTICE)])
    bench = Bench()
    bench.queue()
    bench.redacteur.run_once()
    row = bench.row()
    assert route.call_count == 2
    assert (row.status, row.reject_reason) == ("ready", None)
    assert row.content["summary"] == GOOD_NOTICE["summary"]
    assert row.cost_usd == pytest.approx(0.014)
    assert calls(bench) == [("answered", "encoding"), ("answered", None)]
    assert bench.slept == []


def test_encoding_twice_fails_for_one_hour_with_the_fallback(api: respx.MockRouter) -> None:
    """Two broken answers: failed, not rejected, and nothing of the text is kept"""

    route = api.post(API_URL).mock(return_value=answer(BROKEN_NOTICE))
    bench = Bench()
    bench.queue()
    bench.redacteur.run_once()
    row = bench.row()
    assert route.call_count == 2
    assert (row.status, row.reject_reason, row.content) == ("failed", "encoding", None)
    assert row.retry_at.replace(tzinfo=UTC) == NOW + timedelta(hours=1)
    assert calls(bench) == [("answered", "encoding"), ("answered", "encoding")]
    with bench.sessions() as session:
        assert "\u0102" not in json.dumps([vars(call).get("reject_reason") for call in session.query(AiCall).all()])


def test_translation_with_broken_encoding_is_retried_as_a_whole(api: respx.MockRouter) -> None:
    """The rule applies to the whole translation call"""

    route = api.post(API_URL).mock(
        side_effect=[
            answer({"items": [{"id": "tool_0", "text": "Donne l'heure \u0102\u00a0Paris."}]}),
            answer({"items": [{"id": "tool_0", "text": "Donne l'heure à Paris."}]}),
        ]
    )
    bench = Bench()
    bench.queue("translation", tools=[tool_report("get_time", "Gives the time in Paris.")])
    bench.redacteur.run_once()
    assert route.call_count == 2
    assert bench.row().content == {"items": [{"id": "tool_0", "text": "Donne l'heure à Paris."}]}


def test_four_calls_a_day_for_one_text(api: respx.MockRouter) -> None:
    """Two rounds of two broken answers use the four calls of the day; the next request waits for tomorrow"""

    route = api.post(API_URL).mock(return_value=answer(BROKEN_NOTICE))
    bench = Bench()
    bench.queue()
    bench.redacteur.run_once()
    bench.clock.now = NOW + timedelta(hours=1, minutes=1)
    requeue(bench)
    bench.redacteur.run_once()
    assert route.call_count == 4
    bench.clock.now = NOW + timedelta(hours=2, minutes=2)
    requeue(bench)
    bench.redacteur.run_once()
    row = bench.row()
    assert route.call_count == 4
    assert (row.status, row.reject_reason) == ("paused", "daily_text_cap")
    assert row.retry_at.replace(tzinfo=UTC) == datetime(2026, 11, 10, tzinfo=UTC)
    bench.clock.now = datetime(2026, 11, 10, 0, 5, tzinfo=UTC)
    requeue(bench)
    route.side_effect = None
    route.return_value = answer(GOOD_NOTICE)
    bench.redacteur.run_once()
    assert route.call_count == 5
    assert bench.row().status == "ready"


def test_the_cap_stops_the_second_try_too(api: respx.MockRouter) -> None:
    """With three calls already made today, a broken answer is not retried"""

    route = api.post(API_URL).mock(return_value=answer(BROKEN_NOTICE))
    bench = Bench()
    bench.queue()
    with bench.sessions.begin() as session:
        text = session.query(AiText).one()
        for _ in range(3):
            session.add(AiCall(text_id=text.id, kind="notice", lang="fr", outcome="unavailable", created_at=NOW))
    bench.redacteur.run_once()
    assert route.call_count == 1
    assert (bench.row().status, bench.row().reject_reason) == ("paused", "daily_text_cap")


def test_the_fuse_blocks_the_second_try(api: respx.MockRouter) -> None:
    """The second call goes through the fuse with its worst cost, like the first"""

    route = api.post(API_URL).mock(return_value=answer(BROKEN_NOTICE))
    bench = Bench(ai_daily_fuse_usd=0.04)
    bench.queue()
    bench.redacteur.run_once()
    row = bench.row()
    assert route.call_count == 1
    assert (row.status, row.reject_reason) == ("paused", "daily_fuse")
    assert calls(bench) == [("answered", "encoding")]


def test_a_forbidden_word_is_not_tried_again(api: respx.MockRouter) -> None:
    """Every other rejection stays final for this prompt version"""

    route = api.post(API_URL).mock(return_value=answer({**GOOD_NOTICE, "summary": "Ce serveur est fiable."}))
    bench = Bench()
    bench.queue()
    bench.redacteur.run_once()
    assert route.call_count == 1
    assert (bench.row().status, bench.row().reject_reason) == ("rejected", "forbidden_word")
    assert calls(bench) == [("answered", "forbidden_word")]


def test_every_call_is_logged_even_without_an_answer(api: respx.MockRouter) -> None:
    """An overloaded API counts too: one logged call, no token"""

    api.post(API_URL).mock(return_value=httpx.Response(529))
    bench = Bench()
    bench.queue()
    bench.redacteur.run_once()
    assert calls(bench) == [("unavailable", None)]


def test_translation_sends_parameters_and_never_their_names(api: respx.MockRouter) -> None:
    """The body holds ids made by MCPlain and the descriptions, not the names; a rejected parameter keeps its original"""

    route = api.post(API_URL).mock(
        return_value=answer(
            {
                "items": [
                    {"id": "tool_0", "text": "Donne l'heure."},
                    {"id": "tool_0_param_0", "text": "Fuseau horaire"},
                    {"id": "tool_0_param_1", "text": "x" * 300},
                    {"id": "tool_9_param_0", "text": "Inconnu"},
                ]
            }
        )
    )
    tool = {
        **tool_report("get_time", "Gives the time."),
        "parameters": [{"name": "timezone_CANARY", "description": "Time zone"}, {"name": "format_CANARY", "description": "Format"}],
    }
    bench = Bench()
    bench.queue("translation", tools=[tool])
    bench.redacteur.run_once()
    sent = route.calls.last.request.content.decode("utf-8")
    assert "CANARY" not in sent
    assert json.loads(json.loads(sent)["messages"][0]["content"]) == [
        {"id": "tool_0", "text": "Gives the time."},
        {"id": "tool_0_param_0", "text": "Time zone"},
        {"id": "tool_0_param_1", "text": "Format"},
    ]
    row = bench.row()
    assert (row.status, row.reject_reason) == ("ready", "length")
    assert row.content == {"items": [{"id": "tool_0", "text": "Donne l'heure."}, {"id": "tool_0_param_0", "text": "Fuseau horaire"}]}
