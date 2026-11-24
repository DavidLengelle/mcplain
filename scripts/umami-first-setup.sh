#!/bin/sh
# For David only, once, just after the first start of Umami: changes the password of the admin account that Umami
# creates with the public password "umami", then creates the tracked website and writes its public id in .env.
# The new password is typed without echo; it never goes in .env, on a command line, on the screen or in a log.
# Usage, from anywhere: scripts/umami-first-setup.sh [domain of the website, localhost by default]
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
DOMAIN="${1:-localhost}"
SITE_NAME="MCPlain"
MIN_PASSWORD_CHARS=12
WAIT_SECONDS=60

fail() {
    echo "umami-first-setup: $1" >&2
    exit 1
}

for TOOL in docker curl python3; do
    command -v "$TOOL" >/dev/null 2>&1 || fail "$TOOL is missing: nothing was changed."
done

cd "$ROOT"
CONTAINER="$(docker compose ps -q umami)"
[ -n "$CONTAINER" ] || fail "the umami service is not running: start it with docker compose up -d umami."

PORTS="$(docker inspect -f '{{json .NetworkSettings.Ports}}' "$CONTAINER")"
PORT="$(printf '%s' "$PORTS" | python3 -c '
import json, sys
bindings = [binding for items in (json.load(sys.stdin) or {}).values() if items for binding in items]
hosts = {binding.get("HostIp") for binding in bindings}
ports = {binding.get("HostPort") for binding in bindings}
if not bindings or hosts != {"127.0.0.1"} or len(ports) != 1:
    sys.exit(1)
print(ports.pop())
')" || fail "the Umami dashboard is published elsewhere than on 127.0.0.1: nothing was changed."
BASE="http://127.0.0.1:$PORT"

WEB="$(docker compose port web 3000 2>/dev/null || true)"
if [ -n "$WEB" ]; then
    case "$WEB" in
        127.0.0.1:*) ;;
        *) fail "the website is published elsewhere than on 127.0.0.1: nothing was changed." ;;
    esac
    for HIDDEN in /umami/api/auth/login /umami/login /umami/api/websites /umami; do
        STATUS="$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://$WEB$HIDDEN" || true)"
        [ "$STATUS" = "404" ] || fail "the website lets $HIDDEN through to Umami (HTTP $STATUS): nothing was changed."
    done
fi

WAITED=0
until curl -fs -o /dev/null "$BASE/api/heartbeat"; do
    WAITED=$((WAITED + 1))
    [ "$WAITED" -lt "$WAIT_SECONDS" ] || fail "Umami does not answer on $BASE."
    sleep 1
done

WORK="$(mktemp -d)"
chmod 700 "$WORK"
trap 'stty echo 2>/dev/null || true; rm -rf "$WORK"' EXIT INT TERM
umask 077

token_of() {
    python3 -c 'import json, sys; print(json.load(sys.stdin).get("token", ""))' 2>/dev/null || true
}

login() {
    curl -s -X POST "$BASE/api/auth/login" -H "Content-Type: application/json" --data-binary @- | token_of
}

TOKEN="$(printf '%s' '{"username": "admin", "password": "umami"}' | login)"
[ -n "$TOKEN" ] || fail "the default password does not work any more: it was already changed. Nothing was done."
printf 'Authorization: Bearer %s\n' "$TOKEN" > "$WORK/headers"

stty -echo 2>/dev/null || true
printf 'New password of the Umami admin (at least %s characters): ' "$MIN_PASSWORD_CHARS"
IFS= read -r PASSWORD
printf '\nType it again: '
IFS= read -r AGAIN
stty echo 2>/dev/null || true
printf '\n'
[ "$PASSWORD" = "$AGAIN" ] || fail "the two passwords differ: nothing was changed."
[ "${#PASSWORD}" -ge "$MIN_PASSWORD_CHARS" ] || fail "the password is too short: nothing was changed."
[ "$PASSWORD" != "umami" ] || fail "choose another password than umami: nothing was changed."

printf '%s' "$PASSWORD" | python3 -c 'import json, sys; print(json.dumps({"currentPassword": "umami", "newPassword": sys.stdin.read()}))' > "$WORK/password.json"
STATUS="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/me/password" -H @"$WORK/headers" -H "Content-Type: application/json" --data-binary @"$WORK/password.json")"
rm -f "$WORK/password.json"
[ "$STATUS" = "200" ] || fail "Umami refused the new password (HTTP $STATUS)."
echo "umami-first-setup: the password of the Umami admin is changed."

TOKEN="$(printf '%s' "$PASSWORD" | python3 -c 'import json, sys; print(json.dumps({"username": "admin", "password": sys.stdin.read()}))' | login)"
PASSWORD=""
AGAIN=""
[ -n "$TOKEN" ] || fail "cannot sign in with the new password."
printf 'Authorization: Bearer %s\n' "$TOKEN" > "$WORK/headers"

WEBSITE="$(curl -s "$BASE/api/websites" -H @"$WORK/headers" | DOMAIN="$DOMAIN" python3 -c '
import json, os, sys
for item in (json.load(sys.stdin) or {}).get("data", []):
    if item.get("domain") == os.environ["DOMAIN"]:
        print(item.get("id", ""))
        break
' 2>/dev/null || true)"
if [ -z "$WEBSITE" ]; then
    WEBSITE="$(SITE_NAME="$SITE_NAME" DOMAIN="$DOMAIN" python3 -c 'import json, os; print(json.dumps({"name": os.environ["SITE_NAME"], "domain": os.environ["DOMAIN"]}))' \
        | curl -s -X POST "$BASE/api/websites" -H @"$WORK/headers" -H "Content-Type: application/json" --data-binary @- \
        | python3 -c 'import json, sys; print(json.load(sys.stdin).get("id", ""))' 2>/dev/null || true)"
fi
printf '%s' "$WEBSITE" | grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' || fail "Umami did not create the website $DOMAIN."

if [ -f "$ENV_FILE" ] && grep -Eq '^MCPLAIN_UMAMI_WEBSITE_ID=' "$ENV_FILE"; then
    TEMPORARY="$(mktemp "$ROOT/.env.XXXXXX")"
    VALUE="$WEBSITE" awk 'BEGIN { value = ENVIRON["VALUE"] } /^MCPLAIN_UMAMI_WEBSITE_ID=/ { print "MCPLAIN_UMAMI_WEBSITE_ID=" value; next } { print }' "$ENV_FILE" > "$TEMPORARY"
    chmod 600 "$TEMPORARY"
    mv "$TEMPORARY" "$ENV_FILE"
else
    if [ -s "$ENV_FILE" ] && [ -n "$(tail -c 1 "$ENV_FILE")" ]; then
        printf '\n' >> "$ENV_FILE"
    fi
    printf 'MCPLAIN_UMAMI_WEBSITE_ID=%s\n' "$WEBSITE" >> "$ENV_FILE"
fi

echo "umami-first-setup: website $DOMAIN tracked, its public id $WEBSITE is in .env (MCPLAIN_UMAMI_WEBSITE_ID)."
echo "umami-first-setup: now run: docker compose up -d web"
echo "umami-first-setup: then open $BASE, sign in as admin and turn on the two-factor check (Settings, Profile)."
