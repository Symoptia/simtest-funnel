#!/usr/bin/env bash
# Install project-level dependencies for simtest-funnel.
# Used by both the devcontainer postCreateCommand and copilot-setup-steps workflow.
set -euo pipefail

# Symlink the host's .ssh directory to ensure SSH keys are available in the container
ln -sfn "${HOST_HOME}"/.ssh /home/vscode/.ssh
# Set up sharing of copilot config directory.
ln -sfn "${COPILOT_CONFIG}" /home/vscode/.copilot

uv sync
pnpm install --frozen-lockfile || pnpm install
lefthook install

