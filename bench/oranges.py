"""Where the orange verdicts come from: rule families, counts and a simulation of a proposal, from a bench results file"""

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from bench import DEFAULT_API_URL, VERDICT, read_json

BENCH_DIR = Path(__file__).resolve().parent
PRIVATE_REPORT = BENCH_DIR / "private" / "oranges.md"
POWER = "power"
ANOMALY = "anomaly"
UNSORTED = "unsorted"
FAMILIES: dict[str, str] = {
    "O01": POWER,
    "O02": POWER,
    "O08": POWER,
    "O03": ANOMALY,
    "O04": ANOMALY,
    "O06": ANOMALY,
    "O07": ANOMALY,
    "O05": UNSORTED,
}
FAMILY_NAMES: dict[str, str] = {POWER: "pouvoir", ANOMALY: "anomalie", UNSORTED: "à classer"}
PROPOSAL: frozenset[str] = frozenset({"O01", "O08"})
PROPOSAL_WITH_O05: frozenset[str] = frozenset({"O01", "O08", "O05"})
READING_REASONS: frozenset[str] = frozenset(
    {
        "nothing_analyzable",
        "caveat.partially_compiled",
        "caveat.parse_errors",
        "caveat.skipped_files",
        "caveat.no_tools_found",
        "caveat.incomplete_tracking",
        "caveat.dynamic_descriptions",
        "caveat.network_unresolved",
    }
)
STATUS_PREFIX = "status."
RISKY_LAMPS: frozenset[str] = frozenset({"secrets", "commands"})
LIT_STATES: frozenset[str] = frozenset({"on", "danger"})
MANY_LAMPS = 3
COLORS: tuple[str, ...] = ("green", "orange", "red", "gray")
LAMP_NAMES: dict[str, str] = {
    "files_read": "Lit tes fichiers",
    "files_write": "Modifie tes fichiers",
    "internet": "Va sur Internet",
    "commands": "Lance des commandes",
    "secrets": "Touche à tes secrets",
    "hidden_text": "Texte caché",
}


def orange_rules(record: dict[str, Any]) -> list[str]:
    """Return the orange rule codes of a record"""

    return sorted(rule for rule in record["rules"] if rule.startswith("O"))


def red_rules(record: dict[str, Any]) -> list[str]:
    """Return the red rule codes of a record"""

    return sorted(rule for rule in record["rules"] if rule.startswith("R"))


def read_in_part(record: dict[str, Any]) -> bool:
    """Tell whether the engine kept the record from green because the code was not read and followed in full"""

    return any(reason in READING_REASONS or reason.startswith(STATUS_PREFIX) for reason in record["reasons"])


def color_without(record: dict[str, Any], silent: frozenset[str]) -> str:
    """Return the color the verdict order gives when the silent rules no longer color, from the rule codes"""

    if record["outcome"] != VERDICT or record["color"] == "gray":
        return record["color"] or "gray"
    rules = [rule for rule in record["rules"] if rule not in silent]
    if any(rule.startswith("R") for rule in rules):
        return "red"
    if any(rule.startswith("O") for rule in rules):
        return "orange"
    if read_in_part(record):
        return "gray"
    return "green"


def simulated(record: dict[str, Any], silent: frozenset[str]) -> str:
    """Return the simulated color of a record: reds and grays stay as they are"""

    if record["color"] in ("red", "gray"):
        return record["color"]
    return color_without(record, silent)


def color_counts(records: list[dict[str, Any]], silent: frozenset[str] | None) -> dict[str, int]:
    """Count the colors of the verdicts, today when silent is None, else simulated"""

    counts = dict.fromkeys(COLORS, 0)
    for record in records:
        if record["outcome"] != VERDICT:
            continue
        color = record["color"]
        if silent is not None:
            color = simulated(record, silent)
        counts[color] += 1
    return counts


