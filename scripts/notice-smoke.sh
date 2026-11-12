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
"$ROOT/scripts/image-commit.sh"
docker compose exec -T redacteur python -c "from mcplain_api.ai_prompts import NOTICE_PROMPT_VERSION, TRANSLATION_PROMPT_VERSION; print('prompts:', NOTICE_PROMPT_VERSION, TRANSLATION_PROMPT_VERSION)"

bench_value() {
    CURRENT="$(printenv "$1" || true)"
    if [ -n "$CURRENT" ]; then
        printf '%s' "$CURRENT"
        return
    fi
    sed -n "s/^$1=//p" .env | tail -n 1
}

BENCH_EMAIL="$(bench_value MCPLAIN_BENCH_EMAIL)"
BENCH_PASSWORD="$(bench_value MCPLAIN_BENCH_PASSWORD)"
if [ -z "$BENCH_EMAIL" ] || [ -z "$BENCH_PASSWORD" ]; then
    echo "notice-smoke: no bench account: run scripts/init-secrets.sh, then scripts/make-bench-account.sh." >&2
    exit 1
fi
ORIGIN="$(docker compose exec -T guichet printenv MCPLAIN_PUBLIC_URL)"

ASK='
import sys

import httpx
from altcha import Challenge, Payload, solve_challenge

email, password, origin, text = (sys.stdin.readline().rstrip("\n") for _ in range(4))


def solved(client):
    challenge = Challenge.from_dict(client.get("http://127.0.0.1:8000/api/altcha/challenge").json())
    solution = solve_challenge(challenge)
    if solution is None:
        sys.exit("notice-smoke: the ALTCHA challenge could not be solved")
    return Payload(challenge, solution).to_base64()


with httpx.Client(timeout=30, trust_env=False) as client:
    signed = client.post(
        "http://guichet:3100/api/auth/sign-in/email",
        json={"email": email, "password": password},
        headers={"Origin": origin, "x-altcha": solved(client)},
    )
    if signed.status_code != 200:
        sys.exit(f"notice-smoke: the bench account cannot sign in ({signed.status_code}): run scripts/make-bench-account.sh")
    cookie = "; ".join(f"{name}={value}" for name, value in client.cookies.items())
    created = client.post(
        "http://127.0.0.1:8000/api/analyses",
        json={"input": text},
        headers={"x-altcha": solved(client), "Cookie": cookie},
    )
    if created.status_code != 202:
        sys.exit(f"notice-smoke: POST /api/analyses answered {created.status_code}")
    print(created.json()["id"])
'
IDENTIFIER="$(printf '%s\n%s\n%s\n%s\n' "$BENCH_EMAIL" "$BENCH_PASSWORD" "$ORIGIN" "$INPUT" | docker compose exec -T api python -c "$ASK")"

python3 - "$API" "$INPUT" "$IDENTIFIER" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request

API, INPUT, identifier = sys.argv[1], sys.argv[2], sys.argv[3]
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


print(f"analysis {identifier} of {INPUT}, asked by the bench account with a solved ALTCHA")
for _ in range(300):
    analysis = call("GET", f"/api/analyses/{identifier}")
    if analysis["state"] in ("done", "failed", "quota_exhausted"):
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
