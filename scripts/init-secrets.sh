#!/bin/sh
# For David only: adds the missing secrets to .env with random values, and never replaces a value already there.
# It prints the names of the keys it adds, never a value. Run it from anywhere, then: docker compose up -d --build
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
SECRETS="POSTGRES_PASSWORD BETTER_AUTH_SECRET MCPLAIN_ALTCHA_HMAC_KEY MCPLAIN_APP_DB_PASSWORD MCPLAIN_GUICHET_DB_PASSWORD MCPLAIN_FACTEUR_DB_PASSWORD"

if ! command -v openssl >/dev/null 2>&1; then
    echo "init-secrets: openssl is missing: nothing was written." >&2
    exit 1
fi

umask 077
if [ ! -f "$ENV_FILE" ]; then
    : > "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"
if [ -s "$ENV_FILE" ] && [ -n "$(tail -c 1 "$ENV_FILE")" ]; then
    printf '\n' >> "$ENV_FILE"
fi

set_line() {
    if grep -Eq "^$1=" "$ENV_FILE"; then
        TEMPORARY="$(mktemp "$ROOT/.env.XXXXXX")"
        NAME="$1" VALUE="$2" awk 'BEGIN { name = ENVIRON["NAME"]; value = ENVIRON["VALUE"] } $0 == name "=" { print name "=" value; next } { print }' "$ENV_FILE" > "$TEMPORARY"
        chmod 600 "$TEMPORARY"
        mv "$TEMPORARY" "$ENV_FILE"
    else
        printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"
    fi
}

ADDED=0
for NAME_TO_FILL in $SECRETS; do
    if grep -Eq "^$NAME_TO_FILL=.+" "$ENV_FILE"; then
        continue
    fi
    set_line "$NAME_TO_FILL" "$(openssl rand -hex 32)"
    echo "init-secrets: added $NAME_TO_FILL"
    ADDED=$((ADDED + 1))
done

if ! grep -Eq "^COMPOSE_PROFILES=" "$ENV_FILE"; then
    set_line COMPOSE_PROFILES dev
    echo "init-secrets: added COMPOSE_PROFILES (dev: Mailpit receives the mails)"
    ADDED=$((ADDED + 1))
fi

if [ "$ADDED" -eq 0 ]; then
    echo "init-secrets: nothing to add, every secret is already set."
fi
