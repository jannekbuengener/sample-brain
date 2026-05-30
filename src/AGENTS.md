# AGENTS.md - src Scope

## Scope
- Applies to all files under `src/`.

## Architecture Contracts
- `cli.py` is the command dispatcher; keep command behavior explicit and predictable.
- `config_loader.py` owns profile resolution and environment overrides.
- `config.py` owns path defaults and legacy-safe constants.
- `db.py` owns schema and data access helpers.
- Pipeline modules:
- `scan.py` -> sample metadata ingestion
- `analyze.py` -> audio feature extraction
- `classify.py` -> autotyping (`pred_type`)
- `export_fl.py` -> FL tags output
- Retrieval modules:
- `embed.py`, `index.py`, `search.py`

## Implementation Rules
- Prefer small, isolated function changes over broad rewrites.
- Keep fail-soft behavior where the code intentionally degrades gracefully (missing optional modules/backends).
- Avoid implicit coupling: pass explicit args where possible instead of introducing hidden globals.
- Maintain command-line UX consistency (arg names, defaults, error style).

## Data and Schema Safety
- Any table/column change in `db.py` must preserve compatibility or include coordinated updates in all affected readers/writers.
- Keep `sample_embeddings` invariants intact (`sample_id`, `model_id`, `source_hash` uniqueness semantics).
- Do not weaken uniqueness or FK relationships without clear migration intent.

## Performance and IO
- Preserve stream-oriented scan behavior in `scan.py` (avoid loading full library lists into memory).
- Avoid unnecessary re-reads of large binary/audio payloads.
- Keep numpy dtype assumptions (`float32`) stable across embed/index/search boundaries.

## Verification
- Minimum after non-trivial `src/` changes:
- `.\.venv\Scripts\python.exe -m pytest -q`
- For CLI-affecting changes, run at least one matching CLI smoke command (for example `init` or `search` path, depending on scope).
