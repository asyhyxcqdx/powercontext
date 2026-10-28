#!/usr/bin/env bash
# Backward-compatible WSL entrypoint; server installation works on WSL Linux too.
set -euo pipefail
cd "$(dirname "$0")/.."
exec bash scripts/install_server.sh
