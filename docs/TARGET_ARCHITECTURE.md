# Target Architecture — Sample Brain

## 1. Architecture Purpose

This document describes the target system architecture for Sample Brain. It serves as a blueprint and decision record, not an implementation log.

**Key principles:**

- **Current state (`main`) and target state are explicitly separated.** A reader must always be able to tell what exists today versus what is planned.
- **No implementation claim without evidence.** If a component is described in this document but does not exist in the codebase, it is clearly marked as planned or future.
- **Architecture decisions have traceable rationale.** References to ADRs and requirements documents link design to intent.
- **This document is a guardrail, not a cage.** It constrains the direction of incoming changes so they fit the target system, but it is reviewed and updated as the system evolves.

---

## 2. Current Architecture on `main`

### 2.1 Pipeline

```
Scan  →  Analyze  →  Autotype  →  Export
```

All four steps are implemented and stable.

### 2.2 Component Overview

| Component | Module | Status | Description |
|-----------|--------|--------|-------------|
| CLI Entry | `src/cli.py` (`main()`) | Stable | argparse-based; 8 subcommands registered, 4 stable (init, scan, analyze, autotype, export_fl), 3 guarded (embed, index_build, search), 1 pre-init (init) |
| Config | `src/config.py` | Stable | Project paths, DB path, sample roots, audio extensions, analysis parameters. Hardcoded `SAMPLE_ROOTS` is a known limitation. |
| Database | `src/db.py` | Stable | SQLAlchemy-based SQLite access. Tables: `samples`, `features`, `embedding_models` (schema only, no data), `sample_embeddings` (schema only, no data). |
| Scanner | `src/scan.py` | Stable | Recursive directory traversal, content hash dedup (SHA-1), streaming (no full list in memory), SQLite upsert. |
| Analyzer | `src/analyze.py` | Stable | librosa-based feature extraction: BPM (beat_track), key (chroma CQT), loudness (RMS), brightness (spectral centroid), MFCCs, chroma. Best-effort error handling per file. |
| Classifier | `src/classify.py` | Stable | Rule-based autotyping (duration, brightness, loudness, MFCC energy thresholds) + optional kNN on seed vectors. |
| Export | `src/export_fl.py` | Stable | FL Studio Browser tag file generation. Reads features from DB, assembles tag strings (type, character, key, BPM, loop/oneshot), writes to FL User Data path. |
| Embedding Interface | `src/embed.py` | Stable (interface) | `EmbeddingBackend` ABC, `NoopEmbeddingBackend` (raises on call), `ClapEmbeddingBackend` (stub — raises `EmbeddingBackendUnavailableError`), `EmbeddingWorker` (skeleton — no actual embedding loop). |
| Embedding DB | `src/db.py` | Stable (schema) | `embedding_models` and `sample_embeddings` tables exist. Registry helpers (`upsert_embedding_model`, `get_embedding_model`, `insert_sample_embedding`, `sample_embedding_exists`) are implemented. No `iter_pending_samples()` on `main`. |
| Index | `src/index.py` | **Does not exist on `main`** | CLI subcommand `index_build` is registered with guarded import (fails gracefully). |
| Search | `src/search.py` | **Does not exist on `main`** | CLI subcommand `search` is registered with guarded import (fails gracefully). |

### 2.3 What is on `main` vs what is only on `spike/clap-embedding`

| Capability | On `main` | On `spike/clap-embedding` |
|---|---|---|
| `--backend` CLI flag for embed | ❌ | ✅ |
| Real CLAP model loading + embedding | ❌ | ✅ (guarded, optional deps) |
| `iter_pending_samples()` DB helper | ❌ | ✅ |
| Full embedding worker loop | ❌ | ✅ |
| `requirements-clap.txt` / `[clap]` extra | ❌ | ✅ (optional dep group) |

The spike branch is a validated prototype. Its changes are **not** part of the `main` architecture and must be explicitly ported after review.

### 2.4 Known Technical Debt

