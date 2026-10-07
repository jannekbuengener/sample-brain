#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

if ! command -v npm >/dev/null 2>&1; then
  nvm_bin="$(find /home/ubuntu/.nvm/versions/node -mindepth 2 -maxdepth 2 -type d -name bin 2>/dev/null | sort -V | tail -n 1 || true)"
  if [[ -n "${nvm_bin}" ]]; then
    export PATH="${nvm_bin}:${PATH}"
  fi
fi

sudo apt-get update
sudo apt-get install -y python3.12-venv python3-tk libsndfile1 xvfb

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sb="$(cd "${script_dir}/.." && pwd)"

echo "sample-brain-env-install-begin sb=${sb}"
test -f "${sb}/requirements.txt"

python3.12 -m venv "${sb}/.venv"
"${sb}/.venv/bin/python" -m pip install --upgrade pip
"${sb}/.venv/bin/python" -m pip install -r "${sb}/requirements.txt" "pytest>=8,<10" "ruff==0.16.0"
"${sb}/.venv/bin/python" -m pip install -e "${sb}"

# Sibling checkouts are optional. Prepare them only when they sit beside this repo.
repos="$(cd "${sb}/.." && pwd)"
cdb="${repos}/Claire_de_Binare"
mcp="${repos}/gpt-mcp-server"

if [[ -f "${cdb}/requirements.txt" && -f "${cdb}/requirements-dev.txt" && -f "${cdb}/requirements-mcp.txt" ]]; then
  echo "sample-brain-env-install-claire cdb=${cdb}"
  python3.12 -m venv "${cdb}/.venv"
  "${cdb}/.venv/bin/python" -m pip install --upgrade pip
  "${cdb}/.venv/bin/python" -m pip install -r "${cdb}/requirements.txt" -r "${cdb}/requirements-dev.txt" -r "${cdb}/requirements-mcp.txt"
else
  echo "sample-brain-env-install-skip-claire"
fi

if [[ -f "${mcp}/package-lock.json" ]]; then
  echo "sample-brain-env-install-mcp mcp=${mcp}"
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required to install gpt-mcp-server but was not found" >&2
    exit 1
  fi
  npm ci --no-audit --no-fund --prefix "${mcp}"
else
  echo "sample-brain-env-install-skip-mcp"
fi

echo sample-brain-env-install-ok
