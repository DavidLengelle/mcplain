#!/bin/sh
# Diagnosis of the French notice, for David only: one real call, about 0.6 cent.
#   scripts/notice-diagnose.sh                 the request the writer really sends (mode current)
#   scripts/notice-diagnose.sh --with-format   the same request plus output_config.format, to check the imposed output again
# A second argument names another analysis already in the database (default: uvx mcp-server-fetch).
# The request is built by the same functions as the writer (notice_body). Nothing is written in the database nor in the
# cache, and nothing counts in the fuse. The key is read from .env by Python and only ever put in the request header.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MODE="current"
if [ "${1:-}" = "--with-format" ]; then
    MODE="with-format"
    shift
elif [ "${1:-}" = "--current" ]; then
    shift
fi
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
uv run --locked python - "$ROOT/.env" "$REPORT" "$MODE" <<'PY'
import json
import os
import sys
import unicodedata

ENV_FILE, REPORT, MODE = sys.argv[1], sys.argv[2], sys.argv[3]
for line in open(ENV_FILE, encoding="utf-8"):
    name, sep, value = line.strip().partition("=")
    if sep and (name == "MCPLAIN_ANTHROPIC_API_KEY" or name.startswith("MCPLAIN_AI_")):
        os.environ[name] = value.strip().strip("'\"")

from mcplain.models import AnalysisResult
from mcplain_api.ai_check import OutputRejected, check_notice
from mcplain_api.ai_client import call_api, call_cost, notice_body
from mcplain_api.ai_form import build_form
from mcplain_api.ai_prompts import NOTICE_PROMPT_VERSION
from mcplain_api.settings import Settings

settings = Settings(_env_file=None, database_url="sqlite://")
KEY = settings.anthropic_api_key.get_secret_value()
form = build_form(AnalysisResult.model_validate(json.load(open(REPORT, encoding="utf-8"))))
body = notice_body(settings, form, "fr", with_format=MODE == "with-format")
print(f"mode {MODE}, model {settings.ai_model}, prompt {NOTICE_PROMPT_VERSION}, output_config {sorted(body['output_config'])}")


def clean(text: str) -> str:
    return text.replace(KEY, "[hidden]")


reply = call_api(settings, body)
cost = call_cost(settings, reply.input_tokens, reply.output_tokens)
print(f"result {reply.kind.value}, HTTP {reply.status}, stop_reason {reply.stop_reason}, request-id {reply.request_id}")
print("--- raw text")
print(clean(reply.text))
print("--- non-ASCII characters")
for index, character in enumerate(reply.text):
    if ord(character) > 127:
        around = reply.text[max(0, index - 12):index + 4].encode("unicode_escape").decode("ascii")
        print(f"  {index:5} U+{ord(character):04X} {unicodedata.name(character, '?'):40} {around}")
print("--- check of the writer")
try:
    check_notice(reply.text, form)
    print("accepted")
except OutputRejected as rejected:
    print(f"rejected: {rejected.reason.value}")
print(f"--- tokens in {reply.input_tokens}, out {reply.output_tokens}, cost {cost:.6f} USD")
PY
