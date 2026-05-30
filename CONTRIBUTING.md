# Contributing

## Regeln
- Arbeit ueber Issues + PRs
- PRs klein halten, Scope klar
- Tests/Lint lokal laufen lassen
- Evidence in PR Beschreibung

## Definition of Done (kurz)
- CI gruen
- Risk/Impact beschrieben
- Rollback kurz beschrieben (wenn relevant)

## Lokale Verifikation (Bootstrap)

Fresh checkout → isolated venv → verify. Keep runtime artifacts **outside** the repo.

```bash
# 1) Venv (outside repo recommended)
python3.12 -m venv /tmp/sample-brain-verify-venv
source /tmp/sample-brain-verify-venv/bin/activate

# 2) Install
pip install --upgrade pip
pip install -r requirements.txt pytest
pip install -e .

# 3) CLI
python -m src.cli --help
sample-brain --help

# 4) Tests
python -m pytest -q

# 5) External DB init (no committed catalog.db)
export SAMPLE_BRAIN_DB_PATH=/tmp/sample-brain-verify/catalog.db
python -m src.cli init

# 6) Optional synthetic WAV smoke (generate WAV outside repo first)
python -m src.cli scan --root /tmp/sample-brain-verify-fixtures
python -m src.cli analyze
```

**Linux:** install `libsndfile1` for analyze; if `python -m venv` fails, use `virtualenv`.

**Do not commit:** `.venv/`, `data/catalog.db`, indexes, model caches, private sample paths, or other generated runtime artifacts.

See [`README.md`](./README.md#bootstrap--fresh-setup-validation) for the full bootstrap notes.
