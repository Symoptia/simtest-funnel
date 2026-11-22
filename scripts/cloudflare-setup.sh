#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="simtest-funnel"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -o allexport && source .env && set +o allexport
fi

: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN must be set}"
: "${CLOUDFLARE_ACCOUNT_ID:?CLOUDFLARE_ACCOUNT_ID must be set}"

echo "Checking Cloudflare Pages project: $PROJECT_NAME"
if wrangler pages project list 2>/dev/null | grep -q "$PROJECT_NAME"; then
  echo "Project '$PROJECT_NAME' already exists — skipping creation."
else
  echo "Creating Cloudflare Pages project: $PROJECT_NAME"
  wrangler pages project create "$PROJECT_NAME" --production-branch main
fi

echo ""
echo "Verifying project configuration:"
wrangler pages project list | grep "$PROJECT_NAME" \
  && echo "Cloudflare Pages project '$PROJECT_NAME': OK" \
  || { echo "ERROR: Project not found after creation"; exit 1; }
