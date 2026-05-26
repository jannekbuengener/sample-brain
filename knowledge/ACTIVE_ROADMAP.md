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

### P2 — Index & Search Pipeline (not yet started on main)
- [ ] CLAP backend spike — exists on `spike/clap-embedding` as parked prototype (not merged)
- [ ] FAISS index build module
- [ ] Text-to-sample search
- [ ] Audio-to-audio similarity search

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

> **Note:** Features listed under P2 are not yet implemented on `main`. The codebase currently supports: Scan → Analyze → Autotype → Embed (worker loop, no-op backend) → Export. A CLAP prototype exists on `spike/clap-embedding` as a parked review branch. FAISS index and search are not yet implemented.
