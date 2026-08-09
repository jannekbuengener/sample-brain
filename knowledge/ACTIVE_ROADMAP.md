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

## Track Deconstruction (#227-#268)

GitHub reconciliation complete. Five meta-parents define the full track-to-asset pipeline. Each parent decomposes into a docs contract (#232 Track Map is first) followed by runtime/research child issues. All are **OPEN** with no runtime implementation on `main`.

### Parent hierarchy and working order

```text
#227 [META][TRACK] Track Intelligence & Track Map
  ├── #232 Track Map JSON contract  [READY_TO_DOCUMENT] → docs/TRACK_MAP_V1.md
  ├── #233 One-shot context analyze runtime for arbitrary files
  ├── #234 Define canonical working WAV and shared timebase
  ├── #237 Add cache and provenance for expensive track analysis
  ├── #236 BeatGrid backend adapter (Beat This final0 provisional; librosa fallback)
  ├── #235 Evaluate All-In-One structure analysis (comparison only, not Core)
  └── #265 StructureV1 bar-synchronous boundary backend

#228 [META][STRUCTURE] Musical Structure & Techno Arrangement Understanding
  ├── #238 Define Techno arrangement role vocabulary v1
  ├── #239 Define Track Map signals for Techno arrangement roles
  ├── #241 Define arrangement confidence and manual override contract
  ├── #240 Implement Techno arrangement heuristic classifier v1
  ├── #242 Run Techno arrangement pilot on private tracks
  └── #243 Add optional CLAP semantic signal for arrangement roles

#229 [META][STEMS] Stem Separation for Track Deconstruction
  ├── #244 Define stem backend and output contract
  ├── #245 Spike python-audio-separator integration
  ├── #246 Benchmark stem models on private Techno tracks
  ├── #247 Select default and quality stem backends
  ├── #248 Add stem cache and model provenance
  └── #249 Integrate optional stem pipeline into Track Deconstruction

#230 [META][ASSETS] Intelligent Loop & Section Asset Generation
  ├── #250 Define loop and section asset manifest contract
  ├── #251 Generate bar-aligned 4/8/16-bar loop candidates
  ├── #266 Generate section asset candidates from Arrangement Map
  ├── #252 Score loop candidates v1
  ├── #267 Score section asset candidates v1
  ├── #268 Producer-oriented stem grouping (kick_bass etc.)
  ├── #255 Add stem-based asset candidate generation
  ├── #253 Render deterministic loops and sections
  ├── #254 Re-analyze generated assets and attach metadata
  └── #256 Run Techno asset quality and quantity pilot

#231 [META][PACK] Song to Sample / Performance Pack
  ├── #257 Define Performance Pack manifest schema v1
  ├── #258 Define standard pack directory and file naming
  ├── #259 Build headless Track Deconstruction orchestrator
  ├── #260 Integrate Track Map, arrangement and asset outputs
  ├── #261 Integrate optional stem outputs into Performance Pack
  ├── #262 Add idempotency, resume and cache reuse
  ├── #263 Add Performance Pack re-import and Library compatibility
  └── #264 Run end-to-end Track Deconstruction pilot
```

### Status snapshots

| Parent | Track Map doc | Runtime | Notes |
|--------|---------------|---------|-------|
| #227 Track Intelligence | [docs/TRACK_MAP_V1.md](../docs/TRACK_MAP_V1.md) (`schema_version 1.0.0`) | #233-#237, #236, #265 OPEN | Track Map contract documented in docs (#232 `OPEN` / `READY_TO_DOCUMENT`, pending PR merge); runtime follow-up (#233, #236, #265) |
| #228 Structure/Arrangement | Not started | #238-#243 OPEN | Role vocabulary (#238) before heuristic classifier (#240) |
| #229 Stem Separation | Not started | #244-#249 OPEN | `python-audio-separator` wrapper; `htdemucs`/`htdemucs_ft` baselines; exact checkpoint/license review required (#246) |
| #230 Asset Generation | Not started | #250-#256, #266, #267 OPEN | Loop/section candidates separated; `kick_bass` = kick + musical bassline (#268) |
| #231 Performance Pack | Not started | #257-#264 OPEN | Pack manifest aggregates Track Map + Arrangement + Stems + Assets as separate references |

### Research decisions (recorded, not implemented)

- **Beat/Downbeat:** Beat This `final0` is provisional primary candidate (#236); `librosa` is the lightweight fallback. Not yet confirmed by private Techno audio tests.
- **Structure:** StructureV1 (#265) uses classical audio analysis (self-similarity, recurrence, novelty, energy/low-end/onsets/timbre). No large Techno model as Core.
- **All-In-One:** #235 is comparison/experimental only — not a Core path.
- **Stems:** `python-audio-separator` is the integration wrapper; `htdemucs`/`htdemucs_ft` are provisioneral baselines. Exact checkpoint/weight-license review required before any default selection.
- **Loops:** No own ML model for loop selection; candidates are bar-aligned from downbeat indices.
- **Producer groups:** `kick_bass` = kick attack/body + musical bassline, not `drums + bass` (#268). No perfect mixer-spur reconstruction promised.
- **Private test data:** Own tracks and sample library exist for private pilots; no private audio, paths, or outputs in repo documentation.

### Technical separation chain

```text
Track Map v1 (identity + neutral analysis)
  → Arrangement Map (Techno roles over neutral boundaries)
  → technical Stems (drums/bass/vocals/other — raw model output)
  → Producer Groups (kick_bass, melodic, etc. — musical interpretation)
  → Producer Assets (loops, sections — rendered, deterministic)
  → Performance Pack (manifest aggregating all above)
```

Each link has its own contract and cache. Technical stems ≠ producer assets.

## Documentation Topics (vorgemerkt)

- `docs/SAMPLE_BRAIN_SKILLS_SPEC.md`
- `docs/TRACK_MAP_V1.md` — canonical Track Map v1 contract (#232, parent #227)

## VST-first Product Target (Issues #90–#95)

The product target has been redefined from FL-Browser-first to **VST3-first producing intelligence** with 5 pillars:

- **[LIBRARY]** Library Intelligence and Metadata/Naming Engine — [#94](https://github.com/jannekbuengener/sample-brain/issues/94)
- **[MATCHING]** Harmonic and Rhythmic Matching — [#91](https://github.com/jannekbuengener/sample-brain/issues/91)
- **[CONTEXT]** Track Context Analysis — [#95](https://github.com/jannekbuengener/sample-brain/issues/95)
- **[TRANSFORM]** Realtime Fit and Transform Engine — [#92](https://github.com/jannekbuengener/sample-brain/issues/92)
- **[WORKSPACE]** VST-first Producing Workspace — [#93](https://github.com/jannekbuengener/sample-brain/issues/93)

FL Studio Browser export becomes **legacy/fallback** — not the main product path.

## Later: EPIC 3-6

- Hybrid ranking (BPM, key, type + vector similarity)
- FastAPI local service
- Standalone producing app (from same core as VST3 plugin)
- DAW integration (Ableton, Reaper — beyond VST3)
- DSP-based re-imagine / variant generator

---

> **Note:** Embedding pipeline (worker loop, no-op backend) is on `main`. NumPy vector index (in-memory + `.npz` persistence via `--save`) with cosine search is on `main`. sqlite-vec vec0 cache is opt-in via `[vec]` extra (ADR-0004). Search backend contract is wired — query embedding flows through `EmbeddingBackend.embed_text()`. A guarded `ClapEmbeddingBackend` is on `main`. FAISS is superseded (ADR-0002 kept as historical record). End-to-end semantic search with real vectors requires installed CLAP deps + populated embeddings/index.