- Hardcoded `SAMPLE_ROOTS` in `src/config.py` — no profile-based configuration yet
- No audio fixtures or test suite for pipeline steps
- `classify.py` imports `from .index import load_embeddings` — fails gracefully but couples autotype to a non-existent module
- `src/export_fl.py` hardcodes `SAMPLE_ROOTS` for path resolution
- No migration path for schema changes beyond `CREATE TABLE IF NOT EXISTS`

---

## 3. Target Pipeline

### 3.1 Current Pipeline (Stable)

```
Scan  →  Analyze  →  Autotype  →  Export
```

All four steps are implemented and stable on `main`.

### 3.2 Target Pipeline (EPIC 2 — Semantic Search Foundation)

```
Scan  →  Analyze  →  Embed  →  Index  →  Search  →  Export
```

Embed, Index, and Search are planned. Export will be extended with result metadata.

### 3.3 Long-term Pipeline (EPIC 3-6)

```
Scan  →  Analyze  →  Embed  →  Index  →  Search  →  Recommend  →  Export / DAW Workflow
```

Recommendation, API, and UI are future concerns (EPIC 3+).

### 3.4 Pipeline Step Contracts

| Step | Purpose | Input | Output | Source of Truth | Local Artifacts | Error Behaviour | Status |
|------|---------|-------|--------|-----------------|-----------------|-----------------|--------|
| **Scan** | Recursively discover audio files, compute content hash, store metadata | Directory root path | Rows in `samples` table | SQLite (`samples` table) | None (DB is local artifact) | Skip unsupported formats, continue on permission errors | **Current** |
| **Analyze** | Extract audio features via librosa | `samples` table (path, duration) | Rows in `features` table | SQLite (`features` table) | None | Skip corrupt audio per file, never crash pipeline | **Current** |
| **Autotype** | Classify by instrument type using rules + optional kNN | `features` table | `features.pred_type` updated | SQLite (`features.pred_type`) | None | kNN degrades gracefully if embeddings / seeds unavailable | **Current** |
| **Embed** | Generate per-sample embedding vectors via selected backend | `samples` table (audio file path) | Rows in `sample_embeddings` table | SQLite (`sample_embeddings`) + model registry (`embedding_models`) | Hugging Face model cache (`~/.cache/huggingface/`) | Embedding backend unavailable → clear error; per-file failure skip + report | **Planned** |
| **Index** | Build local vector index from stored embeddings | `sample_embeddings` table | FAISS index file | SQLite (`sample_embeddings`) is source of truth; FAISS is rebuildable cache | `data/indexes/<model>-<version>.faiss` + `.meta` | Not enough embeddings → clear message; index rebuild from scratch supported | **Planned** |
| **Search** | Resolve text or audio queries against the vector index | Text query or audio file path + FAISS index | Ranked list of sample paths + metadata + scores | SQLite (metadata enrichment after FAISS retrieval) | None (index is read-only during search) | No index → clear error; no results → empty list; backend unavailable → clear error | **Planned** |
| **Export** | Write DAW-compatible metadata tags | `features` table + `samples` table | FL Studio Browser tag file | SQLite (data source) | FL Studio tag file at user-specified location | Missing features → skip sample; continue with remaining | **Current** |
| **Recommend** | Suggest compatible samples based on context (future) | Sample/project context + features + embeddings | Ranked recommendation list | SQLite (source data) | None | N/A — future | **Future** |

---

## 4. Component Boundaries

### 4.1 CLI Layer (`src/cli.py`)

- **Responsibility:** Parse arguments, dispatch to pipeline modules, handle top-level errors
- **Must not do:** Contain pipeline logic, import heavy dependencies at module level
- **Inputs:** Command-line arguments
- **Outputs:** Exit code, stdout/stderr output
- **Dependency rule:** CLI imports pipeline modules lazily (inside `if args.cmd ==` blocks) to keep startup fast

### 4.2 Config / Profile Layer (`src/config.py`, future profile system)

- **Responsibility:** Provide project paths, sample roots, analysis parameters, model settings
- **Must not do:** Contain secrets, hardcode user-specific paths in committed code
- **Inputs:** (none at module level — read directly)
- **Outputs:** Paths and constants consumed by all pipeline modules
- **Status:** Current config is basic. Future profile system (EPIC 1) will replace hardcoded `SAMPLE_ROOTS`.

