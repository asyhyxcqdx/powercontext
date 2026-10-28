#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
want='2026-competition-ecosystem'
have=$(git branch --show-current)
if [ "$have" != "$want" ]; then
  echo "Wrong competition branch: current=$have, required=$want" >&2
  exit 1
fi
git rev-parse HEAD
printf 'Branch check PASS: %s\n' "$have"
