#!/usr/bin/env bash
# Write a release version into the Python packages' pyproject.toml files in
# its PEP 440 form (called from prepareCmd in .releaserc.json).
#
# semantic-release computes SemVer versions (1.0.0-beta.21), which
# Cargo.toml and package.json keep. Python packaging normalises versions to
# PEP 440 (1.0.0b21), but hatchling writes the server's metadata version as
# spelled in pyproject.toml, so the server reported `1.0.0-beta.21` while
# the maturin-built library reported `1.0.0b21`. Writing the PEP 440 form
# keeps the metadata, `simtest-funnel-mcp --version` and the MCP
# serverInfo.version in the form pip, uv and PyPI show.
#
# Usage: scripts/release-python-versions.sh <semver>
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: $0 <semver version, e.g. 1.0.0-beta.21>" >&2
  exit 2
fi
semver=$1
# 1.2.3 | 1.2.3-alpha.N | 1.2.3-beta.N | 1.2.3-rc.N  ->  1.2.3, 1.2.3aN, 1.2.3bN, 1.2.3rcN
pep440=$(printf '%s\n' "$semver" | sed -E 's/^([0-9]+\.[0-9]+\.[0-9]+)(-(alpha|beta|rc)\.([0-9]+))?$/\1\3\4/; s/alpha/a/; s/beta/b/')
if ! printf '%s\n' "$pep440" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+((a|b|rc)[0-9]+)?$'; then
  echo "release-python-versions: cannot convert '$semver' to PEP 440" >&2
  exit 1
fi

cd "$(dirname "$0")/.."
sed -i "s/^version = .*/version = \"$pep440\"/" \
  crates/simtest-funnel-python/pyproject.toml python/simtest-funnel-mcp/pyproject.toml
sed -i "s/\"simtest-funnel==[^\"]*\"/\"simtest-funnel==$pep440\"/" python/simtest-funnel-mcp/pyproject.toml
echo "Python packages: $pep440 (from $semver)"