### 4.3 SQLite Catalog (`src/db.py`)

- **Responsibility:** Schema definition, engine creation, CRUD helpers for all entities
- **Must not do:** Import ML backends, contain pipeline orchestration logic
- **Inputs:** SQL queries via SQLAlchemy
- **Outputs:** Database file at `data/catalog.db` (untracked)
- **Tables:** `samples`, `features`, `embedding_models`, `sample_embeddings` (future: `embedding_jobs`, `vector_indexes`, `search_log`)

### 4.4 Scanner (`src/scan.py`)

- **Responsibility:** Recursive directory traversal, audio file detection, content hashing, deduplicated DB insertion
- **Must not do:** Analyze audio content, classify samples, write to export destinations
- **Inputs:** Directory root path(s)
- **Outputs:** Rows in `samples` table
- **Error handling:** Skip permission-denied directories, skip non-audio files, continue on corrupt files

### 4.5 Analyzer (`src/analyze.py`)

- **Responsibility:** Load audio, extract BPM, key, loudness, brightness, MFCCs, chroma; persist to `features` table
- **Must not do:** Classify, embed, search, export
- **Inputs:** Path from `samples` table + audio file on disk
- **Outputs:** Rows in `features` table
- **Error handling:** Best-effort per-file — never crash on corrupt audio

### 4.6 Classifier / Autotype (`src/classify.py`)

- **Responsibility:** Derive instrument-type tags from features using rules (+ optional kNN)
- **Must not do:** Extract features, embed audio, generate FL Studio tags directly
- **Inputs:** `features` table (duration, loudness, brightness, MFCCs, class)
- **Outputs:** Updates to `features.pred_type`
- **Dependency rule:** kNN path optionally imports `from .index import load_embeddings` — degrades gracefully if module is missing

### 4.7 Embedding Backend Interface (`src/embed.py`)

- **Responsibility:** Define `EmbeddingBackend` ABC, provide backend registry (`get_backend()`), worker orchestration
- **Must not do:** Own SQLite schema, contain export logic, force ML dependency installation
- **Inputs:** Audio file path or text query
- **Outputs:** `np.ndarray` (embedding vector)
- **Backend implementations:** `NoopEmbeddingBackend` (default, raises), `ClapEmbeddingBackend` (stub on `main`, real on spike branch)
- **Status on `main`:** Interface is stable. No real embedding occurs. CLAP stub raises `EmbeddingBackendUnavailableError`.

### 4.8 Embedding Worker (`src/embed.py` — `EmbeddingWorker`)

- **Responsibility:** Orchestrate batch embedding: query pending samples, iterate, call backend, persist to DB
- **Must not do:** Define schema, add business logic unrelated to embedding
- **Inputs:** `EmbeddingJobConfig` (backend name, limit, only_missing)
- **Outputs:** `EmbeddingRunResult` (processed/skipped/failed counts)
- **Status on `main`:** Skeleton — returns immediately for `NoopEmbeddingBackend`.

### 4.9 Vector Index Builder (future — `src/index.py`, EPIC 2)

- **Responsibility:** Read embeddings from SQLite, train/apply FAISS index, persist index file and metadata
- **Must not do:** Query the index, enrich search results, generate embeddings
- **Inputs:** `sample_embeddings` table
- **Outputs:** FAISS index file at `data/indexes/`

### 4.10 Search Layer (future — `src/search.py`, EPIC 2)

- **Responsibility:** Accept text or audio query, embed via selected backend, retrieve from FAISS index, enrich results from SQLite
- **Must not do:** Train indexes, generate embeddings for storage, autotype
- **Inputs:** Text query string or audio file path + top-k count
- **Outputs:** Ranked list of `(path, score, metadata)` tuples

### 4.11 Export Layer (`src/export_fl.py`)

- **Responsibility:** Read features from DB, assemble DAW-compatible tags, write to user-specified export location
- **Must not do:** Scan, analyze, classify, embed
- **Inputs:** `features` table + `samples` table + FL Studio User Data path
- **Outputs:** FL Studio Browser tag file at target path
- **Error handling:** Skip samples with missing features, continue with remaining

