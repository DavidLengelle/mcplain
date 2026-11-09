#!/bin/sh
# Print the commit the running redacteur image was built from, among the last 50 commits.
# Exit 1, with a clear message, when the image is not built from the last commit.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IMAGE_DIGEST="$(docker compose exec -T redacteur cat /app/source-tree.txt 2>/dev/null | tr -d '[:space:]')" || IMAGE_DIGEST=""
if [ -z "$IMAGE_DIGEST" ]; then
    echo "image: no fingerprint in the running redacteur image. Rebuild it: docker compose up -d --build" >&2
    exit 1
fi

HEAD_COMMIT="$(git rev-parse --short HEAD)"
FOUND=""
for COMMIT in $(git rev-list -n 50 HEAD); do
    COMMIT_DIGEST="$(git ls-tree -r "$COMMIT" -- api/src engine/src | python3 -c '
import hashlib, sys
entries = {}
for line in sys.stdin:
    meta, path = line.rstrip("\n").split("\t", 1)
    if meta.split()[1] == "blob" and "__pycache__" not in path.split("/"):
        entries[path] = meta.split()[2]
print(hashlib.sha256("".join(f"{entries[p]} {p}\n" for p in sorted(entries)).encode("utf-8")).hexdigest())
')"
    if [ "$COMMIT_DIGEST" = "$IMAGE_DIGEST" ]; then
        FOUND="$(git rev-parse --short "$COMMIT")"
        break
    fi
done

if [ -z "$FOUND" ]; then
    echo "image: built from code that matches none of the last 50 commits (uncommitted changes?)." >&2
    echo "Rebuild it from the last commit $HEAD_COMMIT: docker compose up -d --build" >&2
    exit 1
fi
echo "image commit: $FOUND"
if [ "$FOUND" != "$HEAD_COMMIT" ]; then
    echo "image: built from $FOUND, older than the last commit $HEAD_COMMIT. Rebuild it: docker compose up -d --build" >&2
    exit 1
fi
