# ACTIVE_ROADMAP

## Current Status

- **Repository hygiene** (EPIC 0): completed
- **Documentation Architecture Sprint**: completed
  - [x] Product Requirements (`docs/PRODUCT_REQUIREMENTS.md`)
  - [x] System Requirements (`docs/SYSTEM_REQUIREMENTS.md`)
  - [x] Target Architecture (`docs/TARGET_ARCHITECTURE.md`)
  - [x] Data and Artifact Policy (`docs/DATA_AND_ARTIFACT_POLICY.md`)
  - [x] EPIC 2 Semantic Search Foundation Spec (`docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md`)
  - [x] DAW Integration Spec (`docs/DAW_INTEGRATION_SPEC.md`)
- **EPIC 1 — Config Profiles**: completed
  - [x] Config profile system (YAML, local override, gitignore)
  - [x] CLI `--profile` / `--config` global flags
  - [x] Config loader with env var overrides and validation
  - [x] `scan`, `embed`, `export_fl`, `autotype` wired to config
  - [x] `analyze` documented as DB-catalog special case
  - [x] No real local paths remain in committed code
  - [x] 14 unit tests for config loader
  - [x] README documentation for profiles, CLI overrides, env vars, precedence

## Current Focus: EPIC 2 — Semantic Search Foundation (Completed)

### Design & ADRs
- [x] ADR-0001: Embedding Model Strategy (CLAP) — Accepted
- [x] ADR-0002: Local Vector Index Strategy (FAISS) — Superseded by ADR-0004
- [x] ADR-0003: Embedding DB Schema Design — Accepted
- [x] ADR-0004: SQLite + sqlite-vec Search Backend — Accepted
- [x] ADR-0005: Search Quality Evaluation — Accepted

### Infrastructure on `main`
- [x] Idempotent DB schema extension (`embedding_models`, `sample_embeddings`)
- [x] Embedding backend interface (abstract base, no CLAP yet)
- [x] Embedding registry DB helpers
- [x] `iter_pending_samples()` — source-hash-aware pending sample query
- [x] `EmbeddingWorker.run()` — batch worker loop with DB persistence, dimension validation, per-sample error handling
- [x] CLI `--backend {noop,clap}` flag — wired via config profile or CLI override
- [x] Worker + DB tests (13 tests)
- [x] Guarded CLAP backend adapter (optional imports, CPU-first, no model download in CI)

### Index & Search Pipeline
- [x] Guarded CLAP backend on `main` — `ClapEmbeddingBackend` with lazy loading, 512-dim text/audio embedding, download-free `model_info()`, `[clap]` extra
- [x] NumPy vector index (`src/index.py`) — `build_numpy_index()`, `search_index()`, in-memory, cosine similarity; default search backend
- [x] sqlite-vec vec0 cache (`src/vec_index.py`, `src/search_backend.py`) — opt-in via `--search-backend sqlite-vec`; ADR-0004 accepted
- [x] Search backend adapter — `NumpySearchBackend`, `SqliteVecSearchBackend`; default `numpy`
- [x] Search backend contract wired — `run_search()` calls `get_backend()` → `embed_text()` → `search_index()` → ranked hits
- [x] CLI `search --backend {noop,clap}` — selects backend via CLI or profile config
- [x] CLI `search --index-path` — loads persisted `.npz` index instead of building from DB
- [x] CLI `index_build --model-id / --limit / --search-backend` — functional controlled command
- [x] CLI `search [query] --model-id / --topk / --backend / --search-backend / --index-path` — controls search flow
- [x] 33+ unit tests for index + search (24 index + 9 search)
- [x] NumPy `.npz` index persistence — `save_numpy_index()`, `load_numpy_index()`, `default_index_path()`
- [x] Index metadata validation — format_version, metric, dimension, model_id cross-check
- [x] CLI `index_build --save` — explicit persistence flag (no automatic writes)
- [x] CLI `index_build --index-path` — custom save path (implies `--save`)
- [x] Text-to-sample search — smoke proven (M4)
- [x] Audio-to-audio similarity search — implemented via `--query-audio`
- [x] sqlite-vec Phases 1–8 closed — campaigns complete
- [x] Search quality campaign — Tier A gates PASS (PR #54)
- [x] FAISS: superseded by ADR-0004 — never implemented on `main`

## Documentation Topics (vorgemerkt)

- `docs/SAMPLE_BRAIN_SKILLS_SPEC.md`

## Later: EPIC 3-6

- Hybrid ranking (BPM, key, type + vector similarity)
- FastAPI local service
- React/Tauri desktop UI
- DAW integration (FL Studio, Ableton, Reaper)
- DSP-based re-imagine / variant generator

---

> **Note:** Embedding pipeline (worker loop, no-op backend) is on `main`. NumPy vector index (in-memory + `.npz` persistence via `--save`) with cosine search is on `main`. sqlite-vec vec0 cache is opt-in via `[vec]` extra (ADR-0004). Search backend contract is wired — query embedding flows through `EmbeddingBackend.embed_text()`. A guarded `ClapEmbeddingBackend` is on `main`. FAISS is superseded (ADR-0002 kept as historical record). End-to-end semantic search with real vectors requires installed CLAP deps + populated embeddings/index.
