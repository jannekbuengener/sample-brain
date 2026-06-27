#!/bin/bash
set -euo pipefail

# ---------------------------------------------------------------
# Sample-Brain Self-Hosted Runner — Entrypoint
#
# Handles first-time registration and reconnection with state
# persistence via Docker volume.
#
# Required env: RUNNER_TOKEN (only for first registration)
# Optional env: RUNNER_NAME, RUNNER_LABELS, RUNNER_WORKDIR
# ---------------------------------------------------------------

RUNNER_NAME="${RUNNER_NAME:-sample-brain-runner}"
RUNNER_LABELS="${RUNNER_LABELS:-sample-brain,linux,x64}"
RUNNER_WORKDIR="${RUNNER_WORKDIR:-/home/runner/_work}"
RUNNER_GROUP="${RUNNER_GROUP:-default}"
GITHUB_URL="${GITHUB_URL:-https://github.com/jannekbuengener/sample-brain}"
STATE_DIR="/home/runner/state"

STATE_RUNNER="${STATE_DIR}/.runner"
STATE_CREDENTIALS="${STATE_DIR}/.credentials"
STATE_CREDENTIALS_RSA="${STATE_DIR}/.credentials_rsaparams"

mkdir -p "${STATE_DIR}" "${RUNNER_WORKDIR}"
sudo chown -R runner:runner "${STATE_DIR}" "${RUNNER_WORKDIR}"

restore_state() {
    if [[ -f "${STATE_RUNNER}" && -f "${STATE_CREDENTIALS}" && -f "${STATE_CREDENTIALS_RSA}" ]]; then
        echo "[entrypoint] Restoring runner credentials from persistent state"
        cp "${STATE_RUNNER}" .runner
        cp "${STATE_CREDENTIALS}" .credentials
        cp "${STATE_CREDENTIALS_RSA}" .credentials_rsaparams
        return 0
    fi
    return 1
}

save_state() {
    echo "[entrypoint] Saving runner credentials to persistent state"
    cp .runner "${STATE_RUNNER}"
    cp .credentials "${STATE_CREDENTIALS}"
    cp .credentials_rsaparams "${STATE_CREDENTIALS_RSA}"
}

register_runner() {
    if [[ -z "${RUNNER_TOKEN:-}" ]]; then
        echo "[entrypoint] ERROR: RUNNER_TOKEN is required for first-time registration."
        echo "[entrypoint] Set RUNNER_TOKEN in .env.runner and restart."
        exit 1
    fi

    echo "[entrypoint] Registering runner: ${RUNNER_NAME}"
    ./config.sh \
        --url "${GITHUB_URL}" \
        --token "${RUNNER_TOKEN}" \
        --name "${RUNNER_NAME}" \
        --labels "${RUNNER_LABELS}" \
        --runnergroup "${RUNNER_GROUP}" \
        --work "${RUNNER_WORKDIR}" \
        --unattended \
        --replace

    save_state
    echo "[entrypoint] Registration complete"
}

if restore_state; then
    HAS_CONFIG=$(./config.sh --status 2>/dev/null || echo "not-configured")
else
    echo "[entrypoint] No persistent state found"
    HAS_CONFIG="not-configured"
fi

if [[ "${HAS_CONFIG}" == "not-configured" ]]; then
    register_runner
fi

echo "[entrypoint] Starting runner: ${RUNNER_NAME}"
exec ./run.sh
