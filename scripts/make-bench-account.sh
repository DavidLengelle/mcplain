#!/bin/sh
# For the test stacks and David's machine only, never the VPS: creates the bench account, or gives it the bench role again.
# Its email and password come from MCPLAIN_BENCH_EMAIL and MCPLAIN_BENCH_PASSWORD (environment first, then .env, written by
# scripts/init-secrets.sh). The account signs up through the counter like a browser, with an ALTCHA solved inside the api
# container; then psql, as the owner, marks its address verified and gives it the role bench. The role has no admin power, and
# the API treats it as a normal account (10 a day) unless MCPLAIN_ALLOW_BENCH_ROLE is true. An admin is never changed.
# Nothing is printed but the result: never the password. Usage: scripts/make-bench-account.sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

value_of() {
    CURRENT="$(printenv "$1" || true)"
    if [ -n "$CURRENT" ]; then
        printf '%s' "$CURRENT"
        return
    fi
    if [ -f .env ]; then
        sed -n "s/^$1=//p" .env | tail -n 1
    fi
}

EMAIL="$(value_of MCPLAIN_BENCH_EMAIL)"
PASSWORD="$(value_of MCPLAIN_BENCH_PASSWORD)"
if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
    echo "make-bench-account: MCPLAIN_BENCH_EMAIL or MCPLAIN_BENCH_PASSWORD is empty: run scripts/init-secrets.sh first." >&2
    exit 1
fi
case "$EMAIL" in
    *@*.*) ;;
    *)
        echo "make-bench-account: MCPLAIN_BENCH_EMAIL does not look like an email address." >&2
        exit 2
        ;;
esac
ORIGIN="$(docker compose exec -T guichet printenv MCPLAIN_PUBLIC_URL)"

SIGN_UP='
import sys

import httpx
from altcha import Challenge, Payload, solve_challenge

email, password, origin = (sys.stdin.readline().rstrip("\n") for _ in range(3))
with httpx.Client(timeout=30, trust_env=False) as client:
    challenge = Challenge.from_dict(client.get("http://127.0.0.1:8000/api/altcha/challenge").json())
    solution = solve_challenge(challenge)
    if solution is None:
        sys.exit("make-bench-account: the ALTCHA challenge could not be solved")
    answer = client.post(
        "http://guichet:3100/api/auth/sign-up/email",
        json={"email": email, "password": password, "name": ""},
        headers={"Origin": origin, "x-altcha": Payload(challenge, solution).to_base64(), "x-mcplain-lang": "en"},
    )
    if answer.status_code != 200:
        sys.exit(f"make-bench-account: the counter answered {answer.status_code} to the sign-up")
'

printf '%s\n%s\n%s\n' "$EMAIL" "$PASSWORD" "$ORIGIN" | docker compose exec -T api python -c "$SIGN_UP"

COUNT="$(printf '%s\n' "DELETE FROM public.mail_outbox WHERE recipient = lower(:'email'); WITH changed AS (UPDATE auth.\"user\" SET \"emailVerified\" = true, role = 'bench', \"updatedAt\" = now() WHERE email = lower(:'email') AND role <> 'admin' RETURNING 1) SELECT count(*) FROM changed;" \
    | docker compose exec -T postgres psql -U mcplain -d mcplain -v ON_ERROR_STOP=1 -v email="$EMAIL" -qAt)"

if [ "$COUNT" = "1" ]; then
    echo "make-bench-account: $EMAIL is the bench account."
    exit 0
fi
echo "make-bench-account: no account $EMAIL to give the bench role (an admin is never changed)." >&2
exit 1
