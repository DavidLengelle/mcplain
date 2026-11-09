#!/bin/sh
# Diagnosis of the broken French notice, for David only: two real calls, about 1.2 cent in all.
# A: the real notice request, with output_config.format. B: the same without format, the prompt asking for JSON.
# Nothing is written in the database nor in the cache, and nothing counts in the fuse: the calls go straight to the API.
# The key is read from .env by Python and only ever put in the request header.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
INPUT="${1:-uvx mcp-server-fetch}"

if ! grep -Eq '^MCPLAIN_ANTHROPIC_API_KEY=.+' .env; then
    echo "notice-diagnose: MCPLAIN_ANTHROPIC_API_KEY is empty in .env: nothing was sent." >&2
    exit 1
fi

REPORT="$(mktemp)"
trap 'rm -f "$REPORT"' EXIT
echo "SELECT result FROM analyses WHERE input_raw = :'input' AND state = 'done' ORDER BY finished_at DESC LIMIT 1;" \
    | docker compose exec -T postgres psql -U mcplain -d mcplain -t -A -q -v input="$INPUT" > "$REPORT"
if [ ! -s "$REPORT" ]; then
    echo "notice-diagnose: no finished analysis of $INPUT in the database. Run scripts/notice-smoke.sh first." >&2
    exit 1
fi

cd api
uv run --locked python - "$ROOT/.env" "$REPORT" <<'PY'
import json
import os
import sys
import unicodedata

ENV_FILE, REPORT = sys.argv[1], sys.argv[2]
for line in open(ENV_FILE, encoding="utf-8"):
    name, sep, value = line.strip().partition("=")
    if sep and (name == "MCPLAIN_ANTHROPIC_API_KEY" or name.startswith("MCPLAIN_AI_")):
        os.environ[name] = value.strip().strip("'\"")

from mcplain.models import AnalysisResult
from mcplain_api.ai_client import build_body, call_api, call_cost
from mcplain_api.ai_form import build_form
from mcplain_api.ai_prompts import NOTICE_PROMPT_VERSION, NOTICE_SCHEMA, NOTICE_SYSTEM, notice_message
from mcplain_api.settings import Settings

settings = Settings(_env_file=None, database_url="sqlite://")
KEY = settings.anthropic_api_key.get_secret_value()
form = build_form(AnalysisResult.model_validate(json.load(open(REPORT, encoding="utf-8"))))
message = notice_message(form, "fr")
JSON_ONLY = (
    "\n\nAnswer with one JSON object only, without Markdown, with exactly these fields: "
    + json.dumps(NOTICE_SCHEMA, ensure_ascii=True)
)
with_format = build_body(settings, NOTICE_SYSTEM, message, NOTICE_SCHEMA, settings.ai_max_tokens)
without_format = build_body(settings, NOTICE_SYSTEM + JSON_ONLY, message, NOTICE_SCHEMA, settings.ai_max_tokens)
without_format["output_config"] = {"effort": settings.ai_effort}
print(f"model {settings.ai_model}, prompt {NOTICE_PROMPT_VERSION}, effort {settings.ai_effort}, thinking {settings.ai_thinking}")


def clean(text: str) -> str:
    return text.replace(KEY, "[hidden]")


total = 0.0
for label, body in (("A, with output_config.format", with_format), ("B, without format, JSON asked in the prompt", without_format)):
    reply = call_api(settings, body)
    cost = call_cost(settings, reply.input_tokens, reply.output_tokens)
    total += cost
    print(f"\n===== {label}")
    print(f"result {reply.kind.value}, HTTP {reply.status}, stop_reason {reply.stop_reason}, request-id {reply.request_id}")
    print("--- raw text")
    print(clean(reply.text))
    print("--- non-ASCII characters")
    for index, character in enumerate(reply.text):
        if ord(character) > 127:
            around = reply.text[max(0, index - 12):index + 4].encode("unicode_escape").decode("ascii")
            print(f"  {index:5} U+{ord(character):04X} {unicodedata.name(character, '?'):40} {around}")
    print(f"--- tokens in {reply.input_tokens}, out {reply.output_tokens}, cost {cost:.6f} USD")
print(f"\ntotal {total:.6f} USD")
PY
