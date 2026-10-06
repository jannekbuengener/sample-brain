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
repos="$(cd "${sb}/.." && pwd)"
cdb="${repos}/Claire_de_Binare"
mcp="${repos}/gpt-mcp-server"

echo "sample-brain-env-install-begin sb=${sb}"
test -f "${sb}/requirements.txt"
test -f "${cdb}/requirements.txt"
test -f "${cdb}/requirements-dev.txt"
test -f "${cdb}/requirements-mcp.txt"
test -f "${mcp}/package-lock.json"

python3.12 -m venv "${sb}/.venv"
"${sb}/.venv/bin/python" -m pip install --upgrade pip
"${sb}/.venv/bin/python" -m pip install -r "${sb}/requirements.txt" "pytest>=8,<10" "ruff==0.16.0"
"${sb}/.venv/bin/python" -m pip install -e "${sb}"

python3.12 -m venv "${cdb}/.venv"
"${cdb}/.venv/bin/python" -m pip install --upgrade pip
"${cdb}/.venv/bin/python" -m pip install -r "${cdb}/requirements.txt" -r "${cdb}/requirements-dev.txt" -r "${cdb}/requirements-mcp.txt"

npm ci --no-audit --no-fund --prefix "${mcp}"
echo sample-brain-env-install-ok
