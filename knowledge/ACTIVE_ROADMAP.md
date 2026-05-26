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

## Next Focus: EPIC 2 — Semantic Search Foundation

### Design & ADRs
- [x] ADR-0001: Embedding Model Strategy (CLAP)
- [x] ADR-0002: Local Vector Index Strategy (FAISS)
- [x] ADR-0003: Embedding DB Schema Design

### Infrastructure on `main`
- [x] Idempotent DB schema extension (`embedding_models`, `sample_embeddings`)
- [x] Embedding backend interface (abstract base, no CLAP yet)
- [x] Embedding registry DB helpers
- [x] `iter_pending_samples()` — source-hash-aware pending sample query
- [x] `EmbeddingWorker.run()` — batch worker loop with DB persistence, dimension validation, per-sample error handling
- [x] CLI `--backend {noop,clap}` flag — wired via config profile or CLI override
- [x] Worker + DB tests (13 tests)
- [x] Guarded CLAP backend adapter (optional imports, CPU-first, no model download in CI)

### P2 — Index & Search Pipeline (NumPy skeleton + persistence on main, FAISS deferred)
- [ ] CLAP backend spike — exists on `spike/clap-embedding` as parked prototype (not merged)
- [x] NumPy vector index skeleton (`src/index.py`) — `build_numpy_index()`, `search_index()`, in-memory, cosine similarity
- [x] Controlled search skeleton (`src/search.py`) — `run_search()` with CLAP-required message
- [x] CLI `index_build --model-id / --limit` — functional controlled command
- [x] CLI `search [query] --model-id / --topk` — functional controlled skeleton
- [x] 24 unit tests for index + search (14 in-memory + 10 persistence)
- [x] NumPy `.npz` index persistence — `save_numpy_index()`, `load_numpy_index()`, `default_index_path()`
- [x] Index metadata validation — format_version, metric, dimension, model_id cross-check
- [x] CLI `index_build --save` — explicit persistence flag (no automatic writes)
- [x] CLI `index_build --index-path` — custom save path (implies `--save`)
- [ ] FAISS index build module — deferred until NumPy contract stable
- [ ] Text-to-sample search — blocked by real query embedding
- [ ] Audio-to-audio similarity search — blocked by real CLAP backend

## Future Doku-Stränge (vorgemerkt)

- `docs/BOOTLOADER_AND_CONTEXT_STRATEGY.md`
- `docs/SAMPLE_BRAIN_SKILLS_SPEC.md`

## Later: EPIC 3-6

- Hybrid ranking (BPM, key, type + vector similarity)
- FastAPI local service
- React/Tauri desktop UI
- DAW integration (FL Studio, Ableton, Reaper)
- DSP-based re-imagine / variant generator

---

> **Note:** Embedding pipeline (worker loop, no-op backend) is on `main`. NumPy vector index (in-memory + `.npz` persistence via `--save`) with cosine search is on `main`. FAISS is deferred. A CLAP prototype exists on `spike/clap-embedding` as a parked review branch. Real end-to-end semantic search is not yet implemented (blocked by query embedding backend).
