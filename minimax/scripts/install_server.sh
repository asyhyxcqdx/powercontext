#!/usr/bin/env bash
# Ubuntu 22.04 server bootstrap. Does not modify the system Python version.
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v curl >/dev/null; then
  echo 'Missing curl; install once with apt-get update && apt-get install -y curl ca-certificates git unzip' >&2
  exit 1
fi
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || { echo 'uv executable not found; inspect ~/.local/bin' >&2; exit 1; }
uv python install 3.12
if [ -e .venv/bin/python ]; then
  .venv/bin/python -c 'import sys; assert sys.version_info >= (3, 11), sys.version'
else
  uv venv --python 3.12 .venv
fi
uv pip install --python .venv/bin/python -r requirements.txt
# Keep PowerContext isolated within this minimax project, rather than
# upgrading any previous PowerContext CLI used by other competitions.
if [ ! -x .powercontext-venv/bin/python ]; then
  uv venv --python 3.12 .powercontext-venv
fi
uv pip install --python .powercontext-venv/bin/python 'powercontext[cli,server]==1.4.1'
export PATH="$PWD/.powercontext-venv/bin:$PATH"
command -v powercontext >/dev/null || { echo 'PowerContext project CLI not found.' >&2; exit 1; }
echo 'INSTALL SUCCESS; binaries:'
.venv/bin/python --version
powercontext --help >/dev/null
printf 'PowerContext CLI: %s\n' "$(command -v powercontext)"
echo 'Next: cp .env.example .env; chmod 600 .env; nano .env; bash scripts/full_demo_server.sh'
