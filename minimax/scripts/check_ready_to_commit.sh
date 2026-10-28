#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    echo "Python not found; install Python 3 or create .venv." >&2
    exit 127
  fi
fi
if [ ! -f evidence/15_submission_audit.json ]; then
  echo 'Missing real full-demo evidence. Do NOT submit yet.' >&2
  exit 1
fi
"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path
status=json.loads(Path('evidence/15_submission_audit.json').read_text())
if status.get('status') != 'READY_FOR_REVIEW':
    raise SystemExit('Cannot commit: submission evidence is not READY_FOR_REVIEW')
required=['evidence/11_state_after_server_restart.json',
          'evidence/14_offline_replay.json',
          'evidence/model_last_success.json',
          'snapshots/after/inventory.py']
for file in required:
    if not Path(file).is_file():
        raise SystemExit(f'Cannot commit: missing {file}')
print('Submission readiness gate PASS. Inspect logs before git add.')
PY
