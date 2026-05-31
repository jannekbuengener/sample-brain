# AGENTS.md - tests Scope

## Scope
- Applies to all files under `tests/`.

## Testing Philosophy
- Tests should validate behavior contracts, not incidental implementation details.
- Keep tests deterministic, fast, and isolated (use fixtures/mocks instead of real external dependencies).
- Prefer explicit assertions on error messages for controlled failure paths.

## Current Coverage Focus
- Config/profile resolution and env overrides (`test_config_loader.py`, `test_config_db_path.py`)
- Embedding DB selection flow (`test_db_embeddings.py`)
- Embedding worker success/failure accounting (`test_embed_worker.py`)
- Index serialization/validation and search ranking/validation (`test_index.py`, `test_search.py`)
- CLAP backend availability/error semantics (`test_clap_backend.py`)

## Rules for New or Updated Tests
- Co-locate new tests with the nearest existing concern area.
- When behavior changes in `src/`, update or add the narrowest test that proves the new contract.
- Use meaningful fixture names and avoid hidden shared mutable state.
- Keep mocked expectations resilient (assert intent, not call noise).

## Synthetic Audio Fixtures
- Generate WAV fixtures at runtime in temp directories; do not commit audio binaries.
- Use `tests/audio_fixtures.py` helpers for deterministic synthetic signals.
- Keep catalog writes isolated by monkeypatching `src.db.DB_PATH` to a `tmp_path` location.
- Assert behavior contracts (`scan`/`analyze` no-crash + DB rows), not exact BPM/key values.

## Execution
- Run all tests:
- `.\.venv\Scripts\python.exe -m pytest -q`
- During debugging, run targeted files first, then full suite.
