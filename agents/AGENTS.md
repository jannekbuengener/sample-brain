# AGENTS.md – Sample Brain

## Zweck
- Dieses Repo ist ein **lokal-first Audio-Sample-Toolkit** (Scan -> Analyze -> Autotype -> Export + optionale Embeddings/Search).
- Primäre Orchestrierung liegt in `src/cli.py` (argparse-basierte Commands).

## Rollenmodell
- Claude Code: Session Lead / Governance
- Codex: Execution / Implementation
- Gemini: Audit / Review
- Regel: Rollen nicht vermischen.

## Repo-Landkarte (relevante Arbeitsbereiche)
- `src/cli.py`: CLI-Entrypoint und Command-Dispatch.
- `src/config.py`: Projektpfade, `DB_PATH`, Audio-Defaults, Legacy-Fallbacks.
- `src/config_loader.py`: Profilauflösung (`config/profiles.example.yaml` + optional `profiles.local.yaml`) inkl. Env-Overrides.
- `src/db.py`: SQLite-Schema + DB-Helfer (Samples, Features, Embedding-Registry, Sample-Embeddings).
- `src/scan.py`: rekursiver Streaming-Scan, Audio-Metadaten, Hashing, Upsert nach `samples`.
- `src/analyze.py`: Feature-Extraktion mit librosa/soundfile, Upsert nach `features`.
- `src/classify.py`: regelbasierte Typisierung + optional kNN-Overlay, schreibt `features.pred_type`.
- `src/export_fl.py`: FL Studio Browser Tag-Export.
- `src/embed.py`: Embedding-Backends (`noop`, `clap`), Worker-Lauf, Persistenz nach `sample_embeddings`.
- `src/index.py`: Numpy-Cosine-Index bauen/speichern/laden/suchen.
- `src/search.py`: textbasierte Suche auf Basis Embeddings + Index.
- `tests/`: Abdeckung für Config, DB-Embedding-Flow, Worker, Index und Search-Fehlerpfade.

## Laufreihenfolge (fachlich)
- 1) `init` -> initialisiert DB/Tables.
- 2) `scan` -> befuellt/aktualisiert `samples`.
- 3) `analyze` -> befuellt/aktualisiert `features`.
- 4) `autotype` -> setzt `features.pred_type`.
- 5) `export_fl` -> schreibt FL-Tags.
- Optional:
- 6) `embed` -> schreibt `sample_embeddings`.
- 7) `index_build` -> erzeugt Numpy-Index.
- 8) `search` -> textuelle Aehnlichkeitssuche.

## Wichtige Datenvertraege
- SQLite-Datei standardmaessig: `data/catalog.db` (override via `SAMPLE_BRAIN_DB_PATH`).
- Kern-Tabellen:
- `samples(path UNIQUE, relpath, samplerate, channels, duration, size_bytes, hash)`
- `features(sample_id PK/FK, bpm, key, key_conf, loudness, brightness, mfcc/chroma blobs, class, pred_type)`
- `embedding_models(provider, model_name, model_version, embedding_dim, modality, UNIQUE(...))`
- `sample_embeddings(sample_id, model_id, embedding blob, embedding_format, source_hash, UNIQUE(sample_id, model_id, source_hash))`

## Konfiguration
- Basisprofil: `config/profiles.example.yaml`.
- Lokale Overrides: `config/profiles.local.yaml` (nicht committen).
- Relevante Env-Variablen:
- `SAMPLE_BRAIN_PROFILE`
- `SAMPLE_BRAIN_LIBRARY_ROOTS`
- `SAMPLE_BRAIN_FL_USER_DATA`
- `SAMPLE_BRAIN_MODEL_CACHE_DIR`
- `SAMPLE_BRAIN_DB_PATH`
- `SAMPLE_BRAIN_MAX_TAGS`
- `SAMPLE_BRAIN_EMBEDDING_BACKEND`

## Entwicklungs- und Testkommandos
- Setup:
- `py -3.12 -m venv .venv`
- `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- Smoke:
- `.\.venv\Scripts\python.exe -m src.cli init`
- `.\.venv\Scripts\python.exe -m src.cli scan --root <PATH>`
- `.\.venv\Scripts\python.exe -m src.cli analyze`
- Tests:
- `.\.venv\Scripts\python.exe -m pytest -q`

## Guardrails fuer Agenten
- Keine lokalen Secrets/Pfade in versionierte Dateien schreiben.
- Keine destruktiven Git-Aktionen ohne explizite Userfreigabe.
- Bei Config- oder Pfad-Features immer Profile + Env-Overrides mitdenken (nicht nur Hardcodes).
- DB-Schemaaenderungen nur zusammen mit Migration/Kompatibilitaetspruefung und angepassten Tests.
- Embedding/Search-Arbeit muss `noop`-Fallback und klare Fehlermeldungen beibehalten.
- Bei optionalen Abhaengigkeiten (`clap`/`torch`/`transformers`) fail-soft Verhalten erhalten.

## Nicht in `agents/` speichern
- Secrets, lokale Maschinenpfade, private Prompts, Working-Memory-Notizen, Tool-Logs, personenbezogene Daten.
