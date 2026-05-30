# CURRENT_STATUS

## Current State

- **Branch:** `main` — synchronised with `origin/main`
- **Working tree:** clean
- **Last commit:** `8046816 feat: support external SampleBrain DB path (#13)`

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
- Guarded CLAP backend — real `ClapEmbeddingBackend` with lazy model loading, `embed_text()` (512-dim), `embed_audio()` (512-dim), download-free `model_info()`
- NumPy vector index skeleton (`src/index.py`) — `VectorIndex`, `SearchHit`, `decode_embedding_blob()`, `normalize_vectors()`, `load_embeddings_for_model()`, `build_numpy_index()`, `search_index()`
- NumPy index persistence (`src/index.py`) — `save_numpy_index()`, `load_numpy_index()`, `default_index_path()`, metadata validation (format_version, metric, dim, model_id)
- Search backend contract wired — `run_search()` uses `get_backend(backend_name)` → `embed_text(query)` → `search_index()` → ranked hits
- `search --backend {noop,clap}` — CLI flag wired via config profile or CLI override
- `search --index-path` — loads persisted `.npz` index instead of building from DB
- `NoopEmbeddingBackend` raises `NotImplementedError` → `[ERROR] No embedding backend configured.`
- `ClapEmbeddingBackend` raises `EmbeddingBackendUnavailableError` with `[clap]` install hint when optional deps missing
- CLI subcommands `embed`, `index_build`, `search` functional controlled commands
- `index_build --save` persists `.npz` to `data/indexes/` (no persistence without `--save`)
- `index_build --index-path` custom save path (implies `--save`)
- 50+ unit tests for embedding + index/search pipeline (worker + DB + index + search + clap + config)
- **`SAMPLE_BRAIN_DB_PATH`** — runtime SQLite path override (merged via PR #13); keeps validation DBs outside repo
- **No FAISS** — NumPy `.npz` index is the current implementation; FAISS remains a deferred optional adapter

## EPIC 2 Runtime Proof Status

- **M1 / #11:** Isolated CLAP runtime environment — PASS.
  External venv validated with Python 3.12.10 and CLAP optional dependencies. `model_info()` returns 512-dim metadata without model download.
- **M2 / #12:** Real CLAP text embedding smoke — PASS.
  `get_backend("clap").embed_text("kick drum")` returned a real `np.ndarray` with shape `(512,)` and dtype `float32`. HuggingFace model cache stayed outside the repo.
- **M3:** Real CLAP audio embedding persistence — PASS.
  Synthetic WAV outside repo was scanned and embedded with `embed --backend clap`; a 512-dim float32 embedding was persisted to an external SQLite DB via `SAMPLE_BRAIN_DB_PATH`.
- **M4:** NumPy semantic search E2E — PASS.
  Real CLAP embeddings were loaded from SQLite, persisted into an external NumPy `.npz` index, and queried with `search "kick drum" --backend clap`, returning `rank=1 sample_id=1 score=0.0726`.
- **PR #13:** `SAMPLE_BRAIN_DB_PATH` support merged.
  External runtime DBs are now supported without repo-local DB artifacts.

## CLAP Implementation Status

- **On `main`:** Guarded `ClapEmbeddingBackend` with lazy model loading, optional `[clap]` deps, download-free `model_info()`, real `embed_text()` and `embed_audio()` (512-dim float32) validated in controlled smoke path.
- **Historical:** PR #10 (`spike/clap-embedding`) closed as superseded — `main` is the source of truth.
- **Runtime:** First `embed_text()`/`embed_audio()` call downloads model weights (~500 MB) to `~/.cache/huggingface/`. Guarded unit tests pass without model download.

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

- **FAISS adapter** — not implemented; NumPy `.npz` index is current
- **Large-scale / private sample validation** — only controlled synthetic-fixture E2E smoke proven
- **Production search quality tuning** — E2E smoke confirms plumbing, not ranking quality
- **Dependabot cleanup** — classified in M5a (#14); not merged yet
- **Docs hygiene** — tracked in #14 (M5b in progress)
- **EPIC 3–6** — not started

## Next Steps (empfohlen)

1. Complete M5b docs drift (#14) — sync status/spec/architecture/backlog with E2E evidence
2. Dependabot one-by-one merge (#4 checkout, #8 tqdm first; defer #5 numba)
3. FAISS adapter (M6) — deferred until NumPy path is stable and explicitly approved
4. EPIC 3 hybrid ranking — not before search path is documented and stable on `main`
