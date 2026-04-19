#!/usr/bin/env bash
# Install project-level dependencies for simtest-funnel.
# Used by both the devcontainer postCreateCommand and copilot-setup-steps workflow.
set -euo pipefail

# Symlink the host's .ssh directory to ensure SSH keys are available in the container
ln -sfn "${HOST_HOME:-/home/codespace}"/.ssh /home/vscode/.ssh || \
 echo "Failed to create symlink for .ssh directory. Continuing without it."
# Set up sharing of copilot config directory.
ln -sfn "${COPILOT_CONFIG:-/workspaces/simtest-funnel/.copilot}" /home/vscode/.copilot || \
 echo "Failed to create symlink for copilot config directory. Continuing without it."

uv sync
pnpm install --frozen-lockfile || pnpm install
lefthook install 2>/dev/null || echo "lefthook not found, skipping hook installation"

