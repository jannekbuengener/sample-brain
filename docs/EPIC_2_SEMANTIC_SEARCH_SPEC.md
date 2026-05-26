# EPIC 2 — Semantic Search Foundation Spec

## 1. Purpose

EPIC 2 builds the foundation for semantic sample search. It extends the current pipeline from `Scan → Analyze → Autotype → Export` to `Scan → Analyze → Embed → Index → Search`.

The goal is not "AI magic" but **local, explainable, reproducible sample intelligence**. Every step is designed so a producer can understand what the system knows, how it knows it, and where its limits are.

EPIC 2 delivers three new capabilities:
- **Embed** — generate per-sample embedding vectors via a pluggable backend
- **Index** — build a local vector index for fast similarity search
- **Search** — resolve natural language or audio queries against the catalog

---

## 2. Scope

### In scope

- Embedding model registry with version tracking
- Per-sample embedding storage in SQLite
- Pluggable embedding backend interface (CLAP as primary candidate)
- Batch embedding worker with progress reporting and failure resume
- Local FAISS vector index, rebuildable from SQLite
- Text-to-sample semantic search
- Audio-to-audio similarity search
- Metadata enrichment from SQLite on search results
- CLI subcommands: `embed`, `index_build`, `search`
- Optional `[clap]` dependency extra
- Import-guarded ML libraries (core works without torch/transformers)

### Out of scope (EPIC 2)

- Recommendation engine (EPIC 3)
- Hybrid ranking blending vector + structured metadata (EPIC 3)
- Local HTTP API / FastAPI service (EPIC 4)
- Desktop UI (EPIC 4)
- Cloud sync or multi-user features
- Model training or fine-tuning
- Sample generation or transformation (EPIC 6)
- Committing DB, index, model, or cache artifacts to version control
- Real-time audio analysis
- DAW plugin SDK

---

## 3. Current `main` Status

The following EPIC 2 infrastructure already exists on `main`:

| Component | Status on `main` | Detail |
|-----------|-----------------|--------|
| **SQLite catalog** | ✅ Stable | `samples`, `features` tables with CRUD helpers |
| **Embedding schema** | ✅ Stable | `embedding_models` and `sample_embeddings` tables created by `init_db()` (empty, no data flowing) |
| **Model registry** | ✅ Stable | `upsert_embedding_model()`, `get_embedding_model()` implement INSERT OR IGNORE and query |
| **Embedding persistence** | ✅ Stable | `insert_sample_embedding()`, `sample_embedding_exists()` implement BLOB storage and staleness check via `source_hash` |
| **Backend interface** | ✅ Stable | `EmbeddingBackend` ABC with `embed_audio()`, `embed_text()`, `model_info()` |
| **Worker DB persistence** | ✅ Stable | `EmbeddingWorker.run()` iterates pending samples, calls backend, persists BLOB, reports processed/skipped/failed |
| **CLAP stub** | ✅ Committed | `ClapEmbeddingBackend` — all methods raise `EmbeddingBackendUnavailableError`. No real embedding. |
| **CLI subcommands** | ✅ Registered | `embed`, `index_build`, `search` are registered with guarded imports. Fail gracefully if modules are missing. |
| **`iter_pending_samples()`** | ✅ Done | Source-hash-aware query — returns samples missing current embeddings for a given model |
| **`--backend` CLI flag** | ✅ Done | `embed --backend {noop,clap}` — wired via config profile or CLI override |
| **NumPy vector index** | ✅ NumPy skeleton | `src/index.py` — `build_numpy_index()`, `search_index()`, in-memory, cosine similarity. No FAISS dependency. |
| **Index persistence** | ✅ `.npz` save/load | `save_numpy_index()`, `load_numpy_index()`, `default_index_path()` — writes to `data/indexes/`. Metadata validated on load. |
| **Index CLI** | ✅ Controlled command | `index_build --model-id / --limit / --save / --index-path` — loads embeddings, builds index, persists only with `--save`. |
| **Search contract** | 🔶 Controlled skeleton | `src/search.py` — `run_search()` prints info that CLAP backend is required. No real query embedding. |
| **Search CLI** | 🔶 Controlled skeleton | `search [query] --model-id / --topk` — prints search instructions but cannot embed queries without CLAP. |
| **FAISS index** | ❌ Not integrated | ADR-0002 documents the design. Deferred — NumPy `.npz` is the current persistence format. |
| **Text-to-sample search** | ❌ Not implemented | Blocked by real query embedding backend. NumPy search contract exists for when embeddings arrive. |

