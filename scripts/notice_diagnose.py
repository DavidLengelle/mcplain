"""Diagnosis of the French notice, run by scripts/notice-diagnose.sh only: real calls, nothing written anywhere"""

import copy
import hashlib
import json
import os
import sys
import unicodedata
from collections.abc import Callable
from typing import Any

from mcplain.models import AnalysisResult

from mcplain_api.ai_check import MOJIBAKE_PATTERN, OutputRejected, check_notice
from mcplain_api.ai_client import Reply, call_api, call_cost, notice_body
from mcplain_api.ai_form import build_form
from mcplain_api.ai_prompts import NOTICE_PROMPT_VERSION, NOTICE_SCHEMA, NOTICE_SYSTEM
from mcplain_api.settings import Settings

REPEATS = 3
AROUND = 20
FORBIDDEN_LIST = (
    ' (no "safe", "secure", "sûr", "sécurisé", "fiable", "vérifié", "garanti", "officiel", "de confiance")'
)
CURRENT_JSON_PARAGRAPH = "\n\nAnswer with this JSON object only"
OLD_B_SENTENCE = (
    "\n\nAnswer with one JSON object only, without Markdown, with exactly these fields: "
    + json.dumps(NOTICE_SCHEMA, ensure_ascii=True)
)
OLD_B_SYSTEM_SHA256 = "0193a444ab9e5ea7731c01b95c8f2e6a03638a0b7f670a9433835ba7e2a5210e"


def without_forbidden_list(body: dict[str, Any]) -> dict[str, Any]:
    """V2: the current request without the list of forbidden words in the system prompt"""

    if FORBIDDEN_LIST not in body["system"]:
        raise SystemExit("notice-diagnose: the forbidden word list is no longer in the prompt, update the script")
    changed = copy.deepcopy(body)
    changed["system"] = body["system"].replace(FORBIDDEN_LIST, "")
    return changed


def with_medium_effort(body: dict[str, Any]) -> dict[str, Any]:
    """V3: the current request with effort medium"""

    changed = copy.deepcopy(body)
    changed["output_config"]["effort"] = "medium"
    return changed


def without_thinking(body: dict[str, Any]) -> dict[str, Any]:
    """V4: the current request without the thinking field, so adaptive thinking"""

    changed = copy.deepcopy(body)
    del changed["thinking"]
    return changed


def old_mode_b(body: dict[str, Any]) -> dict[str, Any]:
    """V5: the request of the former mode B, exactly: the notice-v2 prompt, its JSON sentence, no format"""

    changed = copy.deepcopy(body)
    changed["system"] = NOTICE_SYSTEM.split(CURRENT_JSON_PARAGRAPH)[0] + OLD_B_SENTENCE
    if hashlib.sha256(changed["system"].encode("utf-8")).hexdigest() != OLD_B_SYSTEM_SHA256:
        raise SystemExit("notice-diagnose: the prompt changed, mode B can no longer be rebuilt exactly")
    return changed


VARIANTS: tuple[tuple[str, Callable[[dict[str, Any]], dict[str, Any]]], ...] = (
    ("V1 current request", lambda body: copy.deepcopy(body)),
    ("V2 without the forbidden word list", without_forbidden_list),
    ("V3 effort medium", with_medium_effort),
    ("V4 without thinking (adaptive)", without_thinking),
    ("V5 former mode B", old_mode_b),
)


def first_break(text: str) -> str | None:
    """Return the 40 characters around the first broken sequence, escaped, or None"""

    found = MOJIBAKE_PATTERN.search(text)
    if found is None:
        return None
    return text[max(0, found.start() - AROUND) : found.start() + AROUND].encode("unicode_escape").decode("ascii")


def load_settings(env_file: str) -> Settings:
    """Read the AI settings and the key from .env, without ever printing them"""

    for line in open(env_file, encoding="utf-8"):
        name, sep, value = line.strip().partition("=")
        if sep and (name == "MCPLAIN_ANTHROPIC_API_KEY" or name.startswith("MCPLAIN_AI_")):
            os.environ[name] = value.strip().strip("'\"")
    return Settings(_env_file=None, database_url="sqlite://")


def single(settings: Settings, form: dict[str, Any], with_format: bool, hide: Callable[[str], str]) -> None:
    """Send the notice once and show everything about the answer"""

    body = notice_body(settings, form, "fr", with_format=with_format)
    print(f"output_config {sorted(body['output_config'])}")
    reply = call_api(settings, body)
    print(f"result {reply.kind.value}, HTTP {reply.status}, stop_reason {reply.stop_reason}, request-id {reply.request_id}")
    print("--- raw text")
    print(hide(reply.text))
    print("--- non-ASCII characters")
    for index, character in enumerate(reply.text):
        if ord(character) > 127:
            around = reply.text[max(0, index - 12) : index + 4].encode("unicode_escape").decode("ascii")
            print(f"  {index:5} U+{ord(character):04X} {unicodedata.name(character, '?'):40} {around}")
    print("--- check of the writer")
    try:
        check_notice(reply.text, form)
        print("accepted")
    except OutputRejected as rejected:
        print(f"rejected: {rejected.reason.value}")
    cost = call_cost(settings, reply.input_tokens, reply.output_tokens)
    print(f"--- tokens in {reply.input_tokens}, out {reply.output_tokens}, cost {cost:.6f} USD")


def matrix(settings: Settings, form: dict[str, Any], hide: Callable[[str], str]) -> None:
    """Send each variant three times and print a table"""

    base = notice_body(settings, form, "fr")
    rows = []
    total = 0.0
    for label, make in VARIANTS:
        body = make(base)
        replies: list[Reply] = []
        broken = 0
        for attempt in range(1, REPEATS + 1):
            reply = call_api(settings, body)
            replies.append(reply)
            total += call_cost(settings, reply.input_tokens, reply.output_tokens)
            place = first_break(reply.text)
            status = f"HTTP {reply.status}, stop_reason {reply.stop_reason}, request-id {reply.request_id}"
            if place is not None:
                broken += 1
                print(f"{label}, try {attempt}: BROKEN ({status}): {hide(place)}")
            else:
                print(f"{label}, try {attempt}: clean ({status})")
        tokens_in = sum(reply.input_tokens for reply in replies) / REPEATS
        tokens_out = sum(reply.output_tokens for reply in replies) / REPEATS
        cost = sum(call_cost(settings, reply.input_tokens, reply.output_tokens) for reply in replies) / REPEATS
        rows.append((label, broken, tokens_in, tokens_out, cost))
    print(f"\n{'variant':38} {'broken':>7} {'in':>7} {'out':>7} {'cost USD':>10}")
    for label, broken, tokens_in, tokens_out, cost in rows:
        print(f"{label:38} {broken:>4}/{REPEATS} {tokens_in:>7.0f} {tokens_out:>7.0f} {cost:>10.6f}")
    print(f"total {total:.6f} USD")


def main() -> int:
    """Run one mode: current, with-format or matrix"""

    env_file, report, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    settings = load_settings(env_file)
    key = settings.anthropic_api_key.get_secret_value()

    def hide(text: str) -> str:
        """Remove the key from a text before printing it"""

        return text.replace(key, "[hidden]")

    form = build_form(AnalysisResult.model_validate(json.load(open(report, encoding="utf-8"))))
    print(f"mode {mode}, model {settings.ai_model}, prompt {NOTICE_PROMPT_VERSION}")
    if mode == "matrix":
        matrix(settings, form, hide)
    else:
        single(settings, form, mode == "with-format", hide)
    return 0


if __name__ == "__main__":
    sys.exit(main())
