#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
want='2026-competition-ecosystem'
have=$(git branch --show-current)
if [ "$have" != "$want" ]; then
  printf 'Wrong branch: current=%s, required=%s\n' "$have" "$want" >&2
  exit 1
fi
printf 'PASS: branch=%s, commit=%s\n' "$have" "$(git rev-parse HEAD)"
