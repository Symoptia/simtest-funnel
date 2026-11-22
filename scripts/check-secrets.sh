#!/usr/bin/env bash
set -euo pipefail

REPO="Symoptia/simtest-funnel"
ERRORS=0

REQUIRED_VARS=(
  CLOUDFLARE_ACCOUNT_ID
  CLOUDFLARE_API_TOKEN
  PYPI_API_TOKEN
  NPM_TOKEN
  CARGO_REGISTRY_TOKEN
  GH_TOKEN
)

echo "=== Checking local .env ==="
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -o allexport && source .env && set +o allexport
  for var in "${REQUIRED_VARS[@]}"; do
    if [[ -n "${!var:-}" ]]; then
      echo "  .env $var: OK"
    else
      echo "  .env $var: MISSING"
      ((ERRORS++))
    fi
  done
else
  echo "  WARNING: .env file not found (optional for CI-only use)"
fi

echo ""
echo "=== Checking GitHub Secrets ==="
if ! gh auth status &>/dev/null; then
  echo "  WARNING: gh CLI not authenticated — skipping GitHub Secrets check"
else
  CONFIGURED=$(gh secret list --repo "$REPO" 2>/dev/null | awk '{print $1}')
  for var in "${REQUIRED_VARS[@]}"; do
    if echo "$CONFIGURED" | grep -q "^$var$"; then
      echo "  GitHub Secret $var: OK"
    else
      echo "  GitHub Secret $var: MISSING"
      ((ERRORS++))
    fi
  done
fi

echo ""
if [[ $ERRORS -eq 0 ]]; then
  echo "All secrets OK."
  exit 0
else
  echo "ERROR: $ERRORS secret(s) missing. See MAINTAINER.md."
  exit 1
fi