### 4.12 Future Components

| Component | EPIC | Purpose |
|-----------|------|---------|
| FastAPI Service | EPIC 4 | Local HTTP API around pipeline operations |
| Desktop UI | EPIC 4 | React/Tauri local desktop application |
| Recommendation Engine | EPIC 3 | Hybrid ranking combining vector similarity + structured metadata |
| DAW Workflow | EPIC 5 | Integration paths for Ableton, Reaper beyond FL Studio |
| Re-imagine Engine | EPIC 6 | DSP-based variant generation (pitch, time, stretch, reverse, slice) |

---

## 5. Data Flow

```
                         ┌──────────────┐
                         │  User selects │
                         │  library root │
                         └──────┬───────┘
                                │
                                ▼
 ┌──────────────────────────────────────────────────────┐
 │  1. Scan: discover audio files, compute hash,        │
 │     store metadata in SQLite (samples table)          │
 └──────────────────────────┬───────────────────────────┘
                            │
                            ▼
 ┌──────────────────────────────────────────────────────┐
 │  2. Analyze: load audio via librosa, extract         │
 │     BPM/key/loudness/brightness/MFCCs/chroma,        │
 │     persist to SQLite (features table)                │
 └──────────────────────────┬───────────────────────────┘
                            │
                            ▼
 ┌──────────────────────────────────────────────────────┐
 │  3. Autotype: derive instrument-type tags from       │
 │     features via rules (+ optional kNN),             │
 │     update features.pred_type                         │
 └──────────────────────────┬───────────────────────────┘
                            │
                            ▼
 ┌──────────────────────────────────────────────────────┐
 │  4. Embed: (planned) generate embedding vectors      │
 │     via selected backend (CLAP),                     │
 │     persist to sample_embeddings table                │
 └──────────────────────────┬───────────────────────────┘
                            │
                            ▼
 ┌──────────────────────────────────────────────────────┐
 │  5. Index: (planned) build FAISS index from stored   │
 │     embeddings, write to data/indexes/                │
 └──────────────────────────┬───────────────────────────┘
                            │
                            ▼
 ┌──────────────────────────────────────────────────────┐
 │  6. Search: (planned) embed query, retrieve from     │
 │     FAISS, enrich metadata from SQLite,              │
 │     return ranked results                             │
 └──────────────────────────┬───────────────────────────┘
                            │
                            ▼
 ┌──────────────────────────────────────────────────────┐
 │  7. Export: read features from SQLite, assemble      │
 │     DAW-compatible tags, write to user path           │
 └──────────────────────────────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │  All generated artifacts │
              │  stay local, untracked   │
              └─────────────────────────┘
```

**Key design property:** SQLite is the source of truth for all metadata. Generated artifacts (FAISS indexes, tag files, reports, caches) are always rebuildable from the SQLite catalog.

---

## 6. Source of Truth vs Generated Artifacts

### 6.1 Source of Truth (committed to Git)

| Artifact | Location | Purpose |
|----------|----------|---------|
| Source code | `src/` | All pipeline modules, CLI, config, DB helpers |
| Requirements | `requirements.txt`, `pyproject.toml` | Dependency pinning and metadata |
| Documentation | `docs/`, `knowledge/` | Product requirements, architecture, ADRs, roadmaps |
| Schema definitions | `src/db.py` | SQLite schema is defined in code (idempotent `CREATE TABLE IF NOT EXISTS`) |
| Configuration defaults | `src/config.py` | Pipeline parameters, audio extensions, analysis settings |
| Seed data | `data/label_seeds.csv` | Weak labels for kNN autotype (small, tracked intentionally) |
| Regex maps | `data/filename_tag_regex.json` | Filename-based tag inference rules (tracked intentionally) |

### 6.2 Local Runtime State (never committed)

