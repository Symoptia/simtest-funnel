#!/usr/bin/env bash
# Install system-level dependencies for simtest-funnel development.
# Used by both the devcontainer Dockerfile and copilot-setup-steps workflow.
set -euo pipefail

apt-get update
apt-get install -y --no-install-recommends \
    build-essential cmake curl gnupg git ca-certificates

# Shared libraries a headless Chromium needs (about 7 MB on top of the base
# image). The browser itself is not installed here: `make browser-setup`
# downloads it on demand.
apt-get install -y --no-install-recommends \
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 libcairo2 \
    libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 libnspr4 libnss3 \
    libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 \
    libxfixes3 libxkbcommon0 libxrandr2

pip install uv "maturin[patchelf]"

apt-get clean
rm -rf /var/lib/apt/lists/*
