# CURRENT_STATUS

## Current State

- **Branch:** `main`
- **Working tree:** clean (post sqlite-vec campaign closeout)
- **Last commit:** `1602ebb` — benchmark gate evidence (PR #51)
- **Open PRs:** none
- **Open issues:** none
- **Tests:** 138 passed (`pytest -q`; optional `[vec]` extra for vec-specific tests)

## sqlite-vec Campaign — Closed

Phases 1–8 complete on `main` (PRs #47–#51 + Phase 8 docs closeout):

| Phase | Deliverable | PR |
|-------|-------------|-----|
| 1 | Availability + diagnostics (`vec status`, `vec smoke`) | #47 |
| 2 | Schema (`vector_index_state`, vec tables) | #48 |
| 3 | vec0 cache rebuild from `sample_embeddings` | #49 |
| 4–7 | Search backend adapter, config gate, benchmark harness | #50, #51 |
| 8 | Docs hardening (README, EPIC_2, AGENTS, roadmap) | closeout PR |

**Gate evidence:** [SQLITE_VEC_GATE_EVIDENCE.md](../docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md)

| Gate | Verdict |
|------|---------|
| Overlap @ k=10 vs NumPy | **PASS** (1.000) |
| warm p95 @ 100k ≤ 200 ms | **FAIL** (3568 ms) |
| filtered p95 @ 100k ≤ 250 ms | **FAIL** (3440 ms) |

**Decision:** Default `search.backend` remains **`numpy`**. Opt in to `sqlite-vec` via profile, `SAMPLE_BRAIN_SEARCH_BACKEND`, or `--search-backend`.

## What Works (Core Pipeline)

- **Scan** — registers sample files in SQLite catalog; supports `--root` CLI override
- **Analyze** — extracts audio features via librosa; reads from pre-scanned catalog
- **Autotype** — rule-based + optional kNN classification
- **Export** — writes smart tags into FL Studio Browser
- **Packaging** — `sample-brain --help` entry point works
- **CLI** — core pipeline + optional embed/index/search/vec/benchmark/db doctor

## What Works (Semantic Search + sqlite-vec)

- **Embeddings** — CLAP backend (optional `[clap]`), worker persistence, `SAMPLE_BRAIN_DB_PATH`
- **NumPy search** — default backend; `.npz` persistence via `--save` / `--index-path`
- **sqlite-vec** — optional `[vec]` extra; `index_build --search-backend sqlite-vec`; `search --search-backend sqlite-vec`
- **Benchmark** — `benchmark vec --samples 1000 10000 100000` with overlap + latency gates
- **DB doctor** — `db doctor` integrity checks

## EPIC 2 Runtime Proof Status

- **M1–M4:** CLAP + NumPy semantic search E2E — PASS (controlled smoke, external DB)
- **sqlite-vec:** Correctness gate PASS; latency gate FAIL at 100k on measured Windows host

## Bootstrap Validation

| Check | Result |
|-------|--------|
| `pip install -e .` + `pytest -q` | PASS (138 tests) |
| CLI `--help` | PASS |
| External DB via `SAMPLE_BRAIN_DB_PATH` | PASS |
| Optional `[vec]`: `vec status` | PASS when installed |

## What Is Not Done

- **Default switch to sqlite-vec** — blocked until latency gates PASS
- **Phase 5 tags + FTS5 MVP** — not started (roadmap Phase 5)
- **Large-scale private-sample validation** — synthetic/benchmark fixtures only
- **CLAP test hardening** — CLAP-installed venvs may fail unavailable-backend tests
- **EPIC 3–6** — not started

## Next Steps (empfohlen)

1. **sqlite-vec latency follow-up** — only if default switch is desired (~3.5 s p95 @ 100k on evidence host)
2. **CLAP test hardening** — unavailable-backend tests in CLAP-installed venvs
3. **Phase 5 tags/FTS5** — when hybrid/tag search is prioritized

## Key Docs

| Document | Purpose |
|----------|---------|
| [ADR-0004](../docs/adr/ADR-0004-sqlite-vec-search-backend.md) | Accepted sqlite-vec strategy |
| [SQLITE_VEC_ROADMAP.md](../docs/SQLITE_VEC_ROADMAP.md) | Phases 0–8 (all done) |
| [SQLITE_VEC_GATE_EVIDENCE.md](../docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md) | Measured gates |
| [EPIC_2_SEMANTIC_SEARCH_SPEC.md](../docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md) | Search contracts |