def rule_counts(records: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """Count the servers each orange rule touches, among the orange verdicts, most first"""

    counter: Counter[str] = Counter()
    for record in records:
        if record["outcome"] == VERDICT and record["color"] == "orange":
            counter.update(set(orange_rules(record)))
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def only_because(records: list[dict[str, Any]], allowed: frozenset[str]) -> int:
    """Count the orange verdicts whose every orange rule is in a set"""

    return sum(
        1
        for record in records
        if record["outcome"] == VERDICT and record["color"] == "orange" and set(orange_rules(record)) <= allowed
    )


def lit_lamps(record: dict[str, Any]) -> list[str]:
    """Return the lamps of a record that are on or in danger"""

    return [lamp["id"] for lamp in record.get("lamps", []) if lamp["state"] in LIT_STATES]


def needs_caution(record: dict[str, Any], silent: frozenset[str]) -> bool:
    """Tell whether a record would turn green with many lamps lit, or with the secrets or commands lamp lit"""

    if record["color"] == "green" or simulated(record, silent) != "green":
        return False
    lamps = lit_lamps(record)
    return len(lamps) >= MANY_LAMPS or bool(RISKY_LAMPS & set(lamps))


def add_lamps(records: list[dict[str, Any]], api_url: str) -> None:
    """Read the lamps of each finished analysis from the stored report: nothing is analyzed again"""

    with httpx.Client(base_url=api_url, timeout=30) as client:
        for record in records:
            if record.get("analysis_id") is None or "lamps" in record:
                continue
            view = client.get(f"/api/analyses/{record['analysis_id']}").json()
            servers = (view.get("result") or {}).get("servers") or []
            record["lamps"] = []
            if servers:
                record["lamps"] = [{"id": lamp["id"], "state": lamp["state"]} for lamp in servers[0].get("lamps", [])]


def summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Gather every count of the study, without any server name"""

    today = color_counts(records, None)
    return {
        "today": today,
        "proposal": color_counts(records, PROPOSAL),
        "proposal_with_o05": color_counts(records, PROPOSAL_WITH_O05),
        "rules": rule_counts(records),
        "only_o08": only_because(records, frozenset({"O08"})),
        "only_o08_o01": only_because(records, frozenset({"O08", "O01"})),
        "only_power": only_because(records, frozenset(rule for rule, family in FAMILIES.items() if family == POWER)),
        "caution": sum(1 for record in records if needs_caution(record, PROPOSAL)),
        "caution_with_o05": sum(1 for record in records if needs_caution(record, PROPOSAL_WITH_O05)),
    }


def count_table(numbers: dict[str, Any]) -> list[str]:
    """Write the today and simulated colors as a Markdown table"""

    lines = ["| | Verts | Oranges | Rouges | Gris |", "| --- | --- | --- | --- | --- |"]
    rows = [
        ("Aujourd'hui", numbers["today"]),
        ("Simulé, O05 reste orange", numbers["proposal"]),
        ("Simulé, O05 ne colore plus", numbers["proposal_with_o05"]),
    ]
    for label, counts in rows:
        lines.append(f"| {label} | {counts['green']} | {counts['orange']} | {counts['red']} | {counts['gray']} |")
    return lines


def rules_text(rules: list[str]) -> str:
    """Write rule codes with their family"""

    parts = [f"{rule} ({FAMILY_NAMES.get(FAMILIES.get(rule, ''), 'rouge')})" for rule in rules]
    return ", ".join(parts) or "aucune"


def lamps_text(record: dict[str, Any]) -> str:
    """Write the lit lamps of a record"""

    return ", ".join(LAMP_NAMES.get(lamp, lamp) for lamp in lit_lamps(record)) or "aucun"


def private_report(records: list[dict[str, Any]], numbers: dict[str, Any], source: str) -> str:
    """Write the study with the server names: only for bench/private/, never for git"""

    oranges = [record for record in records if record["outcome"] == VERDICT and record["color"] == "orange"]
    reds = [record for record in records if record["outcome"] == VERDICT and record["color"] == "red"]
    lines = [
        "# D'où viennent les oranges (fichier privé, hors de git)",
        "",
        f"Source : `{source}`. Aucune analyse n'a été relancée : les voyants viennent des rapports déjà stockés.",
        "",
        "## 1. Les serveurs orange",
        "",
        "| Serveur | Règles orange (famille) | Voyants allumés |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {record['id']} | {rules_text(orange_rules(record))} | {lamps_text(record)} |" for record in oranges)
    lines.extend(["", "## 2. Comptes", "", "| Règle | Famille | Serveurs orange touchés |", "| --- | --- | --- |"])
    lines.extend(f"| {rule} | {FAMILY_NAMES[FAMILIES[rule]]} | {count} |" for rule, count in numbers["rules"])
    lines.extend(
        [
            "",
            f"- Orange seulement à cause de O08 : {numbers['only_o08']}",
            f"- Orange seulement à cause de O08 et O01 : {numbers['only_o08_o01']}",
            f"- Orange seulement à cause de règles « pouvoir » (O01, O02, O08) : {numbers['only_power']}",
            "",
            "## 3. Simulation",
            "",
            "Proposition : O01 et O08 ne colorent plus ; O02, O03, O04, O06 et O07 restent orange ; rouges et gris "
            "inchangés. Un serveur sans règle orange restante devient vert, sauf si le moteur n'a pas tout lu ou "
            "suivi : il devient alors gris.",
            "",
        ]
    )
    lines.extend(count_table(numbers))
    lines.extend(["", "Serveurs orange qui changent de couleur :", ""])
    for record in oranges:
        proposal = simulated(record, PROPOSAL)
        with_o05 = simulated(record, PROPOSAL_WITH_O05)
        if proposal != "orange" or with_o05 != "orange":
            lines.append(f"- {record['id']} : {proposal} (O05 orange), {with_o05} (O05 sans couleur)")
    lines.extend(
        [
            "",
            "### Les rouges sans leur règle rouge",
            "",
            "| Serveur | Règles rouges | Couleur sans la règle rouge | Avec la proposition | Avec la proposition et O05 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for record in reds:
        reds_only = frozenset(red_rules(record))
        lines.append(
            f"| {record['id']} | {', '.join(red_rules(record))} | {color_without(record, reds_only)} "
            f"| {color_without(record, reds_only | PROPOSAL)} | {color_without(record, reds_only | PROPOSAL_WITH_O05)} |"
        )
    lines.extend(
        [
            "",
            "## 4. Contrôle de prudence",
            "",
            f"Serveurs qui deviendraient verts avec {MANY_LAMPS} voyants allumés ou plus, ou avec « Touche à tes "
            "secrets » ou « Lance des commandes » allumé. C'est là qu'un vert pourrait rassurer à tort.",
            "",
        ]
    )
    for silent, label in ((PROPOSAL, "O05 orange"), (PROPOSAL_WITH_O05, "O05 sans couleur")):
        caution = [record for record in records if needs_caution(record, silent)]
        lines.append(f"Avec la proposition ({label}) : {len(caution)} serveur(s).")
        lines.append("")
        lines.extend(f"- {record['id']} : {lamps_text(record)} (règles : {', '.join(record['rules'])})" for record in caution)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def public_lines(numbers: dict[str, Any]) -> list[str]:
    """Write the counts without any server name"""

    lines = count_table(numbers)
    lines.append("")
    lines.extend(f"{rule} : {count}" for rule, count in numbers["rules"])
    lines.append(
        f"Seulement O08 : {numbers['only_o08']} ; seulement O08 et O01 : {numbers['only_o08_o01']} ; "
        f"seulement « pouvoir » : {numbers['only_power']}"
    )
    lines.append(f"Contrôle de prudence : {numbers['caution']} (O05 sans couleur : {numbers['caution_with_o05']})")
    return lines


def main(argv: list[str] | None = None) -> int:
    """Study a results file and write the named report into the private folder"""

    parser = argparse.ArgumentParser(description="Where the orange verdicts come from")
    parser.add_argument("results")
    parser.add_argument("--api", default=DEFAULT_API_URL)
    parser.add_argument("--report", default=str(PRIVATE_REPORT))
    arguments = parser.parse_args(argv)
    run = read_json(Path(arguments.results))
    if run is None:
        print(f"No results file: {arguments.results}", file=sys.stderr)
        return 2
    records = run["records"]
    add_lamps(records, arguments.api)
    numbers = summary(records)
    report = Path(arguments.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(private_report(records, numbers, Path(arguments.results).name), encoding="utf-8")
    print("\n".join(public_lines(numbers)))
    print(f"Named report: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
