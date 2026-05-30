# AGENTS.md - Root Scope

## Purpose
- This file defines global agent guidance for the whole `sample-brain` repository.
- Deeper `AGENTS.md` files override and refine rules for their own subtree.

## Scope Map
- `src/` -> implementation and runtime logic (`src/AGENTS.md`)
- `tests/` -> unit/integration test expectations (`tests/AGENTS.md`)
- `docs/` -> product/architecture/process docs (`docs/AGENTS.md`)
- `agents/` -> shared cross-agent charter (`agents/AGENTS.md`)

## Project Baseline
- Stack: Python (3.12+), sqlite, librosa/soundfile, numpy/scipy, sqlalchemy.
- CLI entrypoint: `src/cli.py`.
- Main flow: `init -> scan -> analyze -> autotype -> export_fl` (optional: `embed -> index_build -> search`).

## Global Rules
- Keep changes minimal, scoped, and reversible.
- Do not commit machine-local paths, secrets, private keys, or credentials.
- Respect config/profile indirection (`config/profiles.example.yaml` + optional local overrides) instead of hardcoding environment-specific values.
- Preserve graceful behavior for optional dependencies (especially embedding backends).
- Prefer updating tests together with behavior changes.

## Skill routing
- Skill routing: For agent task-to-skill mapping, use `docs/SKILL_INTEGRATION_PLAN.md` and `.cursor/rules/skill-routing.mdc`. These files provide recommendation/routing guidance only; they do not authorize automatic tool, workflow, CI, or security changes.

## Quality Gates
- Setup:
- `py -3.12 -m venv .venv`
- `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- Verify:
- `.\.venv\Scripts\python.exe -m pytest -q`
- CLI smoke:
- `.\.venv\Scripts\python.exe -m src.cli init`

## Handover Notes
- When changing DB schema in `src/db.py`, validate affected read/write paths in `scan`, `analyze`, `classify`, `embed`, `index`, and their tests.
- When changing CLI args in `src/cli.py`, keep behavior and help text coherent across related commands.

## Cursor Cloud specific instructions

### Product shape
- **sample-brain** is a single-process Python CLI (no web server, no Docker). End-to-end testing is sequential CLI invocation, not service startup.
- Entry point: `python -m src.cli` (or `.venv/bin/python -m src.cli` on Linux).

### One-time VM prerequisites (not in update script)
- Ubuntu/Debian: `python3.12-venv` must be installed (`sudo apt-get install -y python3.12-venv`) before the first venv creation.
- Audio I/O: `libsndfile1` is required for real `analyze` runs (usually preinstalled on Ubuntu).

### Dependency refresh (automatic on startup)
- See the VM update script: creates/refreshes `.venv`, installs `requirements.txt` + `pytest`.
- `pytest` is **not** listed in `requirements.txt`; install it alongside requirements for local/Cloud verification.

### Verify (Linux paths)
```bash
source .venv/bin/activate   # optional
python -m src.cli init
python -m pytest -q
python -m py_compile src/analyze.py src/cli.py
python -m src.cli --help
```

### pytest gotcha
- Run `python -m src.cli init` once before the full test suite if `data/catalog.db` is missing or empty (0 bytes). Otherwise `tests/test_index.py::TestBuildIndexCLI::test_build_index_save_without_path_prints_info` can fail with `no such table: sample_embeddings`.

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
- No dedicated linter config in-repo. CI smoke = `py_compile` on core modules + CLI `--help` (see `.github/workflows/ci-smoke.yml`).
