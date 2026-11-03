"""Tests of the study of the orange verdicts, on invented records"""

import json
from pathlib import Path
from typing import Any

import httpx
import respx

import oranges
from bench import NETWORK_FAILURE, VERDICT

API = "http://api.test"


def lamps(*lit: str) -> list[dict[str, str]]:
    """Return the six lamps with the given ones on"""

    return [{"id": lamp, "state": "on" if lamp in lit else "off"} for lamp in oranges.LAMP_NAMES]


def record(
    identifier: str,
    color: str,
    rules: list[str],
    reasons: list[str] | None = None,
    lit: tuple[str, ...] = (),
    outcome: str = VERDICT,
) -> dict[str, Any]:
    """Return a finished record with its rules, reasons and lamps"""

    return {
        "id": identifier,
        "color": color,
        "rules": rules,
        "reasons": reasons or [],
        "outcome": outcome,
        "analysis_id": None,
        "lamps": lamps(*lit),
    }


RECORDS = [
    record("only-o08", "orange", ["O08"], lit=("files_write",)),
    record("o08-o01", "orange", ["O01", "O08"], lit=("internet", "files_write", "commands")),
    record("o02", "orange", ["O02", "O08"], lit=("commands",)),
    record("o06", "orange", ["O06"]),
    record("o05", "orange", ["O05", "O08"], lit=("secrets",)),
    record("o08-partial", "orange", ["O08"], reasons=["caveat.incomplete_tracking"], lit=("commands",)),
    record("green", "green", [], reasons=["no_alert"]),
    record("red", "red", ["O08", "R04"], lit=("internet", "secrets")),
    record("red-o06", "red", ["O06", "R12"]),
    record("gray", "gray", [], reasons=["caveat.no_tools_found"]),
    record("down", None, [], outcome=NETWORK_FAILURE),
]


def test_rule_counts_and_power_only_verdicts() -> None:
    assert oranges.rule_counts(RECORDS) == [("O08", 5), ("O01", 1), ("O02", 1), ("O05", 1), ("O06", 1)]
    assert oranges.only_because(RECORDS, frozenset({"O08"})) == 2
    assert oranges.only_because(RECORDS, frozenset({"O08", "O01"})) == 3
    assert oranges.only_because(RECORDS, frozenset({"O01", "O02", "O08"})) == 4


def test_the_simulation_keeps_reds_grays_and_reading_in_part() -> None:
    assert oranges.color_counts(RECORDS, None) == {"green": 1, "orange": 6, "red": 2, "gray": 1}
    assert oranges.color_counts(RECORDS, oranges.PROPOSAL) == {"green": 3, "orange": 3, "red": 2, "gray": 2}
    assert oranges.color_counts(RECORDS, oranges.PROPOSAL_WITH_O05) == {"green": 4, "orange": 2, "red": 2, "gray": 2}


def test_a_red_without_its_red_rule() -> None:
    red = RECORDS[7]
    assert oranges.color_without(red, frozenset({"R04"})) == "orange"
    assert oranges.color_without(red, frozenset({"R04"}) | oranges.PROPOSAL) == "green"
    assert oranges.color_without(RECORDS[8], frozenset({"R12"}) | oranges.PROPOSAL) == "orange"


def test_the_caution_check_finds_greens_with_many_or_risky_lamps() -> None:
    caution = [item["id"] for item in RECORDS if oranges.needs_caution(item, oranges.PROPOSAL)]
    assert caution == ["o08-o01"]
    with_o05 = [item["id"] for item in RECORDS if oranges.needs_caution(item, oranges.PROPOSAL_WITH_O05)]
    assert with_o05 == ["o08-o01", "o05"]


@respx.mock
def test_the_command_reads_stored_lamps_and_keeps_names_private(tmp_path: Path, capsys: Any) -> None:
    stored = record("secret-name", "orange", ["O08"])
    del stored["lamps"]
    stored["analysis_id"] = "00000000-0000-4000-8000-000000000002"
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"records": [stored]}), encoding="utf-8")
    view = {"result": {"servers": [{"lamps": lamps("commands")}]}}
    route = respx.get(f"{API}/api/analyses/{stored['analysis_id']}").mock(return_value=httpx.Response(200, json=view))
    report = tmp_path / "private" / "oranges.md"
    assert oranges.main([str(results), "--api", API, "--report", str(report)]) == 0
    assert route.call_count == 1
    printed = capsys.readouterr().out
    assert "secret-name" not in printed
    assert "Contrôle de prudence : 1" in printed
    text = report.read_text(encoding="utf-8")
    assert "| secret-name | O08 (pouvoir) | Lance des commandes |" in text
    assert "- secret-name : Lance des commandes" in text


def test_new_orange_rules_are_to_be_sorted_and_keep_their_color() -> None:
    """O09, O10, O11 and an unknown orange rule belong to no family yet, and the simulation keeps them orange"""

    for rule in ("O09", "O10", "O11", "O99"):
        assert oranges.family(rule) == oranges.UNSORTED
        assert oranges.simulated(record("x", "orange", ["O08", rule]), oranges.PROPOSAL) == "orange"
    report = oranges.private_report([record("x", "orange", ["O10"])], oranges.summary([record("x", "orange", ["O10"])]), "r")
    assert "| O10 | à classer | 1 |" in report
