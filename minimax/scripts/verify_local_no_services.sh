#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pytest -q tests/test_sddflow_unit.py
python -m pytest -q tests/test_regression.py
set +e
python -m pytest -q tests/test_feature_min_stock.py > /tmp/sdd_minimax_expected_failure.txt 2>&1
code=$?
set -e
cat /tmp/sdd_minimax_expected_failure.txt
if [ "$code" -ne 1 ] || ! grep -q ' failed' /tmp/sdd_minimax_expected_failure.txt || ! grep -Eq 'AssertionError: assert|E[[:space:]]+assert' /tmp/sdd_minimax_expected_failure.txt; then
  echo 'Baseline did not fail because of the intended business behavior.' >&2
  exit 1
fi
echo 'OFFLINE PRECHECK PASS: helper tests pass; regression passes; target assertions fail on baseline.'
