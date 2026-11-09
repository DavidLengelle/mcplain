"""Tests of the form given to the AI: only what the validated report says, filtered, and no text of a third party"""

import json

import pytest
from helpers import lamps_of, make_settings, report, tool_report
from mcplain.models import AnalysisResult

from mcplain_api.ai_client import build_body
from mcplain_api.ai_form import MAX_FORM_TOOLS, MAX_TRANSLATION_CHARS, build_form, content_hash, translation_items
from mcplain_api.ai_prompts import NOTICE_SCHEMA, NOTICE_SYSTEM, notice_message

CANARY = "CANARY-7f3a"


def result_of(tools: list[dict[str, object]], **server: object) -> AnalysisResult:
    """Return a validated report"""

    return AnalysisResult.model_validate(report(tools, **server))


def domain(name: str, kind: str = "server_code") -> dict[str, object]:
    """Return one cited address of a report"""

    return {"domain": name, "url": f"https://{name}/path-{CANARY}", "file": "a.py", "line": 1, "location_kind": kind}


def test_capabilities_are_yes_or_no_and_never_a_color() -> None:
    """The six lamps become yes or no, danger counts as yes, and no color word exists in the form"""

    lamps = lamps_of("files_read", danger=("secrets",))
    form = build_form(result_of([tool_report("get_time", lamps=lamps)]))
    assert form["tools"] == [
        {
            "name": "get_time",
            "capabilities": {
                "reads_files": True,
                "writes_files": False,
                "internet": False,
                "commands": False,
                "secrets": True,
                "hidden_text": False,
            },
        }
    ]
    assert not {"danger", "orange", "red", "green", "gray", "color"} & set(json.dumps(form).replace('"', " ").split())


def test_names_are_filtered_cut_and_never_empty_or_twice_the_same() -> None:
    """Names keep letters, digits and underscores, 40 at most; empty ones get a number, doubles a suffix"""

    tools = [tool_report(name) for name in ("get-weather!", "é!", "a" * 60, "get_weather", "get weather")]
    names = [tool["name"] for tool in build_form(result_of(tools))["tools"]]
    assert names == ["get_weather", "tool_2", "a" * 40, "get_weather_2", "get_weather_3"]


def test_at_most_sixty_tools_with_the_real_count() -> None:
    """The form holds 60 tools and says how many there really are"""

    form = build_form(result_of([tool_report(f"tool_{index}") for index in range(61)]))
    assert len(form["tools"]) == MAX_FORM_TOOLS
    assert form["tool_count"] == 61


def test_domains_are_cited_filtered_sorted_and_limited() -> None:
    """Only host names of the server code, in the allowed characters, 20 at most; paths never enter"""

    references = [domain(f"h{index:02}.example.com") for index in range(25)]
    references += [domain("IN.TEST.example.com", "test_or_example"), domain("[::1]"), domain("b" * 254), domain("h00.example.com")]
    form = build_form(result_of([tool_report("a")], domains=references, internet_domains=["only-contacted.example.com"]))
    assert form["domains_cited_in_code"] == [f"h{index:02}.example.com" for index in range(20)]
    assert "only-contacted" not in json.dumps(form)
    assert "contacted" not in " ".join(form)


def test_libraries_stay_empty_because_the_report_has_none() -> None:
    """The report keeps only the dependencies with a malicious report: none of them reaches the form"""

    data = report([tool_report("a")])
    data["reputation"] = {
        "status": "checked",
        "packages": [{"name": "somelib", "ecosystem": "npm", "dependency": True, "malicious": [{"id": "MAL-1"}]}],
    }
    form = build_form(AnalysisResult.model_validate(data))
    assert form["libraries"] == []
    assert "somelib" not in json.dumps(form)


@pytest.mark.parametrize(("language", "expected"), [("python", "python"), ("typescript", "typescript"), ("go", "unknown")])
def test_language_comes_from_a_fixed_list(language: str, expected: str) -> None:
    """A language outside the list never reaches the form as text"""

    data = report([tool_report("a")])
    data["servers"][0]["language"] = language
    assert build_form(AnalysisResult.model_validate(data))["language"] == expected


def test_no_tool_gives_no_form() -> None:
    """Without a recognized tool, there is no form, so no call"""

    assert build_form(result_of([])) is None
    empty = report([])
    empty["servers"] = []
    assert build_form(AnalysisResult.model_validate(empty)) is None


def test_hash_is_the_sha256_of_a_canonical_json() -> None:
    """The order of the keys does not change the hash; the content does"""

    assert content_hash({"a": 1, "b": [2]}) == content_hash({"b": [2], "a": 1})
    assert content_hash({"a": 1}) != content_hash({"a": 2})
    assert len(content_hash({})) == 64


def test_canary_never_reaches_the_request_body() -> None:
    """Descriptions, README, package name, quotes and code texts hold the canary: the body never does"""

    data = report(
        [
            {
                **tool_report("get_time", f"Gives the time. {CANARY}"),
                "title": f"Title {CANARY}",
                "parameters": [{"name": CANARY, "description": CANARY}],
                "findings": [
                    {"capability": "network", "file": f"README-{CANARY}.md", "line": 1, "column": 1, "snippet": CANARY, "location_kind": "server_code"}
                ],
            }
        ],
        name=f"server-{CANARY}",
        domains=[domain("example.com")],
        compiled_files=[CANARY],
    )
    data["source"]["name"] = f"package-{CANARY}"
    data["verdict"]["alerts"] = [{"rule": "O01", "color": "orange", "kind": "power_to_know", "quote": CANARY, "detail": CANARY}]
    assert CANARY in json.dumps(data)
    form = build_form(AnalysisResult.model_validate(data))
    body = build_body(make_settings(), NOTICE_SYSTEM, notice_message(form, "fr"), NOTICE_SCHEMA, 3500)
    assert CANARY not in json.dumps(body)


def test_translation_receives_the_descriptions_only_until_the_limit() -> None:
    """Empty descriptions are skipped; past 12 000 characters, the others stay in the original language"""

    tools = [
        tool_report("a", "First."),
        tool_report("b", "   "),
        tool_report("c", "x" * (MAX_TRANSLATION_CHARS - 6)),
        tool_report("d", "Too much."),
        tool_report("e", "After."),
    ]
    items = translation_items(result_of(tools))
    assert [item["id"] for item in items] == ["tool_0", "tool_2"]
    assert sum(len(item["text"]) for item in items) == MAX_TRANSLATION_CHARS
