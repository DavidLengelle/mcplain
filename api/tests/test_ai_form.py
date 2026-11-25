"""Tests of the form given to the AI: only what the validated report says, filtered, and no text of a third party"""

import json
import re

import pytest
from helpers import lamps_of, make_settings, report, tool_report
from mcplain.models import AnalysisResult

from mcplain_api.ai_client import notice_body
from mcplain_api.ai_form import MAX_FORM_TOOLS, MAX_TRANSLATION_CHARS, build_form, content_hash, translation_items
from mcplain_api.ai_prompts import notice_message

CANARY = "CANARY-7f3a"


def result_of(tools: list[dict[str, object]], **server: object) -> AnalysisResult:
    """Return a validated report"""

    return AnalysisResult.model_validate(report(tools, **server))


def domain(name: str, kind: str = "server_code") -> dict[str, object]:
    """Return one cited address of a report"""

    return {"domain": name, "url": f"https://{name}/path-{CANARY}", "file": "a.py", "line": 1, "location_kind": kind}


ALL_UNKNOWN = {name: "unknown" for name in ("reads_files", "writes_files", "internet", "commands", "secrets", "hidden_text")}


def capabilities(**values: str) -> dict[str, str]:
    """Return the six capabilities of the form: no, unless given"""

    names = ("reads_files", "writes_files", "internet", "commands", "secrets", "hidden_text")
    return {name: values.get(name, "no") for name in names}


def with_gap(name: str, lamps: list[dict[str, object]] | None = None) -> dict[str, object]:
    """Return a tool of a report whose code MCPlain could not follow"""

    return {**tool_report(name, lamps=lamps), "gaps": ["unresolved_call"]}


def test_capabilities_are_yes_or_no_and_never_a_color() -> None:
    """The six lamps become yes or no on a followed tool, danger counts as yes, and no color word exists in the form"""

    lamps = lamps_of("files_read", danger=("secrets",))
    form = build_form(result_of([tool_report("get_time", lamps=lamps)]))
    assert form["tools"] == [{"name": "get_time", "capabilities": capabilities(reads_files="yes", secrets="yes")}]
    assert form["server_capabilities"] == capabilities()
    assert not {"danger", "orange", "red", "green", "gray", "color"} & set(json.dumps(form).replace('"', " ").split())


def test_a_tool_not_followed_is_unknown_and_never_no() -> None:
    """A tracking gap turns every unlit capability into unknown, for the tool and for the server; a lit one stays yes"""

    form = build_form(result_of([with_gap("calculate"), with_gap("convert", lamps_of("internet")), tool_report("get_time")]))
    assert form["tools"][0] == {"name": "calculate", "capabilities": ALL_UNKNOWN}
    assert form["tools"][1]["capabilities"] == {**ALL_UNKNOWN, "internet": "yes"}
    assert form["tools"][2]["capabilities"] == capabilities()
    assert form["server_capabilities"] == ALL_UNKNOWN
    assert '"no"' not in json.dumps(form["tools"][0])


def test_the_form_of_calculator_is_the_one_shown_to_david() -> None:
    """One tool with a gap and no lamp: every capability is unknown, and the message holds nothing else"""

    form = build_form(result_of([with_gap("calculate")]))
    assert notice_message(form, "fr") == (
        '{"answer_language":"fr","form":{"domains_cited_in_code":[],"language":"python","server_capabilities":'
        '{"commands":"unknown","hidden_text":"unknown","internet":"unknown","reads_files":"unknown","secrets":"unknown",'
        '"writes_files":"unknown"},"tool_count":1,"tools":[{"capabilities":{"commands":"unknown","hidden_text":"unknown",'
        '"internet":"unknown","reads_files":"unknown","secrets":"unknown","writes_files":"unknown"},"name":"calculate"}]}}'
    )


@pytest.mark.parametrize(
    "server",
    [
        {"compiled_files": ["helpers.so"]},
        {"skipped_files": [{"file": "big.py", "reason": "too_large", "size": 9, "location_kind": "server_code"}]},
        {"parse_errors": [{"file": "broken.py", "line": 3, "column": 1, "location_kind": "server_code"}]},
    ],
)
def test_a_server_read_in_part_makes_every_tool_unknown(server: dict[str, object]) -> None:
    """A tool that calls unread code has no gap: MCPlain still says unknown for every tool of a server read in part"""

    form = build_form(result_of([tool_report("keep", lamps=lamps_of("files_write")), tool_report("list")], **server))
    assert form["tools"][0]["capabilities"] == {**ALL_UNKNOWN, "writes_files": "yes"}
    assert form["tools"][1]["capabilities"] == ALL_UNKNOWN
    assert form["server_capabilities"] == ALL_UNKNOWN


