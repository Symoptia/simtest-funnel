#!/usr/bin/env bash
set -euo pipefail

REPO="Symoptia/simtest-funnel"

if [[ ! -f .env ]]; then
  echo "ERROR: .env file not found. Copy .env.example to .env and fill in values."
  exit 1
fi

gh auth status || { echo "ERROR: gh CLI not authenticated. Run: gh auth login"; exit 1; }

# shellcheck disable=SC1091
set -o allexport
source .env
set +o allexport

REQUIRED_VARS=(
  CLOUDFLARE_ACCOUNT_ID
  CLOUDFLARE_API_TOKEN
  PYPI_API_TOKEN
  NPM_TOKEN
  CARGO_REGISTRY_TOKEN
  GH_TOKEN
)

for var in "${REQUIRED_VARS[@]}"; do
  val="${!var:-}"
  if [[ -z "$val" ]]; then
    echo "ERROR: $var is not set in .env"
    exit 1
  fi
  echo "Setting secret: $var"
  gh secret set "$var" --body "$val" --repo "$REPO"
done

echo ""
echo "All secrets set. Verifying..."
gh secret list --repo "$REPO"
