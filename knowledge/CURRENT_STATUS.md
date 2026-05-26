# CURRENT_STATUS

## Current State

- **Branch:** `main` — synchronised with `origin/main`
- **Working tree:** clean
- **Last commit:** `0c474e6 feat: add global profile config CLI flags`

## What Works (Core Pipeline)

- **Scan** — registers sample files in SQLite catalog
- **Analyze** — extracts audio features via librosa (BPM, key, loudness, brightness, MFCCs, chroma)
- **Autotype** — rule-based + optional kNN classification
- **Export** — writes smart tags into FL Studio Browser
- **Packaging** — `pyproject.toml` entry point (`sample-brain --help`) works
- **CLI** — argparse-based, 8 subcommands registered (4 core stable + 3 optional/experimental)

## Documentation Architecture Sprint — Completed

The following guardrail documents have been defined and committed:

| Document | Purpose |
|----------|---------|
| `PRODUCT_REQUIREMENTS.md` | Vision, audience, problem, MVP scope, non-goals |
| `SYSTEM_REQUIREMENTS.md` | Functional and non-functional requirements, data model, testing strategy |
| `TARGET_ARCHITECTURE.md` | Current vs target architecture, component boundaries, data flow, EPIC 2 design |
| `DATA_AND_ARTIFACT_POLICY.md` | Committed vs untracked artifacts, gitignore reference, enforcement |
| `EPIC_2_SEMANTIC_SEARCH_SPEC.md` | Embedding, index, search contracts; implementation sequence; acceptance criteria |
| `DAW_INTEGRATION_SPEC.md` | FL Studio export, Ableton/Reaper research, format specifications |

## What Exists on `main` for EPIC 2

- Embedding backend interface (`EmbeddingBackend` ABC)
- Embedding model registry + persistence helpers in `src/db.py`
- Embedding worker skeleton (no-op on `main`)
- Guarded CLAP backend stub (raises `EmbeddingBackendUnavailableError`)
- CLI subcommands `embed`, `index_build`, `search` registered with guarded imports
- **No FAISS, no real CLAP embedding, no search pipeline on `main`**

## CLAP Spike Status

- **Branch:** `spike/clap-embedding` — contains full CLAP prototype (optional deps, real embedding, DB persistence)
- **Status:** Parked / Draft — not merged to `main`. The spike validates ADR-0001 architecture decisions but is not production-ready.

## EPIC 1 — Config Profiles (In Progress)

- ✅ `config/profiles.example.yaml` created with placeholder paths
- ✅ `config/profiles.local.yaml` added to `.gitignore`
- ✅ `src/config_loader.py` — profile loading, merging, env overrides
- ✅ `embed --backend` CLI flag with `noop`/`clap` choices
- ✅ Backend resolution from config profile + env + CLI override
- ✅ Global `--profile` / `--config` CLI flags
- ✅ 14 unit tests for config loader
- ✅ README documentation for profiles, CLI overrides, env vars
- ❌ `scan --root` not wired yet
- ❌ `export_fl` / `analyze` not wired to config

## What Is Not Done

- EPIC 2 implementation (embed → index → search) — not started on `main`
- FAISS index builder — not imported, not implemented
- Search pipeline — not imported, not implemented
- EPIC 3-6 — not started

## Next Steps (empfohlen)

1. Wire `scan --root` CLI override to config profile
2. Continue EPIC 1 wiring for remaining subcommands (export_fl, analyze)
3. Begin EPIC 2 implementation sequence per spec
