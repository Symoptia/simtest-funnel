#!/usr/bin/env bash
# Refresh Cargo.lock and uv.lock after semantic-release has rewritten the
# workspace package versions (called from prepareCmd in .releaserc.json).
#
# Only the workspace packages' own entries may change: `cargo update
# --workspace` touches workspace members only and `uv lock` keeps every
# locked dependency version. As a guard, the script fails if the resulting
# diff of either lockfile contains any changed line other than a
# `version = "..."` line, so a release can never upgrade dependencies.
set -euo pipefail

cd "$(dirname "$0")/.."

cargo update --workspace
uv lock

changed=$(git diff -U0 -- Cargo.lock uv.lock \
  | grep -E '^[-+]' \
  | grep -Ev '^(\+\+\+|---) ' \
  | grep -Ev '^[-+]version = "[^"]*"$' || true)
if [ -n "$changed" ]; then
  echo "release-refresh-lockfiles: unexpected lockfile changes:" >&2
  echo "$changed" >&2
  exit 1
fi