def test_reading_tests_in_part_changes_nothing() -> None:
    """A skipped file of the tests is not server code: the tools keep yes or no"""

    skipped = [{"file": "tests/big.py", "reason": "too_large", "size": 9, "location_kind": "test_or_example"}]
    form = build_form(result_of([tool_report("list")], skipped_files=skipped))
    assert form["tools"][0]["capabilities"] == capabilities()


def test_a_network_library_not_followed_makes_internet_unknown() -> None:
    """When a network library is used but no request was recognized, internet is unknown everywhere it is not yes"""

    form = build_form(
        result_of([tool_report("query")], network_not_followed=["pg"], lamps=lamps_of("internet", "files_read"))
    )
    assert form["tools"][0]["capabilities"] == capabilities(internet="unknown")
    assert form["server_capabilities"] == capabilities(internet="yes", reads_files="yes")


def test_a_tool_outside_the_server_code_is_unknown() -> None:
    """MCPlain does not count the code of a tool declared outside the server code: nothing is known about it"""

    tool = {**tool_report("example"), "location_kind": "test_or_example"}
    form = build_form(result_of([tool]))
    assert form["tools"][0]["capabilities"] == ALL_UNKNOWN
    assert form["server_capabilities"] == ALL_UNKNOWN


def test_server_capabilities_count_the_code_that_runs_at_start() -> None:
    """The server lamps come from all its code, start included, even when no tool lamp is lit"""

    form = build_form(result_of([tool_report("think")], lamps=lamps_of("files_read", "internet")))
    assert form["tools"][0]["capabilities"] == capabilities()
    assert form["server_capabilities"] == capabilities(reads_files="yes", internet="yes")


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


def test_no_library_field_and_no_dependency_name() -> None:
    """The report keeps only the dependencies with a malicious report: the form has no libraries field, and no name"""

    data = report([tool_report("a")])
    data["reputation"] = {
        "status": "checked",
        "packages": [{"name": "somelib", "ecosystem": "npm", "dependency": True, "malicious": [{"id": "MAL-1"}]}],
    }
    form = build_form(AnalysisResult.model_validate(data))
    assert set(form) == {"language", "tool_count", "tools", "server_capabilities", "domains_cited_in_code"}
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
    body = notice_body(make_settings(), form, "fr")
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


def with_parameters(name: str, description: str, *parameters: tuple[str, str | None]) -> dict[str, object]:
    """Return a tool of a report with its parameters"""

    return {**tool_report(name, description), "parameters": [{"name": key, "description": text} for key, text in parameters]}


def test_parameter_descriptions_get_ids_made_of_positions() -> None:
    """tool_<i>_param_<j>; a parameter without description is not sent, and no name ever is"""

    tools = [
        with_parameters("fetch", "Fetches a URL.", ("url", "URL to fetch"), ("raw", None), ("max_length", "Maximum number of characters")),
        with_parameters("other", "", ("query", "  "), ("CANARY-7f3a-name", "What to look for")),
    ]
    items = translation_items(result_of(tools))
    assert items == [
        {"id": "tool_0", "text": "Fetches a URL."},
        {"id": "tool_0_param_0", "text": "URL to fetch"},
        {"id": "tool_0_param_2", "text": "Maximum number of characters"},
        {"id": "tool_1_param_1", "text": "What to look for"},
    ]
    for item in items:
        assert re.fullmatch(r"tool_\d+(?:_param_\d+)?", item["id"])
    assert "CANARY" not in json.dumps(items)


def test_tool_descriptions_come_first_under_the_limit() -> None:
    """Every tool description is sent before any parameter; what does not fit stays in the original"""

    tools = [
        with_parameters("a", "x" * 5000, ("p", "first parameter " * 10)),
        with_parameters("b", "y" * 5000, ("q", "z" * 1500)),
        with_parameters("c", "w" * 1000, ("r", "never sent")),
    ]
    items = translation_items(result_of(tools))
    assert [item["id"] for item in items] == ["tool_0", "tool_1", "tool_2", "tool_0_param_0"]
    assert sum(len(item["text"]) for item in items) <= MAX_TRANSLATION_CHARS
