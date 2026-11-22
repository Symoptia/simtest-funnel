#!/usr/bin/env bash
# Host-side initialization for the devcontainer.
# Runs via initializeCommand before the container is created.
set -euo pipefail

mkdir -p "${HOME:-/home/codespace}" || true
mkdir -p "/mnt" || true
