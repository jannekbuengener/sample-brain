# AGENTS.md - Root Scope

## Purpose
- This file defines global agent guidance for the whole `sample-brain` repository.
- Deeper `AGENTS.md` files override and refine rules for their own subtree.

## Scope Map
- `src/` -> implementation and runtime logic (`src/AGENTS.md`)
- `tests/` -> unit/integration test expectations (`tests/AGENTS.md`)
- `docs/` -> product/architecture/process docs (`docs/AGENTS.md`)
- `agents/` -> shared cross-agent charter (`agents/AGENTS.md`)
- `SB.*` root files -> Sample-Brain-Orchestrator: `SB.BOOTLOADER.md` (session startup), `SB.AGENT.LIST.json` (agent registry), `SB.AGENT.RULESET.md` (agent operating rules), `SB.VERFUEGBARE.SKILLS.md` (available skill matrix)

## Project Baseline
- Stack: Python (3.12+), sqlite, librosa/soundfile, numpy/scipy, sqlalchemy.
- CLI entrypoint: `src/cli.py`.
- Main flow: `init -> scan -> analyze -> autotype -> export_fl` (optional: `embed -> index_build -> search`).
- The existing offline analysis/data pipeline remains the foundation. Local real-time playback, mixing, recording, grid-bound editing, `TEMPO`, `SYNC`, and `HÄFTIG` are explicitly allowed inside the local Workbench under the boundary in `docs/REALTIME_WORKBENCH_SCOPE.md` (#318/#319).
- For Screen 1, `LOCK_PYSIDE6_QML` is the decided renderer contract: new visual/product implementation belongs in PySide6 / Qt Quick / QML. Tkinter remains the functional default and legacy/fallback path, plus a source of existing behavior and integration contracts; it does not authorize new Screen-1 product visuals. Python Core/Controller/Audio/Catalog contracts remain authoritative and must be reused rather than duplicated in QML.
- A native audio core may own the hard real-time audio path; Python remains the authoritative analysis/control/core integration layer and must not become the authoritative real-time audio clock.
- The #318 cluster is not a full DAW and does not require a VST/VST3/FL Studio plugin.

## Global Rules
- Keep changes minimal, scoped, and reversible.
- Do not commit machine-local paths, secrets, private keys, or credentials.
- Never commit private samples, tracks, recordings, generated audio, device dumps, or runtime audio caches.
- Respect config/profile indirection (`config/profiles.example.yaml` + optional local overrides) instead of hardcoding environment-specific values.
- Preserve graceful behavior for optional dependencies (especially embedding backends).
- Prefer updating tests together with behavior changes.

## Skill routing
- Machine routing authority: `docs/operations/CAPABILITY_REGISTRY.json` (front door: `docs/operations/README.md`).
- Generated views: `.cursor/rules/skill-routing.mdc`, `SB.VERFUEGBARE.SKILLS.md` (marked generated blocks only).
- Human narrative: `docs/SKILL_INTEGRATION_PLAN.md` (not machine authority).
- `SB.VERFUEGBARE.SKILLS_LISTE_2026-08-09.md` is historical/frozen, not active routing authority.
- These provide recommendation/routing guidance only; they do not authorize automatic tool, workflow, CI, or security changes.

## Quality Gates

For docs/canon/governance/status/routing/audit changes, also run:

```bash
python tools/check_canon_drift.py
```

For operations/capability/routing/skill-mirror changes, also run:

```bash
python tools/check_capability_drift.py
```

These are narrow deterministic drift sweeps; live GitHub/repo evidence still wins.

- Setup:
- `py -3.12 -m venv .venv`
- `.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest`
- `.\.venv\Scripts\python.exe -m pip install -e .`
- Verify:
- `.\.venv\Scripts\python.exe -m pytest -q`
- CLI smoke:
- `.\.venv\Scripts\python.exe -m src.cli --help`
- `.\.venv\Scripts\sample-brain --help`
- External DB smoke (preferred for agents): set `SAMPLE_BRAIN_DB_PATH` outside repo, then `python -m src.cli init`

### Optional `[vec]` verify (sqlite-vec search path)

Only when working on sqlite-vec gates or backend behavior:

```bash
pip install -e ".[vec]"
python -m src.cli vec status
python -m pytest -q   # full suite; optional/backend-specific tests may skip when extras are unavailable
```

Benchmark harness (local only, work-dir outside repo): `python -m src.cli benchmark vec --samples 1000 10000 100000 --work-dir /tmp/sample-brain-bench`. Gate evidence: [`docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md`](docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md). Default search backend remains **`numpy`** until all gates PASS.

## CI Gate Policy
- **`CI_GREEN` is the default merge contract.** Merge only when required checks are green. Optional checks should be green, skipped, or explicitly explained.
- **Review feedback is a mandatory pre-merge gate on the final PR head.** All relevant comments/threads/reviews (including bots) must be seen and dispositioned; inline threads resolved. Follow `docs/MERGE_REVIEW_FEEDBACK_GATE.md`. An untreated comment is a merge blocker. This gate does not weaken `CI_GREEN`.
- **Degraded CI mode is exceptional.** Use it only when GitHub-hosted runners, self-hosted runners, or repository/account infrastructure block checks before PR logic runs.
- **Docs-only billing waivers are narrow.** They require explicit merge-GO, a PR-specific waiver comment, exact docs-only scope, and no code, dependency, workflow, artifact, or secret risk.
- **Code/test/runtime scope under CI outage is not auto-waivable.** Follow `docs/CI_DEGRADED_MODE.md` and treat local validation as required evidence, not as a fake green substitute.
- **Self-hosted runner fallback is the preferred recurring workaround.** Any runner or workflow change remains a separate scoped task with its own review and GO.

## Handover Notes
- When changing DB schema in `src/db.py`, validate affected read/write paths in `scan`, `analyze`, `classify`, `embed`, `index`, and their tests.
- When changing CLI args in `src/cli.py`, keep behavior and help text coherent across related commands.

## Cursor Cloud specific instructions

### Product shape
- **sample-brain** is primarily a local Python CLI plus local Workbench (no web server, no Docker). End-to-end pipeline testing is sequential CLI invocation, not service startup.
- The Workbench may use a narrow native audio core for hard real-time playback/recording while Python remains UI/analysis/control; see `docs/REALTIME_WORKBENCH_SCOPE.md`.
- Entry point: `python -m src.cli` (or `.venv/bin/python -m src.cli` on Linux).

### System packages
- Ubuntu/Debian needs `python3.12-venv` and `python3-tk` before venv creation and Workbench tests (`sudo apt-get install -y python3.12-venv python3-tk`). Tk is required because Workbench modules and tests import `tkinter`.
- `libsndfile1` is required for real `analyze` runs. `xvfb` is required to run the Tk tests headlessly. Both are present on the default Cloud Agent image.

### Dependency refresh (`install`)
The executable Cloud Agent install is `.cursor/environment.json`. It is idempotent, uses LF line endings, and creates `.venv` in the discovered checkout rather than assuming the shell working directory is the repository root. When Claire de Binare or gpt-mcp-server checkouts are present beside this repository, the same install prepares those projects too. It keeps the default Ubuntu image and does not start a server.

The sample-brain portion of that install is:

```bash
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update
sudo apt-get install -y python3.12-venv python3-tk
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt "pytest>=8,<10" "ruff==0.16.0"
.venv/bin/python -m pip install -e .
```

- `pytest` and `ruff` are **not** listed in `requirements.txt`. CI pins `pytest>=8,<10` and `ruff==0.16.0`.

### Verify (Linux paths)
```bash
source .venv/bin/activate
python -m src.cli --help
sample-brain --help
xvfb-run -a python -m pytest -q
python -m ruff check .
python -m py_compile src/analyze.py src/cli.py
```

Activate the venv before pytest. A few tests spawn bare `python`. `.venv/bin` must be on `PATH`, and `/usr/bin/python3` does not have the project dependencies.

### Bootstrap validation notes
- Full `xvfb-run -a python -m pytest -q` on this image: 2318 passed, 72 skipped, and 2 failed. The two failures are `tests/test_workbench_desktop_shortcut.py` runtime-installer rollback tests. They create a temp directory in the repository parent. Cloud Agent checkout is `/workspace`, so that parent is `/` and `tempfile` raises `PermissionError`. That is a checkout-layout limit, not a missing dependency.
- Nested tests call bare `python`. Run pytest from an activated venv so that command is `.venv/bin/python`. Do not symlink or overwrite `/usr/bin/python3.12`.
- Prefer `SAMPLE_BRAIN_DB_PATH` pointing outside the repo for agent smoke tests so `git status` stays clean.
- If `python -m venv` fails on Ubuntu/Debian, use `virtualenv` as fallback (see README bootstrap section).
- Do not run CLAP model download during bootstrap validation.

### Hello-world pipeline (no FL Studio install needed)
Use ephemeral paths under `/tmp` and explicit CLI flags (no committed local profile required):

```bash
mkdir -p /tmp/sample-brain-demo/samples /tmp/sample-brain-demo/fl-user-data
export SAMPLE_BRAIN_DB_PATH=/tmp/sample-brain-demo/catalog.db
python -m src.cli init
python -m src.cli scan --root /tmp/sample-brain-demo/samples
python -m src.cli analyze
python -m src.cli autotype --no-knn
python -m src.cli export_fl --fl-user-data /tmp/sample-brain-demo/fl-user-data
```

Place at least one `.wav` under the scan root (generate with `soundfile` if the repo has no bundled audio). Semantic search (`embed` / `index_build` / `search`) works with `--backend noop` without torch; CLAP is optional via `requirements-clap.txt`.

### Lint
- Ruff is configured in `pyproject.toml`; CI runs the pinned minimal static-correctness gate with `python -m ruff check .` in `.github/workflows/core-pytest.yml`.
- CLI smoke still uses `py_compile` on core modules plus CLI `--help` in `.github/workflows/ci-smoke.yml`.
