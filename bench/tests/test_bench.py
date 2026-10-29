"""Tests of the bench script, with a simulated API"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

import bench

API = "http://api.test"
ANALYSIS_ID = "00000000-0000-4000-8000-000000000001"


def view(state: str, result: dict[str, Any] | None = None, error_code: str | None = None) -> dict[str, Any]:
    """Return an API view of an analysis"""

    return {
        "id": ANALYSIS_ID,
        "state": state,
        "from_cache": False,
        "result": result,
        "error_code": error_code,
    }


def result(
    color: str,
    gray_case: str | None = None,
    rules: list[str] | None = None,
    error: str | None = None,
    version: str | None = "1.0.0",
) -> dict[str, Any]:
    """Return an analysis result with a verdict"""

    alerts = [{"rule": rule} for rule in rules or []]
    data: dict[str, Any] = {
        "status": "ok",
        "source": {"version": version},
        "servers": [
            {
                "tools": [
                    {"location_kind": "server_code", "gaps": ["unknown_type"], "description_is_dynamic": False},
                    {"location_kind": "server_code", "gaps": [], "description_is_dynamic": True},
                    {"location_kind": "test_or_example", "gaps": ["dict_call"], "description_is_dynamic": False},
                ],
                "parse_errors": [],
                "skipped_files": [{"file": "big.js"}],
                "compiled_files": [],
                "files_analyzed": 4,
            }
        ],
        "verdict": {"color": color, "gray_case": gray_case, "alerts": alerts, "reasons": ["no_alert"]},
    }
    if error is not None:
        data["status"] = "error"
        data["error"] = {"code": error, "params": {}}
    return data


def server(identifier: str = "fetch", witness: bool = False, expected: str | None = None) -> bench.Server:
    """Return a bench server"""

    return bench.Server(
        id=identifier,
        input=f"uvx {identifier}",
        language="python",
        group="popular",
        why="test",
        expected=expected,
        witness=witness,
    )


def record(identifier: str, color: str | None, outcome: str = bench.VERDICT, **extra: Any) -> dict[str, Any]:
    """Return a finished record"""

    item = bench.base_record(server(identifier))
    item.update({"outcome": outcome, "color": color, "version": "1.0.0"})
    item.update(extra)
    if color == "gray" and item["cause"] is None:
        item["cause"] = bench.gray_cause(item)
    return item


def no_sleep(seconds: float) -> None:
    """Do not wait in tests"""


def test_the_list_follows_its_criteria() -> None:
    servers = bench.load_servers()
    assert 45 <= len(servers) <= 60
    javascript = [item for item in servers if item.language == "javascript"]
    python = [item for item in servers if item.language == "python"]
    assert 0.55 <= len(javascript) / (len(javascript) + len(python)) <= 0.65
    witnesses = {item.id: item.expected for item in servers if item.witness}
    assert witnesses == {"fetch": "orange", "filesystem": "orange", "github-go": "gray"}
    assert all(item.input.startswith(("npx -y ", "uvx ")) for item in servers if item.language != "go")
    assert all(item.why for item in servers)


def test_duplicate_ids_are_refused(tmp_path: Path) -> None:
    entry = '[[server]]\nid = "a"\ninput = "uvx a"\nlanguage = "python"\ngroup = "popular"\nwhy = "x"\n'
    path = tmp_path / "servers.toml"
    path.write_text(entry + entry, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        bench.load_servers(path)


def test_a_witness_needs_an_expected_color(tmp_path: Path) -> None:
    path = tmp_path / "servers.toml"
    path.write_text(
        '[[server]]\nid = "a"\ninput = "uvx a"\nlanguage = "python"\ngroup = "witness"\nwhy = "x"\nwitness = true\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="witness"):
        bench.load_servers(path)


def test_engine_version_is_read_from_the_repository() -> None:
    assert bench.engine_version().count(".") == 2


@respx.mock
def test_an_analysis_is_followed_until_its_end() -> None:
    respx.post(f"{API}/api/analyses").mock(return_value=httpx.Response(202, json={"id": ANALYSIS_ID, "state": "queued"}))
    respx.get(f"{API}/api/analyses/{ANALYSIS_ID}").mock(
        side_effect=[
            httpx.Response(200, json=view("queued")),
            httpx.Response(200, json=view("analyzing")),
            httpx.Response(200, json=view("done", result("orange", rules=["O01", "O08", "O01"]))),
        ]
    )
    with httpx.Client(base_url=API) as client:
        item = bench.analyze_one(client, server(), poll=0, sleep=no_sleep)
    assert item["outcome"] == bench.VERDICT
    assert item["color"] == "orange"
    assert item["rules"] == ["O01", "O08"]
    assert item["version"] == "1.0.0"
    assert item["analysis_id"] == ANALYSIS_ID
    assert item["duration_seconds"] is not None
    assert item["details"]["tools"] == 2
    assert item["details"]["tools_with_gaps"] == 1
    assert item["details"]["gaps"] == {"unknown_type": 1}
    assert item["details"]["dynamic_descriptions"] == 1
    assert item["details"]["skipped_files"] == 1


@respx.mock
def test_a_registry_outage_is_a_failure_apart() -> None:
    respx.post(f"{API}/api/analyses").mock(return_value=httpx.Response(202, json={"id": ANALYSIS_ID}))
    respx.get(f"{API}/api/analyses/{ANALYSIS_ID}").mock(
        return_value=httpx.Response(200, json=view("failed", result("gray", "error", error="fetch.network_error")))
    )
    with httpx.Client(base_url=API) as client:
        item = bench.analyze_one(client, server(), poll=0, sleep=no_sleep)
    assert item["outcome"] == bench.NETWORK_FAILURE
    assert item["error_code"] == "fetch.network_error"
    assert item["cause"] is None


@respx.mock
def test_a_package_that_does_not_exist_is_a_failure_apart() -> None:
    respx.post(f"{API}/api/analyses").mock(return_value=httpx.Response(202, json={"id": ANALYSIS_ID}))
    respx.get(f"{API}/api/analyses/{ANALYSIS_ID}").mock(
        return_value=httpx.Response(200, json=view("failed", result("gray", "error", error="fetch.pypi_not_found")))
    )
    with httpx.Client(base_url=API) as client:
        item = bench.analyze_one(client, server(), poll=0, sleep=no_sleep)
    assert item["outcome"] == bench.INPUT_FAILURE


@respx.mock
def test_an_atelier_timeout_is_a_gray_of_the_engine_with_its_code() -> None:
    respx.post(f"{API}/api/analyses").mock(return_value=httpx.Response(202, json={"id": ANALYSIS_ID}))
    respx.get(f"{API}/api/analyses/{ANALYSIS_ID}").mock(
        return_value=httpx.Response(200, json=view("failed", result("gray", "timeout", error="job.atelier_timeout")))
    )
    with httpx.Client(base_url=API) as client:
        item = bench.analyze_one(client, server(), poll=0, sleep=no_sleep)
    assert item["outcome"] == bench.VERDICT
    assert item["cause"] == "timeout (job.atelier_timeout)"


@respx.mock
def test_a_refused_input_and_a_full_queue_are_failures_apart() -> None:
    route = respx.post(f"{API}/api/analyses")
    route.mock(return_value=httpx.Response(400, json={"error": {"code": "input.invalid_npm_name", "params": {}}}))
    with httpx.Client(base_url=API) as client:
        refused = bench.analyze_one(client, server(), poll=0, sleep=no_sleep)
        route.mock(return_value=httpx.Response(503, json={"error": {"code": "api.queue_full", "params": {}}}))
        full = bench.analyze_one(client, server(), poll=0, sleep=no_sleep)
        route.mock(return_value=httpx.Response(502, text="bad gateway"))
        broken = bench.analyze_one(client, server(), poll=0, sleep=no_sleep)
    assert (refused["outcome"], refused["error_code"]) == (bench.INPUT_FAILURE, "input.invalid_npm_name")
    assert (full["outcome"], full["error_code"]) == (bench.NETWORK_FAILURE, "api.queue_full")
    assert (broken["outcome"], broken["error_code"]) == (bench.NETWORK_FAILURE, "http.502")


@respx.mock
def test_an_api_that_does_not_answer_is_a_failure_apart() -> None:
    respx.post(f"{API}/api/analyses").mock(side_effect=httpx.ConnectError("refused"))
    with httpx.Client(base_url=API) as client:
        item = bench.analyze_one(client, server(), poll=0, sleep=no_sleep)
    assert (item["outcome"], item["error_code"]) == (bench.NETWORK_FAILURE, "bench.api_unreachable")


@respx.mock
def test_polling_errors_stop_after_a_few_tries() -> None:
    respx.post(f"{API}/api/analyses").mock(return_value=httpx.Response(202, json={"id": ANALYSIS_ID}))
    route = respx.get(f"{API}/api/analyses/{ANALYSIS_ID}").mock(return_value=httpx.Response(500))
    with httpx.Client(base_url=API) as client:
        item = bench.analyze_one(client, server(), poll=0, sleep=no_sleep)
    assert item["outcome"] == bench.NETWORK_FAILURE
    assert route.call_count == bench.MAX_POLL_ERRORS


@respx.mock
def test_an_analysis_that_never_ends_is_stopped_by_the_bench() -> None:
    respx.post(f"{API}/api/analyses").mock(return_value=httpx.Response(202, json={"id": ANALYSIS_ID}))
    respx.get(f"{API}/api/analyses/{ANALYSIS_ID}").mock(return_value=httpx.Response(200, json=view("queued")))
    ticks = iter(range(100))
    with httpx.Client(base_url=API) as client:
        item = bench.analyze_one(client, server(), timeout=5, poll=0, sleep=no_sleep, clock=lambda: next(ticks))
    assert (item["outcome"], item["error_code"]) == (bench.BENCH_TIMEOUT, "bench.timeout")


def test_the_summary_counts_clear_verdicts_on_analyzable_servers_only() -> None:
    records = [
        record("a", "green"),
        record("b", "orange"),
        record("c", "gray", gray_case="incomplete_tracking"),
        record("d", "gray", gray_case="incomplete_tracking"),
        record("e", "gray", gray_case="no_tools_found"),
        record("go", "gray", gray_case="unsupported_language"),
        record("down", None, outcome=bench.NETWORK_FAILURE, error_code="fetch.network_error"),
    ]
    summary = bench.summarize(records)
    assert summary["counts"] == {"green": 1, "orange": 1, "red": 0, "gray": 4}
    assert summary["analyzable"] == 5
    assert summary["clear"] == 2
    assert summary["clear_percent"] == 40.0
    assert summary["gray_causes"][0] == {"cause": "incomplete_tracking", "count": 2}
    assert {item["cause"] for item in summary["gray_causes"]} == {
        "incomplete_tracking",
        "no_tools_found",
        "unsupported_language",
    }
    assert summary["failures"] == [{"id": "down", "outcome": bench.NETWORK_FAILURE, "error_code": "fetch.network_error"}]


def test_an_empty_run_has_no_clear_verdict() -> None:
    assert bench.summarize([])["clear_percent"] == 0.0


def test_a_color_change_fails_and_a_new_version_does_not() -> None:
    baseline = {"servers": {"a": {"color": "green", "version": "1.0.0"}, "b": {"color": "orange", "version": "0.9.0"}}}
    comparison = bench.compare([record("a", "gray", gray_case="no_tools_found"), record("b", "orange")], baseline)
    assert comparison["color_changes"] == [{"id": "a", "before": "green", "after": "gray"}]
    assert comparison["version_changes"] == [{"id": "b", "before": "0.9.0", "after": "1.0.0"}]
    assert comparison["failed"] is True
    calm = bench.compare([record("b", "orange")], baseline)
    assert calm["failed"] is False
    assert calm["removed"] == ["a"]


def test_a_witness_with_the_wrong_color_fails_even_without_baseline() -> None:
    wrong = record("fetch", "gray", gray_case="no_tools_found", witness=True, expected="orange")
    comparison = bench.compare([wrong], None)
    assert comparison["witness_failures"] == [{"id": "fetch", "expected": "orange", "after": "gray"}]
    assert comparison["failed"] is True


def test_a_failure_apart_is_not_a_color_change() -> None:
    baseline = {"servers": {"a": {"color": "green", "version": "1.0.0"}}}
    down = record("a", None, outcome=bench.NETWORK_FAILURE, error_code="fetch.timeout")
    witness = record("fetch", None, outcome=bench.NETWORK_FAILURE, witness=True, expected="orange")
    comparison = bench.compare([down, witness], baseline)
    assert comparison["failed"] is False
    assert comparison["unverified"] == ["a", "fetch"]


def test_the_summary_never_names_a_red_server() -> None:
    baseline = {"servers": {"secret-name": {"color": "green", "version": "1.0.0"}}}
    records = [record("secret-name", "red", rules=["R05"]), record("b", "orange")]
    run = bench.build_run(records, baseline, "0.3.0", "2026-10-29T10:00:00+00:00")
    markdown = bench.render_markdown(run)
    assert "secret-name" not in markdown
    assert bench.HIDDEN_NAME in markdown
    assert "The bench fails" in markdown
    assert "secret-name" not in bench.progress_line(records[0])
    unlisted = bench.render_markdown(bench.build_run(records, {"servers": {}}, "0.3.0", "2026-10-29"))
    assert "secret-name" not in unlisted
    assert "Not in the baseline: b, 1 (name hidden" in unlisted


def test_the_summary_lists_gray_causes_and_failures() -> None:
    records = [
        record("a", "gray", gray_case="timeout", error_code="job.atelier_timeout"),
        record("down", None, outcome=bench.NETWORK_FAILURE, error_code="fetch.network_error"),
    ]
    markdown = bench.render_markdown(bench.build_run(records, None, "0.3.0", "2026-10-29"))
    assert "| timeout (job.atelier_timeout) | 1 |" in markdown
    assert "| down | network_failure | fetch.network_error |" in markdown
    assert "No baseline" in markdown


def test_the_baseline_refuses_a_red_verdict() -> None:
    run = bench.build_run([record("a", "red")], None, "0.3.0", "2026-10-29")
    with pytest.raises(ValueError, match="reviewed"):
        bench.make_baseline(run, "results.json")


def test_the_baseline_keeps_the_color_of_each_analyzed_server() -> None:
    records = [record("a", "orange"), record("down", None, outcome=bench.NETWORK_FAILURE)]
    baseline = bench.make_baseline(bench.build_run(records, None, "0.3.0", "2026-10-29"), "results.json")
    assert baseline["servers"] == {"a": {"color": "orange", "gray_case": None, "version": "1.0.0"}}
    assert baseline["engine_version"] == "0.3.0"


def test_two_runs_are_compared_side_by_side() -> None:
    before = bench.build_run([record("a", "gray", gray_case="no_tools_found"), record("b", "orange")], None, "0.2.1", "d")
    after = bench.build_run([record("a", "green"), record("b", "orange")], None, "0.3.0", "d")
    table = bench.render_comparison(before, after)
    assert "| gray | 1 | 0 |" in table
    assert "| a | gray: no_tools_found | green |" in table
    assert "| b |" not in table


@respx.mock
def test_the_run_command_writes_results_and_summary_and_fails_on_a_wrong_witness(tmp_path: Path) -> None:
    servers = tmp_path / "servers.toml"
    servers.write_text(
        '[[server]]\nid = "fetch"\ninput = "uvx mcp-server-fetch"\nlanguage = "python"\ngroup = "witness"\n'
        'why = "x"\nexpected = "orange"\nwitness = true\n',
        encoding="utf-8",
    )
    respx.post(f"{API}/api/analyses").mock(return_value=httpx.Response(202, json={"id": ANALYSIS_ID}))
    respx.get(f"{API}/api/analyses/{ANALYSIS_ID}").mock(
        return_value=httpx.Response(200, json=view("done", result("gray", "no_tools_found")))
    )
    output = tmp_path / "results.json"
    summary = tmp_path / "summary.md"
    arguments = [
        "run",
        "--api",
        API,
        "--servers",
        str(servers),
        "--baseline",
        str(tmp_path / "missing.json"),
        "--output",
        str(output),
        "--summary",
        str(summary),
    ]
    assert bench.main(arguments) == 0
    assert bench.main([*arguments, "--check"]) == 1
    run = json.loads(output.read_text(encoding="utf-8"))
    assert run["records"][0]["cause"] == "no_tools_found"
    assert run["comparison"]["witness_failures"][0]["id"] == "fetch"
    assert "Witnesses with a wrong color" in summary.read_text(encoding="utf-8")


def test_the_baseline_command_writes_the_file(tmp_path: Path) -> None:
    results = tmp_path / "results.json"
    bench.write_json(results, bench.build_run([record("a", "orange")], None, "0.3.0", "2026-10-29"))
    target = tmp_path / "baseline.json"
    assert bench.main(["baseline", str(results), "--baseline", str(target)]) == 0
    assert json.loads(target.read_text(encoding="utf-8"))["servers"]["a"]["color"] == "orange"
    assert bench.main(["baseline", str(tmp_path / "none.json"), "--baseline", str(target)]) == 2


def test_the_summary_command_prints_a_results_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    results = tmp_path / "results.json"
    bench.write_json(results, bench.build_run([record("secret-name", "red")], None, "0.2.1", "2026-10-29"))
    assert bench.main(["summary", str(results)]) == 0
    printed = capsys.readouterr().out
    assert "| 0 | 0 | 1 | 0 | 0 |" in printed
    assert "secret-name" not in printed
    assert bench.main(["summary", str(tmp_path / "none.json")]) == 2