---

## 4. Spike Status (`spike/clap-embedding`)

The branch `spike/clap-embedding` (PR #10) contains a validated prototype of the CLAP embedding path. It is:

- **Experimental** — for validation and review
- **Not merged to `main`** — kept as a reference implementation
- **Not production-ready** — requires review, hardening, and testing before it can be considered stable

### What remains on the spike (not on `main`)

| Capability | Branch |
|---|---|
| `ClapModel.from_pretrained()` + `ClapProcessor.from_pretrained()` | `spike/clap-embedding` |
| Real `embed_text()` and `embed_audio()` returning 512-dim vectors | `spike/clap-embedding` |
| `requirements-clap.txt` and `[clap]` optional extra | `spike/clap-embedding` |

The following capabilities previously exclusive to the spike have been ported to `main`:
- `--backend {noop,clap}` CLI flag
- `iter_pending_samples()` DB helper
- `EmbeddingWorker.run()` loop with DB persistence

### Spike status

- The spike is **complete** — all acceptance criteria from ADR-0001 are met
- The spike is **parked** — not being actively merged or rebased
- Porting spike changes to `main` is a deliberate step that requires review, not an automatic merge
- The spike validates the architecture decisions in ADR-0001 and ADR-0003

---

## 5. MVP Definition for EPIC 2

EPIC 2 MVP is reached when:

### Must have

1. Embedding model metadata is registered in SQLite on first use
2. Sample embeddings are computed reproducibly (same sample + same model → same vector)
3. Embeddings are persisted as BLOBs in `sample_embeddings` table
4. A vector index (NumPy cosine similarity skeleton on `main`; FAISS pending) can be built from stored embeddings via a CLI command
5. A text query can be embedded and searched against the index, returning ranked sample paths (blocked by real query embedding backend)
6. Search results include sample metadata (BPM, key, type, path) enriched from SQLite
7. All generated artifacts (DB, index files) remain local and untracked
8. Core CLI (`--help`, `init`, `scan`, `analyze`, `autotype`, `export_fl`) works without torch/transformers

### Nice to have (MVP+)

- Audio-to-audio similarity search
- Index metadata tracking (model_id, build time, sample count)
- Resumable batch embedding after interruption

### Not required for MVP

- Perfect ranking quality (useful results are sufficient)
- Desktop or web UI
- HTTP API
- Multiple embedding backends beyond CLAP
- Recommendation engine or "you might also like" features
- Hybrid ranking with structured metadata
- Batch performance optimisation for libraries >100k samples
- GPU acceleration

---

## 6. Production-Ready Definition

A component or pipeline step is considered production-ready when:

| Criterion | Description |
|-----------|-------------|
| **Clear CLI contract** | The subcommand has documented arguments, help text, and expected behaviour |
| **Import guards** | No ML library is imported at module level. Core pipeline runs without torch/transformers. |
| **Reproducible model metadata** | Model registration captures provider, name, version, dimension, modality |
| **Staleness detection** | Embedding existence is checked via `source_hash` — re-embedding is triggered when sample content changes |
| **Resumable worker** | Batch embedding can be interrupted and resumed without duplicating or losing work |
| **Robust error handling** | A single corrupt or unsupported file does not crash the pipeline. Failures are reported per sample. |
| **No private data in tests** | Test fixtures are synthetic (generated, not sampled from libraries) |
| **No generated artifacts in git** | `git status` is clean after any pipeline run |
| **Documented artifact paths** | All local artifacts (DB, indexes, caches) are documented in the artifact policy |
| **Core smoke checks** | `sample-brain --help` and pipeline entry points work without optional dependencies |
| **Optional CLI smoke checks** | Embedding/index/search subcommands load and report errors clearly without crashing |

---

## 7. Implementation Sequence

| # | Step | Description | Depends On | Status on `main` | Acceptance Criteria |
|---|------|-------------|------------|-------------------|---------------------|
| 1 | DB schema for embeddings | `embedding_models` + `sample_embeddings` tables | — | ✅ Done | Tables created by `init_db()`, unique constraints enforced |
| 2 | Embedding backend interface | `EmbeddingBackend` ABC with `embed_audio()`, `embed_text()`, `model_info()` | — | ✅ Done | Interface defines contract; `NoopEmbeddingBackend` raises clear errors |
| 3 | Model registry helpers | `upsert_embedding_model()`, `get_embedding_model()` | Step 1 | ✅ Done | Models registered with unique constraint, queryable |
| 4 | Embedding persistence helpers | `insert_sample_embedding()`, `sample_embedding_exists()` | Step 1 | ✅ Done | Embeddings stored as BLOB, staleness checked via `source_hash` |
| 5 | Pending sample selection | `iter_pending_samples()` — query samples missing embeddings | Steps 1, 4 | ✅ Done | Returns sample IDs not yet embedded for a given model; source-hash-aware staleness detection |
| 6 | Batch embedding worker | `EmbeddingWorker.run()` — iterate pending samples, call backend, persist | Steps 4, 5 | ✅ Done | Processes N samples, reports processed/skipped/failed, resumable |
| 7 | CLI `--backend` flag | `embed` subcommand accepts `--backend {noop,clap}` | Step 6 | ✅ Done | Backend selected via CLI, defaults to `"noop"` |
| 8 | Optional CLAP backend | `ClapEmbeddingBackend` with real model loading | Step 2 | ❌ Stub on `main`, real on spike | `_clap_available()` check, guarded imports, 512-dim vectors, no CI model download |
| 9 | NumPy index persistence | `save_numpy_index()` — write `.npz` with vectors, sample_ids, metadata | Steps 4, 8 | ✅ `.npz` persistence | Index file written to `data/indexes/` via `--save`. Metadata: format_version, backend, model_id, dim, metric, normalized, sample_count, created_at. |
| 10 | Text search embedding | `backend.embed_text()` for search queries | Steps 2, 8 | ❌ Not implemented | Text string → 512-dim vector via selected backend |
| 11 | Text-to-sample search | Embed query → search NumPy index → enrich from SQLite → ranked results | Steps 9, 10 | ❌ Not implemented | Results include path, score, BPM, key, type |
| 12 | Audio-to-audio search | Embed audio file → search NumPy index → enrich → ranked results | Steps 9, 8 | ❌ Not implemented | Same search contract as text, but audio-derived query vector |
| 13 | CLI `index_build` | Registered subcommand calls `build_numpy_index()` | Step 9 | ✅ NumPy skeleton + persistence | Index built on demand, status reported. Persisted via `--save` / `--index-path`. No FAISS. |
| 14 | CLI `search` | Registered subcommand calls `run_search()` with query, top-k | Steps 11, 12 | 🔶 Controlled skeleton | Search CLI accepts args and prints instructions. Returns no results without real embedding backend. |
| 15 | Documentation and validation | Documented contracts, acceptance tests, CI smoke checks | Steps 1-14 | 🔶 Partial | Index/search contracts documented. 24 tests for skeleton + persistence. End-to-end validation blocked by real backend. |

**Implementation priority within EPIC 2:** Steps 1-5 are foundation (mostly done). Steps 6-9 are the core build-out. Steps 10-15 layer search on top.

---

## 8. Data Contracts

### 8.1 Sample metadata contract

| Field | Type | Source | Required |
|-------|------|--------|----------|
| `id` | INTEGER | SQLite (auto) | ✅ |
| `path` | TEXT | Scanner | ✅ |
| `relpath` | TEXT | Scanner | ✅ |
| `hash` | TEXT (SHA-1) | Scanner | ✅ |
| `samplerate` | INTEGER | Scanner (via soundfile) | Optional |
| `channels` | INTEGER | Scanner (via soundfile) | Optional |
| `duration` | REAL | Scanner (via soundfile) | Optional |
| `size_bytes` | INTEGER | Scanner | ✅ |

### 8.2 Feature contract

| Field | Type | Source | Required |
|-------|------|--------|----------|
| `sample_id` | INTEGER (FK) | SQLite | ✅ |
| `bpm` | REAL | Analyzer (librosa) | Optional |
| `key` | TEXT | Analyzer (chroma) | Optional |
| `key_conf` | REAL | Analyzer | Optional |
| `loudness` | REAL | Analyzer (RMS) | Optional |
| `brightness` | REAL | Analyzer (spectral centroid) | Optional |
| `mfcc_mean` | BLOB | Analyzer | Optional |
| `mfcc_std` | BLOB | Analyzer | Optional |
| `chroma_mean` | BLOB | Analyzer | Optional |
| `chroma_std` | BLOB | Analyzer | Optional |
| `class` | TEXT | Analyzer (duration heuristic) | Optional |
| `pred_type` | TEXT | Autotype | Optional |

### 8.3 Embedding model contract

| Field | Type | Source | Required |
|-------|------|--------|----------|
| `id` | INTEGER | SQLite (auto) | ✅ |
| `provider` | TEXT | Backend (`model_info()`) | ✅ |
| `model_name` | TEXT | Backend (`model_info()`) | ✅ |
| `model_version` | TEXT | Backend (`model_info()`) | Optional (nullable) |
| `embedding_dim` | INTEGER | Backend (`model_info()`) | ✅ |
| `modality` | TEXT | Backend (`model_info()`) | ✅ |
| `created_at` | TEXT | SQLite (default) | ✅ |

**Uniqueness:** `(provider, model_name, model_version, modality)`

### 8.4 Sample embedding contract

| Field | Type | Source | Required |
|-------|------|--------|----------|
| `id` | INTEGER | SQLite (auto) | ✅ |
| `sample_id` | INTEGER (FK → samples.id) | Embedder | ✅ |
| `model_id` | INTEGER (FK → embedding_models.id) | Embedder | ✅ |
| `embedding` | BLOB (float32 bytes) | Backend (`embed_audio()`) | ✅ |
| `embedding_format` | TEXT | Embedder | ✅ (default `"numpy-blob"`) |
| `source_hash` | TEXT (SHA-1) | Scanner (at embed time) | ✅ |
| `created_at` | TEXT | SQLite (default) | ✅ |

**Uniqueness:** `(sample_id, model_id, source_hash)` — prevents duplicate embeddings for same sample + model + content version.

### 8.5 Vector index contract

| Field | Type | Source | Required |
|-------|------|--------|----------|
| Index file | NumPy `.npz` archive | Index builder (`save_numpy_index()`) | ✅ |
| Vectors | float32 `(N, dim)` | `.npz` key `vectors` | ✅ |
| Sample IDs | int64 `(N,)` | `.npz` key `sample_ids` | ✅ |
| Metadata | JSON string | `.npz` key `metadata_json` | ✅ |
| Model reference | model_id | Index builder | ✅ |
| Embedding dimension | int | Metadata (`embedding_dim`) | ✅ |
| Metric | str (`"cosine"`) | Metadata | ✅ |
| Normalized | bool (`True`) | Metadata | ✅ |
| Format version | int (`1`) | Metadata | ✅ |
| Build timestamp | ISO 8601 | Metadata (`created_at`) | ✅ |
| Sample count | int | Metadata (`sample_count`) | ✅ |

**Current format:** `data/indexes/model-{model_id}-numpy-cosine.npz` (single `.npz` file)
**Future format (FAISS):** `data/indexes/<model_name>-<model_version>-<index_type>.faiss` + `.meta`
**Lifecycle:** Rebuildable cache. Source of truth is SQLite `sample_embeddings` table.

### 8.6 Search result contract

| Field | Type | Source | Required |
|-------|------|--------|----------|
| `sample_id` | INTEGER | FAISS → SQLite mapping | ✅ |
| `path` | TEXT | `samples` table | ✅ |
| `score` | FLOAT | FAISS similarity | ✅ |
| `bpm` | REAL / null | `features` table | Optional |
| `key` | TEXT / null | `features` table | Optional |
| `pred_type` | TEXT / null | `features` table | Optional |
| `duration` | REAL / null | `samples` table | Optional |
| `loudness` | REAL / null | `features` table | Optional |
| `brightness` | REAL / null | `features` table | Optional |

---

## 9. Embedding Backend Contract

### 9.1 Interface

```python
class EmbeddingBackend(ABC):
    @abstractmethod
    def embed_audio(self, audio_path: str) -> np.ndarray: ...
    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray: ...
    @abstractmethod
    def model_info(self) -> EmbeddingModelInfo: ...
```

### 9.2 Rules

1. **No top-level torch/transformers imports.** All ML library imports are guarded inside methods (`try: import torch; except ImportError`).
2. **`model_info()` must not download model weights.** Metadata must be available without triggering a model download.
3. **Backend errors must be controlled.** Any error in `embed_audio()` or `embed_text()` raises `EmbeddingBackendUnavailableError` or a documented subclass. Raw `ImportError` or `RuntimeError` from torch must not propagate to the caller.
4. **Embedding vectors must be `float32` `np.ndarray`.** The dimension must match `model_info().embedding_dim`.
5. **Backend must not own SQLite schema.** Persistence is handled by the worker, not the backend.
6. **Backend must not contain CLI logic.** Dispatch is handled by `get_backend()` and the CLI layer.

### 9.3 CLAP-specific constraints (see ADR-0001)

- Model: `laion/clap-htsat-unfused` (512-dim, audio+text, via Hugging Face `transformers`)
- CPU-first default; CUDA is opt-in via `device="cuda"`
- Model download (~500 MB) on first `embed_audio()` or `embed_text()` call
- `_clap_available()` returns `True` only after `pip install torch transformers`

---

## 10. SQLite Persistence Contract

1. **SQLite remains the source of truth.** All metadata (samples, features, embeddings) is stored in and queryable from SQLite. The vector index is a cache, not a primary store.
2. **Embeddings are stored as BLOBs.** The `sample_embeddings.embedding` column contains raw float32 bytes (`np.ndarray.tobytes()`).
3. **Model metadata is stored once.** `embedding_models` uses `INSERT OR IGNORE` with a unique constraint on `(provider, model_name, model_version, modality)`.
4. **Uniqueness prevents duplicates.** The `(sample_id, model_id, source_hash)` unique constraint on `sample_embeddings` ensures that re-running the embedding pipeline does not create duplicate entries for unchanged samples.
5. **Staleness detection.** If a sample file's content hash changes (re-exported, re-rendered, modified), the old embedding is not overwritten — a new row with the new hash is inserted, and the old row remains for traceability.
6. **Failed embeddings are reported.** The worker must record the count of failed samples. Silent failures are not acceptable.
7. **No vector index as source of truth.** FAISS indexes can be deleted and rebuilt at any time without data loss.

---

## 11. Index Persistence and Validation

The current implementation uses NumPy `.npz` archives for index persistence. FAISS remains the long-term target but is not yet implemented.

### 11.1 NumPy `.npz` persistence

1. **Format:** Single `.npz` file containing three keys: `vectors` (float32), `sample_ids` (int64), `metadata_json` (JSON string).
2. **Default location:** `data/indexes/model-{model_id}-numpy-cosine.npz` — generated by `default_index_path()`.
3. **Writing:** `save_numpy_index()` is called by `build_index()` only when `--save` is passed. No automatic writes.
4. **Reading:** `load_numpy_index()` validates metadata before returning a `VectorIndex`:
   - `format_version == 1`
   - `metric == "cosine"`
   - `backend == "numpy"`
   - `vectors.shape[0] == sample_ids.shape[0]`
   - `vectors.shape[1] == metadata["embedding_dim"]`
   - optional `model_id` cross-check
5. **Artifact hygiene:** `data/indexes/` and `*.npz` are in `.gitignore`. Index files are never committed.

### 11.2 FAISS Index Contract (future)

1. **FAISS index is a rebuildable cache.** The source of truth for all embeddings is the SQLite `sample_embeddings` table. The index is disposable and rebuildable on demand.
2. **Index reads embeddings from SQLite.** `build_index()` queries `sample_embeddings` for all vectors of a given model, assembles them into a `np.ndarray`, and trains/loads the index.
3. **Index files are untracked.** All files under `data/indexes/` are in `.gitignore`. File patterns `*.faiss`, `*.index` are excluded.
4. **First index type: IndexFlatIP.** Exact inner-product search. No training required, works directly on raw vectors. This is the simplest correct implementation.
5. **Approximate indexes later.** IndexIVFFlat (with k-means training) can be introduced once the exact index is validated and performance profiling indicates a need.
6. **Index metadata must record:** model_id, embedding dimension, distance metric, index type, sample count, build timestamp.
7. **Index file naming convention:** `<provider>-<model_name>-<model_version>-<index_type>.faiss`
8. **Mapping:** FAISS indexes by integer position (0..N-1). A metadata JSON file maps position → sample_id for result enrichment.

---

## 12. Search Contract

### 12.1 Text-to-sample search

```
Text query string  ──►  backend.embed_text(query)  ──►  512-dim vector
                                                              │
                                                              ▼
                                                      FAISS index.search()
                                                              │
                                                              ▼
                                                   Top-k position IDs + scores
                                                              │
                                                              ▼
                                                   Metadata enrichment from SQLite
                                                              │
                                                              ▼
                                                   Ranked results with path, BPM, key, type, score
```

### 12.2 Audio-to-audio similarity search

```
Audio file path  ──►  backend.embed_audio(path)  ──►  512-dim vector
                                                              │
                                                              ▼
                                                      FAISS index.search()
                                                              │
                                                              ▼
                                                   (same as text search from here)
```

### 12.3 Result contract

Each search result must include:

| Field | Source | Always present? |
|-------|--------|-----------------|
| `sample_id` | SQLite mapping | ✅ Yes |
| `path` | `samples` table | ✅ Yes |
| `score` | FAISS (inner product) | ✅ Yes |
| `bpm` | `features` table | If available |
| `key` | `features` table | If available |
| `pred_type` | `features` table | If available |
| `duration` | `samples` table | If available |
| `loudness` | `features` table | If available |
| `brightness` | `features` table | If available |

### 12.4 Error behaviour

| Condition | Behaviour |
|-----------|-----------|
| No index exists | Clear error message: "No index found. Run `sample-brain index_build` first." |
| No embeddings for any sample | Clear error message: "No embeddings in database. Run `sample-brain embed` first." |
| Backend unavailable | `EmbeddingBackendUnavailableError` with install instructions |
| Query embedding fails | Per-query error reported, search aborted with message |
| FAISS returns empty results | Empty list returned (no close matches) |

---

## 13. Acceptance Criteria by Milestone

### M1 — Embedding foundation

| # | Criterion | Validation |
|---|-----------|------------|
| 1 | `embedding_models` table exists after `init_db()` | Run `init_db()`, query schema |
| 2 | `sample_embeddings` table exists after `init_db()` | Run `init_db()`, query schema |
| 3 | `upsert_embedding_model()` returns a valid model ID | Call with test metadata, verify return |
| 4 | `insert_sample_embedding()` stores a BLOB and returns ID | Call with test vector, verify round-trip |
| 5 | `sample_embedding_exists()` detects existing embedding | Insert, verify `True`; query non-existent, verify `False` |

### M2 — CLAP backend (from spike)

| # | Criterion | Validation |
|---|-----------|------------|
| 1 | `_clap_available()` returns `True` after `pip install torch transformers` | Import test |
| 2 | `ClapEmbeddingBackend.model_info()` returns metadata without model download | Call without network, verify no crash |
| 3 | `ClapEmbeddingBackend.embed_text("kick")` returns 512-dim `np.ndarray` (float32) | Call once, verify shape and dtype |
| 4 | `ClapEmbeddingBackend.embed_audio(path)` returns 512-dim `np.ndarray` (float32) | Use a synthetic fixture, verify shape and dtype |
| 5 | `sample-brain --help` works without torch/transformers | Run in clean environment, verify no import error |
| 6 | `git status` shows no model/cache/embedding artifacts after test run | Run spike, check working tree |

### M3 — Batch embedding

| # | Criterion | Validation |
|---|-----------|------------|
| 1 | Worker queries pending samples via `iter_pending_samples()` | Run on DB with mixed embedded/unembedded samples |
| 2 | Worker embeds each pending sample and persists to DB | Verify `sample_embeddings` rows after run |
| 3 | Worker skips already-embedded samples | Re-run, verify `processed = 0` |
| 4 | Worker reports processed, skipped, and failed counts | Inspect `EmbeddingRunResult` |
| 5 | Worker resumes after interruption | Embed subset, kill, re-run, verify no duplicates |

### M4 — FAISS index

| # | Criterion | Validation |
|---|-----------|------------|
| 1 | `build_index()` reads all embeddings from `sample_embeddings` | Run on DB with N embeddings, verify index sample count |
| 2 | Index file is written to `data/indexes/` | Verify file exists and has expected `.faiss` extension |
| 3 | Metadata JSON is written alongside index | Verify `.meta` file contains model_id, dimension, metric, build_time |
| 4 | Index is rebuildable from scratch | Delete index, rebuild, verify identical search results |
| 5 | No index files appear in `git status` | Rebuild, check working tree |

### M5 — Text search

| # | Criterion | Validation |
|---|-----------|------------|
| 1 | `search("dark pad")` returns ranked results | Run with text query, verify list of results |
| 2 | Results include path, score, and available metadata | Inspect result fields |
| 3 | Result order is by descending score (most similar first) | Verify first result has highest score |
| 4 | Query without index gives clear error | Remove index, search, verify helpful error message |
| 5 | Query without embeddings gives clear error | Clear DB embeddings, search, verify helpful error message |

### M6 — Audio similarity

| # | Criterion | Validation |
|---|-----------|------------|
| 1 | `search("path/to/audio.wav")` returns similar samples | Run with audio file, verify list of results |
| 2 | Same result contract as text search | Inspect fields |
| 3 | Unsupported audio formats give clear error | Try with non-audio file, verify error |

### M7 — CLI and documentation

| # | Criterion | Validation |
|---|-----------|------------|
| 1 | `sample-brain embed --help` shows `--backend`, `--limit`, `--all` | Run help |
| 2 | `sample-brain index_build --help` shows expected arguments | Run help |
| 3 | `sample-brain search --help` shows `query`, `--topk` | Run help |
| 4 | All three subcommands fail gracefully without optional deps | Run in clean environment |
| 5 | Artifact policy is respected — no generated files appear in `git status` | Run all three, check working tree |

---

## 14. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Heavy ML dependencies (torch ~2-3 GB, transformers ~500 MB) | High — scares off users | High | Optional `[clap]` extra, guarded imports, clear install docs |
| Model download size on first use (~500 MB) | Medium — one-time delay | High | User-visible message before download, cache in `~/.cache/huggingface/` |
| CPU embedding performance (seconds per file) | Medium — slow for large libraries | Medium | Batch processing, progress bar, resumable worker |
| Embedding staleness (sample changed, old vector remains) | Medium — wrong search results | Low | `source_hash` comparison on every embed run; re-embedding triggered automatically |
| Index/model version mismatch (FAISS built with old model, query uses new model) | Medium — dimension mismatch or nonsense similarity | Low | Index metadata records model_id; search cross-checks before use |
| Private samples accidentally referenced in tests or docs | High — privacy violation | Low | Synthetic fixtures only; policy explicitly bans sample audio in repo |
| Generated artifacts accidentally committed | Medium — repo bloat | Medium | `.gitignore` + commit checklist + CI check + artifact policy |
| False sense of semantic accuracy (user expects perfect results, gets approximations) | Medium — trust erosion | Medium | Document confidence limits in help text and docs; "no fake intelligence" principle |
| FAISS index rebuild time for >100k samples | Medium — minutes on CPU | Low | Explicitly deferred to EPIC 2+; IndexFlatIP is fast to build (no training) |

---

## 15. Transition to EPIC 3

EPIC 2 delivers:
- Reproducible, versioned sample embeddings
- Local vector index (NumPy cosine similarity skeleton; FAISS deferred) with CLI-invokable build
- Search contract and CLI skeleton (real search requires query embedding backend)
- Metadata enrichment from SQLite on search results

EPIC 3 (Hybrid Ranking & Recommendation) builds on this foundation:

| Capability | EPIC 2 delivers | EPIC 3 adds |
|------------|----------------|-------------|
| Ranking | Pure vector similarity (inner product) | Blended score: vector similarity × structured metadata filters |
| Search | Text and audio queries | Context-aware search (BPM, key, type constraints) |
| Results | Ranked by semantic similarity | Ranked by hybrid relevance (semantic + music theory + usage patterns) |
| Recommendation | Not in scope | "Samples like this" based on combined signals |

**EPIC 3 does not begin until EPIC 2 search is stable**, meaning:
- All M5 (text search) and M6 (audio similarity) acceptance criteria are met
- The CLI is documented and tested
- No `git status` pollution from any pipeline step
- The implementation works without torch/transformers for core pipeline

EPIC 3 specifics are TODO — this document does not define them. At transition time, `docs/EPIC_3_HYBRID_RANKING_SPEC.md` should be created following the same structure as this document.

---

## 16. Related Documents

| Document | Relevance |
|----------|-----------|
| `docs/PRODUCT_REQUIREMENTS.md` | Product vision, target audience, MVP scope |
| `docs/SYSTEM_REQUIREMENTS.md` | Functional requirements (FR-EMBD-01-08, FR-IDX-01-04, FR-SRCH-01-04), embedding/index/search contracts |
| `docs/TARGET_ARCHITECTURE.md` | System architecture, component boundaries, dependency direction, EPIC 2 design (Section 7) |
| `docs/DATA_AND_ARTIFACT_POLICY.md` | What is committed vs untracked (indexes, embeddings, models, caches) |
| `knowledge/roadmap/adr/ADR-0001-embedding-model-strategy.md` | CLAP selection rationale, backend design, spike plan, dependency constraints |
| `knowledge/roadmap/adr/ADR-0002-local-vector-index-strategy.md` | FAISS selection rationale, index lifecycle, artifact hygiene |
| `knowledge/roadmap/adr/ADR-0003-embedding-db-schema-design.md` | SQLite schema design for embeddings, BLOB rationale, staleness detection |
| `docs/ISSUE_BACKLOG.md` | EPIC 2 task breakdown (#10-#15) |
| `knowledge/ACTIVE_ROADMAP.md` | Current implementation status — P1 done, P2 planned |