| Artifact | Location | Rebuildable | Notes |
|----------|----------|-------------|-------|
| SQLite database | `data/catalog.db` | ✅ Yes (scan → analyze → autotype) | Single-file SQLite, created by `init` |
| Reports | `reports/` | ✅ Yes | Generated by validation/make scripts |
| HF model cache | `~/.cache/huggingface/` | ❌ Downloaded (one-time) | System-global, outside repo |
| FAISS index files | `data/indexes/` | ✅ Yes (from `sample_embeddings`) | Rebuildable via `index_build` |
| FL Studio tags | User-specified path | ✅ Yes (from DB) | Written by `export_fl` |

### 6.3 Policy Summary

- **Generated artifacts are never committed.** Any artifact that can be regenerated from source code + SQLite data must be excluded from version control.
- **`.gitignore` covers:** `.venv/`, `data/catalog.db`, `data/indexes/`, `reports/`, `data/models/`, `__pycache__/`, `*.pt`, `*.pth`, `*.safetensors`, `*.npy`, `*.npz`.
- **Only source code, documentation, configuration, and intentional seed data live in Git.**
- Detailed policy is specified in `docs/DATA_AND_ARTIFACT_POLICY.md`.

---

## 7. EPIC 2 Architecture

### 7.1 SQLite — Source of Truth for All Metadata

**Status on `main`:** Schema exists, helpers exist, no data flowing yet.

**Decision:** Embedding vectors are stored as BLOBs in SQLite (`sample_embeddings.embedding`). SQLite remains the single source of truth. FAISS is a rebuildable cache, not a primary store.

**Rationale (see ADR-0003):**
- Transactional integrity for sample-to-vector mappings
- Join compatibility with `features` and `samples` tables for hybrid search
- For <100k samples × 512 dims × 4 bytes ≈ 200 MB, SQLite is well within practical limits
- No additional infrastructure or background processes

**Key helpers implemented on `main`:**
- `upsert_embedding_model()` — register or retrieve embedding model
- `get_embedding_model()` — query model metadata
- `insert_sample_embedding()` — persist a single embedding
- `sample_embedding_exists()` — staleness check via `source_hash`

**Not on `main` (exists on spike branch):**
- `iter_pending_samples()` — query samples missing embeddings for a given model

### 7.2 CLAP — Preferred Embedding Backend

**Status on `main`:** Stub only. Real implementation on `spike/clap-embedding`.

**Decision:** LAION-CLAP is the primary embedding model candidate. The backend is abstracted behind `EmbeddingBackend` ABC to allow future substitution.

**Rationale (see ADR-0001):**
- Joint audio-text embedding space (enables both text-to-sample and audio-to-audio search)
- Pre-trained, open-source model (MIT license for most variants)
- 512-dim vectors compatible with FAISS
- Proven in producer/sample-search contexts

**Key constraints:**
- `torch` and `transformers` must remain **optional** dependencies — no runtime import in core pipeline
- CPU-first by default; CUDA is opt-in via `device` parameter
- Model download (~500 MB) happens on first use, user-visible, one-time
- The `ClapEmbeddingBackend` on `main` is a guarded stub — calling `embed_audio()` or `embed_text()` raises `EmbeddingBackendUnavailableError`

**Spike branch reference:** The full CLAP implementation lives on `spike/clap-embedding` and must be explicitly ported to `main` after review. It adds:
- Real `ClapModel.from_pretrained()` + `ClapProcessor.from_pretrained()` (Hugging Face `laion/clap-htsat-unfused`)
- `_load_model()` with guarded torch/transformers imports
- `embed_text()` and `embed_audio()` producing 512-dim `np.ndarray`
- Full `EmbeddingWorker.run()` loop with DB persistence
- CLI `--backend` flag

### 7.3 FAISS — Local Vector Index Cache

**Status on `main`:** Not imported. Not implemented. ADR-0002 documents design only.

**Decision:** FAISS (`faiss-cpu`) is the local vector index. It is a rebuildable cache — the source of truth remains SQLite.

**Rationale (see ADR-0002):**
- Industry standard for approximate nearest-neighbor search
- CPU-only (`faiss-cpu`) meets performance requirements
- IndexFlatIP (exact) and IndexIVFFlat (approximate) cover precision vs. speed trade-offs
- Local-only, no cloud dependency

