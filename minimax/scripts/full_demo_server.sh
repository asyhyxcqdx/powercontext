#!/usr/bin/env bash
# On-server entrypoint. All three technology integrations use the local server.
set -euo pipefail
cd "$(dirname "$0")/.."
exec bash scripts/full_demo_wsl.sh
