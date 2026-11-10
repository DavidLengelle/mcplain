#!/bin/sh
# For David only: makes one account admin, only when its email address is verified. Usage: scripts/make-admin.sh you@example.com
# The address goes to psql as a variable, never pasted into the SQL. The website can never change a role.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ "$#" -ne 1 ]; then
    echo "usage: scripts/make-admin.sh <email>" >&2
    exit 2
fi
EMAIL="$1"
case "$EMAIL" in
    *@*.*) ;;
    *)
        echo "make-admin: this does not look like an email address." >&2
        exit 2
        ;;
esac
if [ "${#EMAIL}" -gt 320 ] || printf '%s' "$EMAIL" | grep -q '[[:space:]]'; then
    echo "make-admin: this does not look like an email address." >&2
    exit 2
fi

COUNT="$(printf '%s\n' "WITH changed AS (UPDATE auth.\"user\" SET role = 'admin', \"updatedAt\" = now() WHERE email = lower(:'email') AND \"emailVerified\" RETURNING 1) SELECT count(*) FROM changed;" \
    | docker compose exec -T postgres psql -U mcplain -d mcplain -v ON_ERROR_STOP=1 -v email="$EMAIL" -At)"

if [ "$COUNT" = "1" ]; then
    echo "make-admin: $EMAIL is now admin."
    exit 0
fi
echo "make-admin: no account with a verified email address $EMAIL. Sign up, open the link of the mail, then run this again." >&2
exit 1
