# CURRENT_STATUS

## Current State

- **Branch:** `main` — synchronised with `origin/main`
- **Working tree:** clean
- **Last commit:** `9765771 fix: remove hardcoded sample root fallback`

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
- Embedding worker skeleton (no-op on `main`)
- Guarded CLAP backend stub (raises `EmbeddingBackendUnavailableError`)
- CLI subcommands `embed`, `index_build`, `search` registered with guarded imports
- **No FAISS, no real CLAP embedding, no search pipeline on `main`**

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

- EPIC 2 implementation (embed → index → search) — not started on `main`
- FAISS index builder — not imported, not implemented
- Search pipeline — not imported, not implemented
- EPIC 3-6 — not started

## Next Steps (empfohlen)

1. Begin EPIC 2 implementation sequence per spec (batch embedding → FAISS index → search)
