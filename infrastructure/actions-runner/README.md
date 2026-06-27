# Sample-Brain Self-Hosted GitHub Actions Runner

Containerized GitHub Actions runner for Sample-Brain CI/CD, completely
independent from the CDB runner infrastructure.

## Quick Start

```bash
# 1. Generate a registration token:
#    GitHub repo > Settings > Actions > Runners > New runner > copy token

# 2. Configure environment
cp .env.example .env.runner
# Paste RUNNER_TOKEN into .env.runner

# 3. Build and start
docker compose -f infrastructure/actions-runner/docker-compose.yml up -d --build

# 4. Verify
docker compose -f infrastructure/actions-runner/docker-compose.yml logs -f
# Expected: "Listening for Jobs"
```

## Labels

| Label | Origin | Purpose |
|-------|--------|---------|
| `self-hosted` | automatic | Standard GitHub label |
| `sample-brain` | explicit | Primary identifier for Sample-Brain jobs |
| `linux` | explicit | Operating system |
| `x64` | explicit | Architecture |

Workflows target: `runs-on: [self-hosted, sample-brain]`.

## Architecture

- **Docker-based**: The runner runs in a container, isolated from the host and
  from any other runner instances (e.g. CDB runners).
- **State persistence**: Runner credentials are stored in a named Docker volume
  (`sample-brain-runner-state`), allowing container rebuilds without
  re-registration.
- **Separate volumes**: Work directory and credentials each have dedicated volumes.
- **Auto-restart**: `restart: unless-stopped` ensures the runner reconnects after
  host reboots or crashes.
- **Python included**: Pre-built with Python 3.12, pip, and venv from the
  `mcr.microsoft.com/devcontainers/python:3.12-bookworm` base image.

## Volume Management

| Volume | Mount | Purpose |
|--------|-------|---------|
| `sample-brain-runner-state` | `/home/runner/state` | Runner credentials (`.runner`, `.credentials`, `.credentials_rsaparams`) |
| `sample-brain-runner-work` | `/home/runner/_work` | Job workspace data |

## Token Refresh

The registration token (from GitHub UI) expires after 1 hour, but it is only
needed for the initial `config.sh` call. Once registered, the runner
authenticates with its own credentials stored in the state volume.
A new token is required only when:

- The container is rebuilt from scratch without a state volume.
- The state volume is deleted or corrupted.
- The runner is manually removed in the GitHub UI.

## Maintenance

**Rebuild without re-registration:**

```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml down
docker compose -f infrastructure/actions-runner/docker-compose.yml up -d --build
```

**Stop (runner stays registered, goes offline):**

```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml down
```

**Full removal (deregister + delete volumes):**

```bash
docker compose -f infrastructure/actions-runner/docker-compose.yml down -v
```

Then remove the runner from GitHub UI: Settings > Actions > Runners.

## Rollback

1. Stop the container: `docker compose down`
2. Remove the new state: `docker volume rm sample-brain-runner-state`
3. Generate a fresh `RUNNER_TOKEN`
4. Update `.env.runner` with the new token
5. Rebuild and start: `docker compose up -d --build`
6. Remove the old runner entry from GitHub UI if it didn't deregister cleanly

## Security Notes

- No secrets in workflow files — `contents: read` is sufficient for smoke tests.
- `workflow_dispatch` only — no automatic pull_request or push triggers.
- Isolated Docker network — no access to CDB containers or networks.
- Runner runs as non-root user (`runner` UID 1001) inside the container.
- No shared workdir with CDB — dedicated `sb-runner-work` volume.
- The Docker socket mount is optional and disabled by default in compose.