**Index lifecycle:**
1. Read all embeddings from `sample_embeddings` table
2. Train index (IVF) or load directly (Flat)
3. Write index + metadata JSON to `data/indexes/`
4. On search: load index, query, map positions back to `sample_id`, enrich from SQLite
5. On staleness: rebuild from SQLite (index is disposable)

### 7.4 Search — Query and Retrieval

**Status on `main`:** Not implemented.

**Planned flow:**
```
Text query  ──►  Embed via CLAP  ──►  FAISS retrieval  ──►  Enrich from SQLite  ──►  Ranked results
Audio file  ──►  Embed via CLAP  ──►  FAISS retrieval  ──►  Enrich from SQLite  ──►  Ranked results
```

**Hybrid search (EPIC 3, future):** Vector similarity combined with BPM, key, type, and duration filters.

### 7.5 CLI Subcommands for EPIC 2

| Subcommand | Status on `main` | Behaviour |
|---|---|---|
| `embed` | Registered, guarded | Calls `run_embed(limit, only_missing)` with hardcoded `get_backend("noop")`. No real embeddings. |
| `index_build` | Registered, guarded | Imports `from .index import build_index` — fails gracefully (module does not exist). |
| `search` | Registered, guarded | Imports `from .search import run_search` — fails gracefully (module does not exist). |

---

## 8. Dependency Direction

### 8.1 Dependency Rules

```
CLI Layer
  │
  ▼
Pipeline modules (scan, analyze, classify, embed, export)
  │
  ▼
DB Layer (SQLAlchemy helpers)
  │
  ▼
Config Layer (paths, constants)
```

### 8.2 What must not import what

- **DB layer must not import ML backends** — `src/db.py` has no knowledge of CLAP, torch, or transformers
- **Embedding backend must not own SQLite schema** — `src/embed.py` imports DB helpers for persistence, but does not define schema
- **Analyzer must not classify** — feature extraction is separate from type inference
- **Classifier must not extract features** — reads from `features` table, never calls librosa
- **Export must not embed or classify** — reads from DB only
- **CLI must not import pipeline modules at module level** — lazy imports keep startup fast

### 8.3 Permitted cross-module calls

| Caller | Callee | Reason |
|--------|--------|--------|
| `cli.py` | `scan.run_scan()` | Dispatch |
| `cli.py` | `analyze.run_analyze()` | Dispatch |
| `cli.py` | `classify.write_autotype_to_db()` | Dispatch |
| `cli.py` | `export_fl.run_export()` | Dispatch |
| `cli.py` | `embed.run_embed()` | Dispatch |
| `scan.py` | `db.init_db()` | Ensure tables exist |
| `scan.py` | `db` helpers via SQLAlchemy | Data insertion |
| `analyze.py` | `db.init_db()` | Ensure tables exist |
| `analyze.py` | `db` helpers via SQLAlchemy | Data insertion |
| `classify.py` | `db.init_db()` | Ensure tables exist |
| `classify.py` | `db` helpers via SQLAlchemy | Data read/write |
| `classify.py` | `index.load_embeddings()` (optional, guarded) | kNN seed vectors |
| `embed.py` | `db` helpers | Model registration, embedding persistence |
| `export_fl.py` | `db.init_db()` | Ensure tables exist |
| `export_fl.py` | `db` helpers via SQLAlchemy | Data read |

### 8.4 No circular dependencies

The dependency graph is acyclic. No module imports a module that imports it back. If a cycle is detected during development, it must be resolved by extracting the shared concern into a lower-level module (typically `db.py` or `config.py`).

---

## 9. Local-first Architecture Rules

The following rules apply to all current and future components:

1. **No cloud dependency for core pipeline.** All operations from scan through export must work without any network access.
2. **No telemetry.** No analytics, usage tracking, or crash reporting built into any pipeline component.
3. **No sample upload.** Audio data never leaves the local filesystem as part of any core operation.
4. **Model downloads are explicit and optional.** ML model weights are downloaded on first use, not during installation. The user must explicitly opt in by installing optional dependencies and running the embedding pipeline.
5. **All generated artifacts are untracked.** SQLite DB, FAISS indexes, reports, caches, and model weights are excluded from version control.
6. **All state is rebuildable where possible.** The SQLite catalog is the source of truth. FAISS indexes, reports, and tag exports are caches that can be regenerated.
7. **Optional dependencies are import-guarded.** Core CLI and pipeline steps must never require torch, transformers, or any other heavy ML library at import time.

