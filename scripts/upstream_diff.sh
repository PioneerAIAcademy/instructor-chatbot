#!/usr/bin/env bash
# upstream_diff.sh — what changed upstream in each file this repo copied.
#
#   bash scripts/upstream_diff.sh ../pathway-chatbot [upstream-ref]
#
# For every row of the UPSTREAM.md "Files" table, prints `git diff --stat`
# of the upstream path between the base commit (named in UPSTREAM.md) and
# <upstream-ref> (default: main). Read-only: uses only the local checkout,
# no network. Run `git -C <path> fetch` first for the newest upstream.

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 <pathway-chatbot checkout> [upstream-ref]" >&2
  exit 2
fi

UPSTREAM_DIR="$1"
REF="${2:-main}"
REPO_ROOT="$(git rev-parse --show-toplevel)"
MANIFEST="$REPO_ROOT/UPSTREAM.md"

git -C "$UPSTREAM_DIR" rev-parse --git-dir >/dev/null 2>&1 \
  || { echo "not a git checkout: $UPSTREAM_DIR" >&2; exit 2; }

BASE="$(grep -m1 -oE 'Upstream base commit:\*\* `[0-9a-f]+`' "$MANIFEST" | grep -oE '[0-9a-f]{7,}')"
[ -n "$BASE" ] || { echo "no base commit found in UPSTREAM.md" >&2; exit 2; }
git -C "$UPSTREAM_DIR" cat-file -e "$BASE^{commit}" 2>/dev/null \
  || { echo "base commit $BASE is not in $UPSTREAM_DIR (fetch it)" >&2; exit 2; }

echo "upstream: $UPSTREAM_DIR  base: $BASE  ref: $REF ($(git -C "$UPSTREAM_DIR" rev-parse --short "$REF"))"
echo

changed=0
total=0
# Table rows look like: | `local` | `upstream` | Status | notes |
while IFS= read -r upstream_path; do
  total=$((total + 1))
  stat="$(git -C "$UPSTREAM_DIR" diff --stat "$BASE" "$REF" -- "$upstream_path")"
  if [ -n "$stat" ]; then
    changed=$((changed + 1))
    echo "$stat" | sed '$d'
  fi
done < <(grep -E '^\| `[^`]+` \| `[^`]+` \|' "$MANIFEST" | awk -F'`' '{print $4}')

echo
echo "$changed of $total tracked upstream files changed since $BASE."
