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
