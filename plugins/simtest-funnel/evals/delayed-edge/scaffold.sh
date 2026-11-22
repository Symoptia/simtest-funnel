#!/usr/bin/env bash
# Writes this case's input files into the run's empty workspace (the current
# directory). Data is generated, or copied from the repository checkout this
# case lives in, by ../_data/make_data.py; nothing is stored in the plugin.
set -euo pipefail
case_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
generator="$case_dir/../_data/make_data.py"
if [ ! -f "$generator" ]; then
  echo "scaffold: $generator not found (run the suite from a repository checkout)" >&2
  exit 1
fi
exec python3 "$generator" "$(basename "$case_dir")" .
