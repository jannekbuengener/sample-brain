# CURRENT_STATUS

## Current State

- **Branch:** `main` — synchronised with `origin/main`
- **Working tree:** clean
- **Last commit:** `850080d feat: persist numpy vector index`

## What Works (Core Pipeline)

- **Scan** — registers sample files in SQLite catalog; supports `--root` CLI override
- **Analyze** — extracts audio features via librosa (BPM, key, loudness, brightness, MFCCs, chroma); reads from pre-scanned catalog (no `--root` needed)
- **Autotype** — rule-based + optional kNN classification; supports `--no-knn` CLI override and config profile overrides (`autotype.use_knn`, `autotype.knn_min_conf`)
- **Export** — writes smart tags into FL Studio Browser; supports `--fl-user-data` and `--max-tags` CLI overrides
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
- `iter_pending_samples()` — source-hash-aware pending sample query (`src/db.py`)
- `EmbeddingWorker.run()` — batch worker loop with DB persistence, per-sample error handling, dimension validation (`src/embed.py`)
- `--backend {noop,clap}` CLI flag — wired via config profile or CLI override
- Guarded CLAP backend stub (raises `EmbeddingBackendUnavailableError`)
- NumPy vector index skeleton (`src/index.py`) — `VectorIndex`, `SearchHit`, `decode_embedding_blob()`, `normalize_vectors()`, `load_embeddings_for_model()`, `build_numpy_index()`, `search_index()`
- NumPy index persistence (`src/index.py`) — `save_numpy_index()`, `load_numpy_index()`, `default_index_path()`, metadata validation (format_version, metric, dim, model_id)
- Controlled search skeleton (`src/search.py`) — `run_search()` prints info that CLAP backend is required
- CLI subcommands `embed`, `index_build`, `search` functional controlled commands
- `index_build --save` persists `.npz` to `data/indexes/` (no persistence without `--save`)
- `index_build --index-path` custom save path (implies `--save`)
- 37 unit tests for embedding + index/search pipeline (5 worker + 8 DB + 24 index/search/persistence)
- **No FAISS, no real CLAP embedding, no end-to-end semantic search on `main`**

## CLAP Spike Status

- **Branch:** `spike/clap-embedding` — contains full CLAP prototype (optional deps, real embedding, DB persistence)
- **Status:** Parked / Draft — not merged to `main`. The spike validates ADR-0001 architecture decisions but is not production-ready.

## EPIC 1 — Config Profiles (Completed)

**Acceptance Criteria verification:**

| # | Criterion | Status |
|---|-----------|--------|
| 1 | No real local paths in committed code or config | ✅ `SAMPLE_ROOTS` is empty list; no `D:\` or `C:\Users` in `src/` |
| 2 | Example profile exists with placeholder paths | ✅ `config/profiles.example.yaml` — all `<PLACEHOLDER>` values |
| 3 | Local profile is gitignored | ✅ `git check-ignore config/profiles.local.yaml` returns the file |
| 4 | CLI can select a profile via `--profile` | ✅ `--profile minimal-demo embed --limit 1` works |
| 5 | Default profile used when none specified | ✅ `DEFAULT_PROFILE_NAME = "default"` |
| 6 | Env vars override profile values | ✅ Tested: `SAMPLE_BRAIN_MAX_TAGS=10` overrides `export.max_tags` |
| 7 | CLI flags override env vars | ✅ Precedence chain implemented in all handlers |
| 8 | Missing paths produce clear errors | ⚠️ Partial — backend validated; path existence not yet checked (future hardening) |
| 9 | Unknown profile produces clear error | ✅ `Unknown profile: {name}. Available: {names}` |
| 10 | README explains profile setup | ✅ Configuration section, CLI overrides table, security note |

**Wired subcommands:**

| Subcommand | Config keys | CLI overrides |
|------------|-------------|---------------|
| `scan` | `library_roots` | `--root` |
| `embed` | `embedding.backend` | `--backend` |
| `export_fl` | `fl_user_data_path`, `export.max_tags`, `library_roots` | `--fl-user-data`, `--max-tags` |
| `autotype` | `autotype.use_knn`, `autotype.knn_min_conf` | `--no-knn` |
| `analyze` | DB-catalog based (no root wiring needed) | — |

**Future hardening (not blockers for close):**
- Runtime path validation (EPIC 1 Spec Section 9)
- CLI wiring integration tests
- `embed --model-cache-dir` CLI flag
- Explicit local-config-only flag

## What Is Not Done

- Real CLAP backend — not on `main` (stub only; real implementation on `spike/clap-embedding`)
- FAISS index builder — not imported, not integrated
- Real end-to-end semantic search — blocked by real embedding backend
- Query embedding backend — not implemented (CLAP not on `main`)
- EPIC 3-6 — not started

## Next Steps (empfohlen)

1. Docs update for EPIC 2 Index Persistence (current step)
2. Search query embedding strategy
3. Real CLAP backend decision / PR #10 handling
4. FAISS adapter — deferred until NumPy index contract is stable and embeddings exist
