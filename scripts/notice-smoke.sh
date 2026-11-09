#!/bin/sh
# Real test of the AI notice, for David only: it spends real tokens (at most about 0.20 dollar).
# Never run by the tests or the CI. The key stays in .env: compose hands it to the redacteur service,
# and this script only checks that the line is filled, without ever reading its value out.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
API="${MCPLAIN_API_URL:-http://127.0.0.1:8000}"
INPUT="${1:-uvx mcp-server-fetch}"

if ! grep -Eq '^MCPLAIN_ANTHROPIC_API_KEY=.+' .env; then
    echo "notice-smoke: MCPLAIN_ANTHROPIC_API_KEY is empty in .env: nothing was sent." >&2
    exit 1
fi

docker compose up -d redacteur >/dev/null

python3 - "$API" "$INPUT" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request

API, INPUT = sys.argv[1], sys.argv[2]
WAITING = {"pending", "none"}


def call(method, path, payload=None):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(API + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f"notice-smoke: {method} {path} answered {error.code}")


created = call("POST", "/api/analyses", {"input": INPUT})
identifier = created["id"]
print(f"analysis {identifier} of {INPUT}")
for _ in range(300):
    analysis = call("GET", f"/api/analyses/{identifier}")
    if analysis["state"] in ("done", "failed"):
        break
    time.sleep(1)
print(f"state {analysis['state']}, verdict {analysis['result']['verdict']['color']}")

for kind, lang in (("notice", "fr"), ("notice", "en"), ("translation", "fr")):
    answer = call("POST", f"/api/analyses/{identifier}/{kind}", {"lang": lang})
    for _ in range(90):
        if answer["status"] not in WAITING:
            break
        time.sleep(2)
        answer = call("GET", f"/api/analyses/{identifier}/{kind}?lang={lang}")
    print(f"\n--- {kind} {lang}: status {answer['status']}, source {answer['source']}, reason {answer['reject_reason']}")
    if answer["content"] is not None:
        print(json.dumps(answer["content"], ensure_ascii=True, indent=2))
PY

echo
echo "--- tokens and cost of the last calls"
docker compose exec -T postgres psql -U mcplain -d mcplain -c \
    "SELECT kind, lang, status, reject_reason, input_tokens, output_tokens, round(cost_usd::numeric, 6) AS cost_usd, request_id FROM ai_texts ORDER BY updated_at DESC LIMIT 3"
echo "--- state and admin alerts"
docker compose exec -T postgres psql -U mcplain -d mcplain -c "SELECT paused_until, disabled_reason FROM ai_state"
docker compose exec -T postgres psql -U mcplain -d mcplain -c "SELECT code, created_at, details FROM ai_admin_alerts ORDER BY created_at DESC LIMIT 5"
