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

## Global Rules
- Keep changes minimal, scoped, and reversible.
- Do not commit machine-local paths, secrets, private keys, or credentials.
- Respect config/profile indirection (`config/profiles.example.yaml` + optional local overrides) instead of hardcoding environment-specific values.
- Preserve graceful behavior for optional dependencies (especially embedding backends).
- Prefer updating tests together with behavior changes.

## Skill routing
- Skill routing: For agent task-to-skill mapping, use `docs/SKILL_INTEGRATION_PLAN.md`, `.cursor/rules/skill-routing.mdc`, and `SB.VERFUEGBARE.SKILLS.md`. These files provide recommendation/routing guidance only; they do not authorize automatic tool, workflow, CI, or security changes.

## Quality Gates
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
python -m pytest -q   # 138 tests; vec-specific tests skip without [vec]
```

Benchmark harness (local only, work-dir outside repo): `python -m src.cli benchmark vec --samples 1000 10000 100000 --work-dir /tmp/sample-brain-bench`. Gate evidence: [`docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md`](docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md). Default search backend remains **`numpy`** until all gates PASS.

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
pip install -r requirements.txt pytest
pip install -e .
python -m src.cli --help
sample-brain --help
python -m pytest -q
python -m py_compile src/analyze.py src/cli.py
```

### Bootstrap validation notes
- Fresh isolated venv bootstrap validation passed `pytest -q` (138 tests) without a repo-local `init`.
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
- No dedicated linter config in-repo. CI smoke = `py_compile` on core modules + CLI `--help` (see `.github/workflows/ci-smoke.yml`).
