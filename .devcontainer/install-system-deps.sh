#!/usr/bin/env bash
# Install system-level dependencies for mbd2d development.
# Used by both the devcontainer Dockerfile and copilot-setup-steps workflow.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

apt-get update
apt-get install -y --no-install-recommends \
    build-essential \
    cmake

pip install uv

apt-get clean
rm -rf /var/lib/apt/lists/*
