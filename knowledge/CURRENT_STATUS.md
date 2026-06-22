# CURRENT_STATUS

## Live State

- **Branch:** `main`
- **HEAD:** `b096fcb` (`build(deps): bump numpy from 1.26.4 to 2.4.6`)
- **Open PRs:** 2 Dependabot (#63 soundfile 0.14.0, #64 tqdm 4.68.1)
- **Open issues:** 9 — #72, #73, #74 (previous EPIC-2 follow-ups), **#90–#95 (VST-first product target, new)**
- **Tests:** 106 passed, 2 skipped (`pytest -q` core; 4 `[vec]`-dependent test files fail import without `sqlite_vec` installed — see test command below)

```powershell
python -m pytest -q --ignore=tests/test_search.py --ignore=tests/test_search_backend.py --ignore=tests/test_search_quality.py --ignore=tests/test_vec_index.py
```

## Search Quality Campaign — Closed

Merged via PR #54 (`0673819`, 2026-05-31). Adds relevance evaluation on existing search infrastructure (no DB schema change, no sqlite-vec tuning):

| Deliverable | Status |
|-------------|--------|
| ADR-0005 Search Quality Spec | ✅ |
| Golden query suite (`golden_v1.yaml`, Tier A) | ✅ |
| `search_eval.py` + `collect_search_hits()` + `benchmark search-quality` | ✅ |
| Tier A regression (`test_search_quality.py`) | ✅ |
| Filter/hybrid E2E tests | ✅ |
| Tier B CLAP stub (`golden_v2_clap.yaml`, `@pytest.mark.clap`) | ✅ optional |
| Evidence report | ✅ [SEARCH_QUALITY_EVIDENCE.md](../docs/benchmarks/SEARCH_QUALITY_EVIDENCE.md) |

**Tier A gates (measured):** Mean P@1=1.000, P@5=0.600, R@10=1.000, filter compliance 100%, must-recall PASS.

## sqlite-vec Campaign — Closed

Phases 1–8 complete on `main` (PRs #47–#51 + Phase 8 docs closeout):

| Phase | Deliverable | PR |
|-------|-------------|-----|
| 1 | Availability + diagnostics (`vec status`, `vec smoke`) | #47 |
| 2 | Schema (`vector_index_state`, vec tables) | #48 |
| 3 | vec0 cache rebuild from `sample_embeddings` | #49 |
| 4–7 | Search backend adapter, config gate, benchmark harness | #50, #51 |
| 8 | Docs hardening (README, EPIC_2, roadmap, CURRENT_STATUS) | #53 |

**Gate evidence:** [SQLITE_VEC_GATE_EVIDENCE.md](../docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md)

| Gate | Verdict |
|------|---------|
| Overlap @ k=10 vs NumPy | **PASS** (1.000) |
| warm p95 @ 100k ≤ 200 ms | **FAIL** (3568 ms) |
| filtered p95 @ 100k ≤ 250 ms | **FAIL** (3440 ms) |

**Decision:** Default `search.backend` remains **`numpy`**. Opt in to `sqlite-vec` via profile, `SAMPLE_BRAIN_SEARCH_BACKEND`, or `--search-backend`.

## sqlite-vec bootstrap (opt-in)

```powershell
pip install -e ".[vec]"
sample-brain vec status
sample-brain vec smoke
sample-brain index_build --model-id 1 --search-backend sqlite-vec
sample-brain search "kick" --model-id 1 --search-backend sqlite-vec --backend clap
sample-brain db doctor
sample-brain benchmark vec --samples 1000 --work-dir $env:TEMP\sample-brain-bench
```

- **Default:** `search.backend: numpy` in profile; override via `SAMPLE_BRAIN_SEARCH_BACKEND` or `--search-backend`
- **Embedding vs search backend:** `--backend` / `embedding.backend` selects CLAP/noop; `--search-backend` / `search.backend` selects NumPy vs sqlite-vec
- **Artifacts:** use `SAMPLE_BRAIN_DB_PATH` and external `--work-dir`; never commit DBs, `.npz`, or benchmark outputs

## What Works

### Core Pipeline
- **Scan** — registers sample files in SQLite catalog; supports `--root` CLI override
- **Analyze** — extracts audio features via librosa; reads from pre-scanned catalog
- **Autotype** — rule-based + optional kNN classification
- **Export** — writes smart tags into FL Studio Browser
- **Packaging** — `sample-brain --help` entry point works
- **CLI** — core pipeline + optional embed/index/search/vec/benchmark/db doctor

### Semantic Search + sqlite-vec
- **Embeddings** — CLAP backend (optional `[clap]`), worker persistence, `SAMPLE_BRAIN_DB_PATH`
- **NumPy search** — default backend; `.npz` persistence via `--save` / `--index-path`
- **sqlite-vec** — optional `[vec]` extra; `index_build --search-backend sqlite-vec`; `search --search-backend sqlite-vec`
- **Benchmark** — `benchmark vec` (overlap + latency gates); `benchmark search-quality` (Tier A P@K/R@K gates)
- **DB doctor** — `db doctor` integrity checks

## EPIC 2 Runtime Proof Status

- **M1–M5 (Tier A):** Golden query suite + P@K/R@K harness — PASS (synthetic fixtures, NumPy backend)
- **M1–M4:** CLAP + NumPy semantic search E2E — PASS (controlled smoke, external DB)
- **sqlite-vec:** Correctness gate PASS; latency gate FAIL at 100k on measured Windows host

## Bootstrap Validation

| Check | Result |
|-------|--------|
| `pip install -e .` + `pytest -q` (core) | PASS (106 passed, 2 skipped; 4 `[vec]`-dependent files fail import without `sqlite_vec`) |
| CLI `--help` | PASS |
| External DB via `SAMPLE_BRAIN_DB_PATH` | PASS |
| Optional `[vec]`: `vec status` | PASS when installed |

## What Is Not Done

- **Default switch to sqlite-vec** — blocked until latency gates PASS
- **Tier B CLAP search-quality evidence** — stub only; local `@pytest.mark.clap` optional
- **Phase 5 tags + FTS5 MVP** — not started (roadmap Phase 5)
- **Large-scale private-sample validation** — synthetic/benchmark fixtures only
- **EPIC 3–6** — not started

## Key Docs

| Document | Purpose |
|----------|---------|
| [ADR-0004](../docs/adr/ADR-0004-sqlite-vec-search-backend.md) | Accepted sqlite-vec strategy |
| [ADR-0005](../docs/adr/ADR-0005-search-quality-evaluation.md) | Search quality evaluation (Tier A/B) |
| [SQLITE_VEC_ROADMAP.md](../docs/SQLITE_VEC_ROADMAP.md) | Phases 0–8 (all done) |
| [SQLITE_VEC_GATE_EVIDENCE.md](../docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md) | Measured backend gates |
| [SEARCH_QUALITY_EVIDENCE.md](../docs/benchmarks/SEARCH_QUALITY_EVIDENCE.md) | Tier A relevance gates |
| [EPIC_2_SEMANTIC_SEARCH_SPEC.md](../docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md) | Search contracts |
