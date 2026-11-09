#!/bin/sh
set -eu

REPOSITORY="https://github.com/harishsg993010/damn-vulnerable-MCP-server.git"
SHA="cdc4c6b5b76353203effcb26058e50fa6067d3a6"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$ROOT/engine/tests/fixtures/external/dvmcp"

if [ -e "$TARGET/.git" ]; then
    FOUND="$(git -C "$TARGET" rev-parse HEAD)"
    if [ "$FOUND" != "$SHA" ]; then
        echo "dvmcp: $TARGET is at $FOUND, expected $SHA. Remove the folder and run again." >&2
        exit 1
    fi
    echo "dvmcp: already at $SHA"
    exit 0
fi

if [ -e "$TARGET" ]; then
    echo "dvmcp: $TARGET exists but is not a clone. Remove the folder and run again." >&2
    exit 1
fi

mkdir -p "$TARGET"
git -C "$TARGET" init --quiet
git -C "$TARGET" config core.hooksPath /dev/null
git -C "$TARGET" remote add origin "$REPOSITORY"
git -C "$TARGET" fetch --quiet --depth 1 origin "$SHA"
git -C "$TARGET" -c advice.detachedHead=false checkout --quiet --detach FETCH_HEAD

FOUND="$(git -C "$TARGET" rev-parse HEAD)"
if [ "$FOUND" != "$SHA" ]; then
    echo "dvmcp: got $FOUND, expected $SHA" >&2
    exit 1
fi
echo "dvmcp: cloned at $SHA"
