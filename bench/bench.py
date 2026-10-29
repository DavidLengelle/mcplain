"""Bench of MCPlain: analyze real MCP servers through the API of a running stack, then sum up the verdicts"""

import argparse
import json
import re
import sys
import time
import tomllib
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

BENCH_DIR = Path(__file__).resolve().parent
SERVERS_FILE = BENCH_DIR / "servers.toml"
BASELINE_FILE = BENCH_DIR / "baseline.json"
RESULTS_DIR = BENCH_DIR / "results"
ENGINE_INIT = BENCH_DIR.parent / "engine" / "src" / "mcplain" / "__init__.py"
DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_CONCURRENCY = 2
DEFAULT_TIMEOUT_SECONDS = 900.0
POLL_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_POLL_ERRORS = 5
FINISHED_STATES: frozenset[str] = frozenset({"done", "failed"})
COLORS: tuple[str, ...] = ("green", "orange", "red", "gray")
CLEAR_COLORS: frozenset[str] = frozenset({"green", "orange", "red"})
OUT_OF_SCOPE_CASES: frozenset[str] = frozenset({"unsupported_language"})
DETAILED_CASES: frozenset[str] = frozenset({"error", "timeout"})
NETWORK_ERRORS: frozenset[str] = frozenset(
    {
        "fetch.timeout",
        "fetch.network_error",
        "fetch.http_error",
        "fetch.github_rate_limited",
        "fetch.unexpected_response",
        "fetch.invalid_json",
        "job.fetch_error",
    }
)
INPUT_ERRORS: frozenset[str] = frozenset(
    {
        "fetch.not_found",
        "fetch.github_repo_not_found",
        "fetch.github_ref_not_found",
        "fetch.npm_not_found",
        "fetch.pypi_not_found",
        "fetch.pypi_no_files",
    }
)
VERDICT = "verdict"
NETWORK_FAILURE = "network_failure"
INPUT_FAILURE = "input_failure"
BENCH_TIMEOUT = "bench_timeout"
HIDDEN_NAME = "(name hidden: red verdict, see the full results)"
VERSION_PATTERN = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)


@dataclass(frozen=True)
class Server:
    """Class that describes one server of the bench list"""

    id: str
    input: str
    language: str
    group: str
    why: str
    expected: str | None = None
    witness: bool = False


def load_servers(path: Path = SERVERS_FILE) -> list[Server]:
    """Read the bench list and check that every id is unique and every expected color is known"""

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    servers = [Server(**item) for item in data.get("server", [])]
    ids = [server.id for server in servers]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise ValueError(f"duplicate server ids: {', '.join(duplicates)}")
    for server in servers:
        if server.expected is not None and server.expected not in COLORS:
            raise ValueError(f"unknown expected color for {server.id}: {server.expected}")
        if server.witness and server.expected is None:
            raise ValueError(f"witness without expected color: {server.id}")
    return servers


def engine_version(path: Path = ENGINE_INIT) -> str:
    """Return the engine version written in the repository, the one the local stack is built from"""

    match = VERSION_PATTERN.search(path.read_text(encoding="utf-8"))
    if match is None:
        return "unknown"
    return match.group(1)


def base_record(server: Server) -> dict[str, Any]:
    """Return the record of a server before its analysis"""

    return {
        "id": server.id,
        "input": server.input,
        "language": server.language,
        "group": server.group,
        "expected": server.expected,
        "witness": server.witness,
        "outcome": BENCH_TIMEOUT,
        "analysis_id": None,
        "state": None,
        "color": None,
        "gray_case": None,
        "cause": None,
        "rules": [],
        "reasons": [],
        "version": None,
        "duration_seconds": None,
        "from_cache": False,
        "error_code": None,
        "details": {},
    }


def reading_details(result: dict[str, Any]) -> dict[str, Any]:
    """Count what limited the reading of a result: tools, tracking gaps, dynamic descriptions, unread files"""

    tools = [tool for server in result.get("servers", []) for tool in server.get("tools", [])]
    counted = [tool for tool in tools if tool.get("location_kind") == "server_code"]
    gaps: Counter[str] = Counter()
    for tool in counted:
        gaps.update(set(tool.get("gaps", [])))
    servers = result.get("servers", [])
    details: dict[str, Any] = {
        "tools": len(counted),
        "tools_with_gaps": sum(1 for tool in counted if tool.get("gaps")),
        "gaps": dict(sorted(gaps.items())),
        "dynamic_descriptions": sum(1 for tool in counted if tool.get("description_is_dynamic")),
        "parse_errors": sum(len(server.get("parse_errors", [])) for server in servers),
        "skipped_files": sum(len(server.get("skipped_files", [])) for server in servers),
        "compiled_files": sum(len(server.get("compiled_files", [])) for server in servers),
        "files_analyzed": sum(server.get("files_analyzed", 0) for server in servers),
    }
    verdict = result.get("verdict") or {}
    if verdict.get("coverage") is not None:
        details["coverage"] = verdict["coverage"]
    return details


