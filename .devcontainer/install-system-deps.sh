#!/usr/bin/env bash
# Install system-level dependencies for simtest-funnel development.
# Used by both the devcontainer Dockerfile and copilot-setup-steps workflow.
set -euo pipefail

apt-get update
apt-get install -y --no-install-recommends \
    build-essential cmake curl gnupg git ca-certificates

pip install uv

apt-get clean
rm -rf /var/lib/apt/lists/*
