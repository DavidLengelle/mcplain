#!/bin/sh
# Diagnosis of the French notice, for David only: real calls.
#   scripts/notice-diagnose.sh                 the request the writer really sends (mode current), 1 call, about 0.6 cent
#   scripts/notice-diagnose.sh --with-format   the same request plus output_config.format, 1 call
#   scripts/notice-diagnose.sh --matrix        5 variants, 3 calls each, about 8 cents (see scripts/notice_diagnose.py)
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
elif [ "${1:-}" = "--matrix" ]; then
    MODE="matrix"
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
uv run --locked python "$ROOT/scripts/notice_diagnose.py" "$ROOT/.env" "$REPORT" "$MODE"
