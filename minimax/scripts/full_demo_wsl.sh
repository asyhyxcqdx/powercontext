#!/usr/bin/env bash
# Exact real-integrations evidence run on Linux server; no mocked results.
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
if [ -z "${MINIMAX_API_KEY:-}" ] || [[ "$MINIMAX_API_KEY" == REPLACE_* ]]; then
  echo 'MINIMAX_API_KEY is not set; cannot claim a real MiniMax code change.' >&2
  exit 1
fi
export PATH="$PWD/.venv/bin:$PWD/.powercontext-venv/bin:$HOME/.local/bin:$PATH"
# Isolated local-only PowerContext instance; do not expose public ports.
export POWERCONTEXT_HOME="$PWD/runtime/powercontext-home"
export POWERCONTEXT_SERVER_HTTP_HOST=127.0.0.1
export POWERCONTEXT_SERVER_HTTP_PORT=18080
export POWERCONTEXT_SERVER_DATABASE_KIND=sqlite
export POWERCONTEXT_SERVER_ACCESS_MODE=disabled
unset POWERCONTEXT_SERVER_DATABASE_URL || true
command -v powercontext >/dev/null || { echo 'PowerContext not installed. Run scripts/install_server.sh first.' >&2; exit 1; }
export POWERCONTEXT_URL="${POWERCONTEXT_URL:-http://127.0.0.1:18080}"
if [ "$POWERCONTEXT_URL" != 'http://127.0.0.1:18080' ]; then
  echo 'This automatic server demonstration uses local port 18080; override only via manual CLI.' >&2
  exit 1
fi
mkdir -p runtime evidence
python -m sddflow.cli reset-code
if python -c 'import socket; s=socket.socket(); s.settimeout(1); result=s.connect_ex(("127.0.0.1",18080)); s.close(); raise SystemExit(0 if result==0 else 1)' >/dev/null 2>&1; then
  echo 'Port 18080 already occupied. Stop the existing process before this isolated run.' >&2
  exit 1
fi
start_pc() {
  powercontext server run > runtime/powercontext-server.log 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 45); do
    if python -c 'from urllib.request import urlopen; urlopen("http://127.0.0.1:18080/health/ready",timeout=2)' >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo 'PowerContext server exited; inspect runtime/powercontext-server.log' >&2
      return 1
    fi
    sleep 1
  done
  echo 'PowerContext server failed to become healthy; inspect runtime/powercontext-server.log' >&2
  return 1
}
stop_pc() {
  if [ -n "${SERVER_PID:-}" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    SERVER_PID=''
  fi
}
trap stop_pc EXIT
start_pc
python -m sddflow.cli init-scope > evidence/01_scope.json
python -m sddflow.cli ingest > evidence/02_ingest.json
python -m sddflow.cli state-read > evidence/03_initial_empty_state.json
python - <<'PY'
import json
obj=json.load(open('evidence/03_initial_empty_state.json'))
assert not obj['records'], 'State was not empty; clean runtime/powercontext-home and retry'
PY
python -m sddflow.cli baseline-test > evidence/04_before_test.json
python -m sddflow.cli state-write --stage baseline_failed --next implement_min_stock_with_MiniMax > evidence/05_state_write.json
python -m sddflow.cli context > evidence/06_development_context.json
python -m sddflow.cli model-apply > evidence/07_minimax_applied.json
python -m sddflow.cli ingest > evidence/08_reingest_modified_code.json
python -m sddflow.cli after-test > evidence/09_after_test.json
python -m sddflow.cli state-write --stage validated --next review_and_submit > evidence/10_state_write_validated.json
stop_pc
# Start a *new PowerContext server process* against the exact same durable home.
start_pc
python -m sddflow.cli state-read --require-stage validated > evidence/11_state_after_server_restart.json
python -m sddflow.cli context > evidence/12_context_after_server_restart.json
python -m sddflow.cli verify-spec-refresh > evidence/13_spec_refresh.json
python -m sddflow.cli reproduce-offline > evidence/14_offline_replay.json
python -m sddflow.cli audit > evidence/15_submission_audit.json
python - <<'PY'
import json
out=json.load(open('evidence/15_submission_audit.json'))
assert out['status']=='READY_FOR_REVIEW', out
print('ALL SIX EVIDENCE CATEGORIES PRODUCED; review evidence/ and commit real logs.')
PY
