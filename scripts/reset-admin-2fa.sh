#!/bin/sh
# For David only, when the phone and the backup codes are both lost: turns off the second factor of one account and deletes
# all its sessions, straight in the database like make-admin.sh. There is no web route for this, on purpose.
# The account keeps its role but loses the admin power until the second factor is turned on again from "My account".
# Usage: scripts/reset-admin-2fa.sh you@example.com
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ "$#" -ne 1 ]; then
    echo "usage: scripts/reset-admin-2fa.sh <email>" >&2
    exit 2
fi
EMAIL="$1"
case "$EMAIL" in
    *@*.*) ;;
    *)
        echo "reset-admin-2fa: this does not look like an email address." >&2
        exit 2
        ;;
esac
if [ "${#EMAIL}" -gt 320 ] || printf '%s' "$EMAIL" | grep -q '[[:space:]]'; then
    echo "reset-admin-2fa: this does not look like an email address." >&2
    exit 2
fi

COUNT="$(printf '%s\n' "WITH target AS (SELECT id FROM auth.\"user\" WHERE email = lower(:'email')), factors AS (DELETE FROM auth.\"twoFactor\" WHERE \"userId\" IN (SELECT id FROM target)), sessions AS (DELETE FROM auth.\"session\" WHERE \"userId\" IN (SELECT id FROM target)), changed AS (UPDATE auth.\"user\" SET \"twoFactorEnabled\" = false, \"updatedAt\" = now() WHERE id IN (SELECT id FROM target) RETURNING 1) SELECT count(*) FROM changed;" \
    | docker compose exec -T postgres psql -U mcplain -d mcplain -v ON_ERROR_STOP=1 -v email="$EMAIL" -At)"

if [ "$COUNT" = "1" ]; then
    echo "reset-admin-2fa: the second factor of $EMAIL is off and its sessions are deleted. Sign in with the password, then turn it on again in My account, Security."
    exit 0
fi
echo "reset-admin-2fa: no account $EMAIL." >&2
exit 1