---

## 10. Future Architecture

### 10.1 FastAPI Local Service (EPIC 4)

A local HTTP API that wraps pipeline operations and search:
- Health endpoint
- Scan, analyze, embed, search endpoints
- Long-running operations with status reporting
- Local-only binding (127.0.0.1), no authentication in initial version

**Status:** Not implemented. Not planned before EPIC 2 completion.

### 10.2 Desktop UI (EPIC 4)

React/Tauri local desktop application with:
- Sample browser and search interface
- Audio preview
- Result inspection and export
- Local-first, no cloud backend

**Status:** Not implemented. Not planned before API stability.

### 10.3 Recommendation Engine (EPIC 3)

Hybrid ranking combining:
- Vector similarity (CLAP embeddings)
- Structured metadata (BPM, key, type, duration, loudness)
- Configurable weighting for semantic vs. metadata signals

**Status:** Not implemented. Not planned before semantic search stability.

### 10.4 DAW Workflow (EPIC 5)

Beyond FL Studio export:
- Ableton Live integration (`.alc` templates, tags)
- Reaper integration (metadata export)
- DAW-agnostic metadata formats

**Status:** Not implemented. FL Studio export is the only stable integration point.

### 10.5 Re-imagine Engine (EPIC 6)

DSP-based sample variant generation:
- Pitch shift, time stretch, reverse, slice
- Deterministic, local-only
- Bounded scope — no generative AI

**Status:** Not implemented. Research phase.

---

## 11. Non-Goals (Architecture Level)

The following are explicitly **not part of the target architecture** at any planned stage unless re-evaluated:

- **No cloud-first or hybrid architecture** — the system is designed for local-only operation. Cloud features, if any, are optional opt-in extras.
- **No sample marketplace** — no store, ratings, purchases, or community features.
- **No generative song production** — the system analyses, retrieves, and organises. It does not create music.
- **No committed audio samples** — `.wav`, `.mp3`, `.flac`, `.aiff` and similar files are never committed to the repository.
- **No committed DB/index/model/cache artifacts** — all generated state is untracked by design.
- **No FAISS or vector search in MVP** — semantic search is deliberately gated behind EPIC 2 and an explicit dependency decision.
- **No API or UI before CLI pipeline is reliable** — the CLI pipeline (scan → analyze → autotype → export) must be stable and tested before any API or UI layer is built.
- **No real-time audio processing** — the pipeline is batch-oriented. Real-time analysis within the DAW is not a goal.
- **No DAW plugin SDK** — integration happens through metadata export. VST3, AU, or AAX plugins are not planned.

---

## 12. Architecture Decision Links

| Document | What it covers |
|----------|---------------|
| `docs/PRODUCT_REQUIREMENTS.md` | Product vision, target audience, problem statement, MVP scope, non-goals, user stories |
| `docs/SYSTEM_REQUIREMENTS.md` | Functional requirements, non-functional requirements, system constraints, definition of done, data model, testing strategy |
| `knowledge/roadmap/adr/ADR-0001-embedding-model-strategy.md` | CLAP model selection rationale, backend abstraction design, dependency constraints, spike plan |
| `knowledge/roadmap/adr/ADR-0002-local-vector-index-strategy.md` | FAISS selection rationale, index lifecycle, artifact hygiene rules |
| `knowledge/roadmap/adr/ADR-0003-embedding-db-schema-design.md` | SQLite schema design for `embedding_models` and `sample_embeddings`, BLOB storage rationale, staleness detection |
| `knowledge/ACTIVE_ROADMAP.md` | Current implementation status, completed items, next focus areas |
| `knowledge/CURRENT_STATUS.md` | Daily/weekly status summary — what works, what is in progress, what is blocked |
| `docs/ISSUE_BACKLOG.md` | Granular task backlog across all epics |