def classify(record: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    """Fill a record from the final view of an analysis: color, gray case, rules, version, or a failure apart"""

    result = view.get("result") or {}
    verdict = result.get("verdict") or {}
    error = result.get("error") or {}
    source = result.get("source") or {}
    record["analysis_id"] = view.get("id")
    record["state"] = view.get("state")
    record["from_cache"] = bool(view.get("from_cache"))
    record["error_code"] = error.get("code") or view.get("error_code")
    record["version"] = source.get("version")
    record["color"] = verdict.get("color")
    record["gray_case"] = verdict.get("gray_case")
    record["reasons"] = list(verdict.get("reasons", []))
    record["rules"] = sorted({alert["rule"] for alert in verdict.get("alerts", [])})
    record["details"] = reading_details(result)
    code = record["error_code"]
    if code in NETWORK_ERRORS:
        record["outcome"] = NETWORK_FAILURE
    elif code in INPUT_ERRORS:
        record["outcome"] = INPUT_FAILURE
    elif record["color"] in COLORS:
        record["outcome"] = VERDICT
    else:
        record["outcome"] = NETWORK_FAILURE
        record["error_code"] = code or "bench.unreadable_view"
    if record["outcome"] == VERDICT and record["color"] == "gray":
        record["cause"] = gray_cause(record)
    return record


def gray_cause(record: dict[str, Any]) -> str:
    """Return the cause of a gray verdict, with the error code when the case alone says too little"""

    case = record["gray_case"] or "unknown"
    if case in DETAILED_CASES and record["error_code"]:
        return f"{case} ({record['error_code']})"
    return case


def analyze_one(
    client: httpx.Client,
    server: Server,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    poll: float = POLL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Ask the API for one analysis, wait for its end, and return its record"""

    record = base_record(server)
    started = clock()
    try:
        answer = client.post("/api/analyses", json={"input": server.input})
    except httpx.HTTPError:
        record["outcome"] = NETWORK_FAILURE
        record["error_code"] = "bench.api_unreachable"
        return record
    if answer.status_code != 202:
        record["outcome"] = INPUT_FAILURE
        if answer.status_code >= 500:
            record["outcome"] = NETWORK_FAILURE
        record["error_code"] = error_code_of(answer)
        return record
    identifier = answer.json()["id"]
    record["analysis_id"] = identifier
    errors = 0
    while clock() - started < timeout:
        try:
            view_answer = client.get(f"/api/analyses/{identifier}")
            view_answer.raise_for_status()
            view = view_answer.json()
        except (httpx.HTTPError, ValueError):
            errors += 1
            if errors >= MAX_POLL_ERRORS:
                record["outcome"] = NETWORK_FAILURE
                record["error_code"] = "bench.api_unreachable"
                return record
            sleep(poll)
            continue
        if view.get("state") in FINISHED_STATES:
            classify(record, view)
            record["duration_seconds"] = round(clock() - started, 1)
            return record
        sleep(poll)
    record["outcome"] = BENCH_TIMEOUT
    record["error_code"] = "bench.timeout"
    return record


def error_code_of(answer: httpx.Response) -> str:
    """Return the error code of an API answer, or its HTTP status when it has none"""

    try:
        return str(answer.json()["error"]["code"])
    except (ValueError, KeyError, TypeError):
        return f"http.{answer.status_code}"


def run_bench(
    servers: list[Server],
    api_url: str = DEFAULT_API_URL,
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    poll: float = POLL_SECONDS,
    report: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Analyze every server, a few at a time, and return the records in list order"""

    with httpx.Client(base_url=api_url, timeout=REQUEST_TIMEOUT_SECONDS) as client:

        def one(server: Server) -> dict[str, Any]:
            """Analyze one server and report its record"""

            record = analyze_one(client, server, timeout=timeout, poll=poll)
            if report is not None:
                report(record)
            return record

        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            return list(pool.map(one, servers))


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Count the colors, the share of clear verdicts on analyzable servers, the gray causes and the failures"""

    verdicts = [record for record in records if record["outcome"] == VERDICT]
    counts = {color: sum(1 for record in verdicts if record["color"] == color) for color in COLORS}
    analyzable = [record for record in verdicts if record["gray_case"] not in OUT_OF_SCOPE_CASES]
    clear = [record for record in analyzable if record["color"] in CLEAR_COLORS]
    percent = 0.0
    if analyzable:
        percent = round(100 * len(clear) / len(analyzable), 1)
    causes = Counter(record["cause"] for record in verdicts if record["color"] == "gray")
    return {
        "servers": len(records),
        "counts": counts,
        "analyzable": len(analyzable),
        "clear": len(clear),
        "clear_percent": percent,
        "gray_causes": [{"cause": cause, "count": count} for cause, count in causes.most_common()],
        "failures": [
            {"id": record["id"], "outcome": record["outcome"], "error_code": record["error_code"]}
            for record in records
            if record["outcome"] != VERDICT
        ],
    }


def compare(records: list[dict[str, Any]], baseline: dict[str, Any] | None) -> dict[str, Any]:
    """Compare a run with the baseline colors and the witnesses; any color change or wrong witness fails"""

    reference = {}
    if baseline is not None:
        reference = baseline.get("servers", {})
    color_changes = []
    version_changes = []
    witness_failures = []
    unverified = []
    for record in records:
        known = reference.get(record["id"])
        if record["outcome"] != VERDICT:
            if known is not None or record["witness"]:
                unverified.append(record["id"])
            continue
        if known is not None and known.get("color") != record["color"]:
            color_changes.append({"id": record["id"], "before": known.get("color"), "after": record["color"]})
        if known is not None and known.get("version") != record["version"]:
            version_changes.append({"id": record["id"], "before": known.get("version"), "after": record["version"]})
        if record["witness"] and record["color"] != record["expected"]:
            witness_failures.append({"id": record["id"], "expected": record["expected"], "after": record["color"]})
    ids = {record["id"] for record in records}
    return {
        "baseline": baseline is not None,
        "color_changes": color_changes,
        "version_changes": version_changes,
        "witness_failures": witness_failures,
        "unverified": unverified,
        "new": sorted(ids - set(reference)),
        "removed": sorted(set(reference) - ids),
        "failed": bool(color_changes or witness_failures),
    }


def red_ids(records: list[dict[str, Any]]) -> set[str]:
    """Return the ids of the servers that got a red verdict"""

    return {record["id"] for record in records if record["outcome"] == VERDICT and record["color"] == "red"}


def shown_name(server_id: str, hidden: set[str]) -> str:
    """Return a server id, or a placeholder when its verdict is red"""

    if server_id in hidden:
        return HIDDEN_NAME
    return server_id


def shown_names(server_ids: list[str], hidden: set[str]) -> str:
    """Return a list of server ids for a summary, with the red ones counted but not named"""

    names = [item for item in server_ids if item not in hidden]
    count = len(server_ids) - len(names)
    if count:
        names.append(f"{count} {HIDDEN_NAME}")
    return ", ".join(names) or "none"


def render_markdown(run: dict[str, Any]) -> str:
    """Write the summary of a run in Markdown; the name of a red server is never written"""

    summary = run["summary"]
    comparison = run["comparison"]
    hidden = red_ids(run["records"])
    counts = summary["counts"]
    lines = [
        f"## MCPlain bench, engine {run['engine_version']}, {run['date']}",
        "",
        f"Servers: {summary['servers']}. Analyzable: {summary['analyzable']}. "
        f"Clear verdicts (green, orange or red): {summary['clear']} ({summary['clear_percent']} %).",
        "",
        "| Green | Orange | Red | Gray | Failures apart |",
        "| --- | --- | --- | --- | --- |",
        f"| {counts['green']} | {counts['orange']} | {counts['red']} | {counts['gray']} | {len(summary['failures'])} |",
        "",
    ]
    if summary["gray_causes"]:
        lines.extend(["### Gray causes", "", "| Cause | Servers |", "| --- | --- |"])
        lines.extend(f"| {item['cause']} | {item['count']} |" for item in summary["gray_causes"])
        lines.append("")
    if summary["failures"]:
        lines.extend(["### Failures apart (not a gray of the engine)", "", "| Server | Outcome | Code |", "| --- | --- | --- |"])
        lines.extend(
            f"| {shown_name(item['id'], hidden)} | {item['outcome']} | {item['error_code']} |" for item in summary["failures"]
        )
        lines.append("")
    lines.extend(comparison_lines(comparison, hidden))
    return "\n".join(lines).rstrip() + "\n"


def comparison_lines(comparison: dict[str, Any], hidden: set[str]) -> list[str]:
    """Write the comparison with the baseline and the witnesses"""

    if not comparison["baseline"]:
        lines = ["### Baseline", "", "No baseline: colors were not compared.", ""]
    elif comparison["color_changes"]:
        lines = ["### Color changes", "", "| Server | Baseline | Now |", "| --- | --- | --- |"]
        lines.extend(
            f"| {shown_name(item['id'], hidden)} | {item['before']} | {item['after']} |"
            for item in comparison["color_changes"]
        )
        lines.append("")
    else:
        lines = ["### Baseline", "", "No color change.", ""]
    if comparison["witness_failures"]:
        lines.extend(["### Witnesses with a wrong color", "", "| Witness | Expected | Now |", "| --- | --- | --- |"])
        lines.extend(
            f"| {shown_name(item['id'], hidden)} | {item['expected']} | {item['after']} |"
            for item in comparison["witness_failures"]
        )
        lines.append("")
    if comparison["version_changes"]:
        lines.extend(["### New versions", "", "| Server | Baseline | Now |", "| --- | --- | --- |"])
        lines.extend(
            f"| {shown_name(item['id'], hidden)} | {item['before']} | {item['after']} |"
            for item in comparison["version_changes"]
        )
        lines.append("")
    if comparison["unverified"]:
        lines.extend(["### Not verified (failure apart)", "", shown_names(comparison["unverified"], hidden), ""])
    if comparison["baseline"] and (comparison["new"] or comparison["removed"]):
        lines.extend(
            [
                "### List changes",
                "",
                f"Not in the baseline: {shown_names(comparison['new'], hidden)}. "
                f"Gone from the list: {shown_names(comparison['removed'], hidden)}.",
                "",
            ]
        )
    if comparison["failed"]:
        lines.extend(["**The bench fails: a color changed or a witness is wrong. Check before updating the baseline.**", ""])
    return lines


def build_run(records: list[dict[str, Any]], baseline: dict[str, Any] | None, version: str, date: str) -> dict[str, Any]:
    """Gather the records, the summary and the comparison of a run"""

    return {
        "date": date,
        "engine_version": version,
        "records": records,
        "summary": summarize(records),
        "comparison": compare(records, baseline),
    }


def make_baseline(run: dict[str, Any], source: str) -> dict[str, Any]:
    """Build the baseline from a run; a red verdict waits for a human review and a timeout is no color: both stay out"""

    kept = [
        record
        for record in run["records"]
        if record["outcome"] == VERDICT and record["color"] != "red" and record["gray_case"] not in DETAILED_CASES
    ]
    servers = {
        record["id"]: {"color": record["color"], "gray_case": record["gray_case"], "version": record["version"]}
        for record in kept
    }
    return {
        "engine_version": run["engine_version"],
        "date": run["date"],
        "source": source,
        "left_out": len(run["records"]) - len(kept),
        "servers": servers,
    }


def read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON file, or return None when it does not exist"""

    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write a JSON file with a stable layout"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def progress_line(record: dict[str, Any]) -> str:
    """Return one short line about a finished server, without the name of a red one"""

    name = record["id"]
    if record["color"] == "red" and record["outcome"] == VERDICT:
        name = HIDDEN_NAME
    state = record["color"] or record["outcome"]
    if record["cause"]:
        state = f"{state}: {record['cause']}"
    elif record["outcome"] != VERDICT:
        state = f"{state}: {record['error_code']}"
    return f"{name}: {state} ({record['duration_seconds']} s)"


def command_run(arguments: argparse.Namespace) -> int:
    """Run the bench, write the full results and the summary, and tell whether the check passes"""

    servers = load_servers(Path(arguments.servers))
    if arguments.only:
        wanted = set(arguments.only.split(","))
        servers = [server for server in servers if server.id in wanted]
    version = engine_version()
    now = datetime.now(UTC)
    date = now.strftime("%Y-%m-%d")
    records = run_bench(
        servers,
        api_url=arguments.api,
        concurrency=arguments.concurrency,
        timeout=arguments.timeout,
        report=lambda record: print(progress_line(record), flush=True),
    )
    baseline = read_json(Path(arguments.baseline))
    run = build_run(records, baseline, version, now.isoformat(timespec="seconds"))
    output = Path(arguments.output or RESULTS_DIR / f"{date}-engine-{version}.json")
    write_json(output, run)
    markdown = render_markdown(run)
    print(markdown)
    if arguments.summary:
        with Path(arguments.summary).open("a", encoding="utf-8") as handle:
            handle.write(markdown)
    print(f"Full results: {output}")
    if arguments.check and run["comparison"]["failed"]:
        return 1
    return 0


def command_baseline(arguments: argparse.Namespace) -> int:
    """Write the baseline from a results file"""

    run = read_json(Path(arguments.results))
    if run is None:
        print(f"No results file: {arguments.results}", file=sys.stderr)
        return 2
    baseline = make_baseline(run, Path(arguments.results).name)
    write_json(Path(arguments.baseline), baseline)
    print(f"Baseline written: {arguments.baseline} ({len(baseline['servers'])} servers, {baseline['left_out']} left out)")
    return 0


def command_summary(arguments: argparse.Namespace) -> int:
    """Print the Markdown summary of a results file, without the name of a red server"""

    run = read_json(Path(arguments.results))
    if run is None:
        print(f"No results file: {arguments.results}", file=sys.stderr)
        return 2
    print(render_markdown(run), end="")
    return 0


def command_compare(arguments: argparse.Namespace) -> int:
    """Print the counts of two results files side by side, then the servers whose color changed"""

    before = read_json(Path(arguments.before))
    after = read_json(Path(arguments.after))
    if before is None or after is None:
        print("Both results files must exist", file=sys.stderr)
        return 2
    print(render_comparison(before, after))
    return 0


def render_comparison(before: dict[str, Any], after: dict[str, Any]) -> str:
    """Write two runs side by side in Markdown, without the name of a red server"""

    hidden = red_ids(before["records"]) | red_ids(after["records"])
    left = before["summary"]
    right = after["summary"]
    lines = [
        f"| | Engine {before['engine_version']} | Engine {after['engine_version']} |",
        "| --- | --- | --- |",
    ]
    for color in COLORS:
        lines.append(f"| {color} | {left['counts'][color]} | {right['counts'][color]} |")
    lines.append(f"| failures apart | {len(left['failures'])} | {len(right['failures'])} |")
    lines.append(f"| clear verdicts | {left['clear_percent']} % | {right['clear_percent']} % |")
    lines.extend(["", "| Server | Before | After |", "| --- | --- | --- |"])
    previous = {record["id"]: record for record in before["records"]}
    for record in after["records"]:
        old = previous.get(record["id"])
        if old is None:
            continue
        old_state = describe(old)
        new_state = describe(record)
        if old_state != new_state:
            lines.append(f"| {shown_name(record['id'], hidden)} | {old_state} | {new_state} |")
    return "\n".join(lines) + "\n"


def describe(record: dict[str, Any]) -> str:
    """Return the color of a record and its gray cause, or its failure"""

    if record["outcome"] != VERDICT:
        return f"{record['outcome']} ({record['error_code']})"
    if record["cause"]:
        return f"gray: {record['cause']}"
    return record["color"]


def parser() -> argparse.ArgumentParser:
    """Build the command line parser"""

    main = argparse.ArgumentParser(description="Bench of MCPlain on real MCP servers")
    commands = main.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="analyze every server of the list through the API")
    run.add_argument("--api", default=DEFAULT_API_URL)
    run.add_argument("--servers", default=str(SERVERS_FILE))
    run.add_argument("--baseline", default=str(BASELINE_FILE))
    run.add_argument("--only", default="")
    run.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    run.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    run.add_argument("--output", default="")
    run.add_argument("--summary", default="")
    run.add_argument("--check", action="store_true")
    run.set_defaults(handler=command_run)
    baseline = commands.add_parser("baseline", help="write the baseline from a results file")
    baseline.add_argument("results")
    baseline.add_argument("--baseline", default=str(BASELINE_FILE))
    baseline.set_defaults(handler=command_baseline)
    summary = commands.add_parser("summary", help="print the summary of a results file")
    summary.add_argument("results")
    summary.set_defaults(handler=command_summary)
    versus = commands.add_parser("compare", help="compare two results files")
    versus.add_argument("before")
    versus.add_argument("after")
    versus.set_defaults(handler=command_compare)
    return main


def main(argv: list[str] | None = None) -> int:
    """Run one command of the bench"""

    arguments = parser().parse_args(argv)
    return arguments.handler(arguments)


if __name__ == "__main__":
    sys.exit(main())
