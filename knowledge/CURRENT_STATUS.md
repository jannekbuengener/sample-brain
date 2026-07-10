# CURRENT_STATUS

## Live State

- **Branch:** `main` @ `2d42ee3` (docs backlog sync after workbench close; runtime hotfix PR #199)
- **Open PRs:** none
- **Open issues:** 4 — [#198](https://github.com/jannekbuengener/sample-brain/issues/198) Workbench matching/suggestions planning, [#196](https://github.com/jannekbuengener/sample-brain/issues/196) numpy/numba HOLD, [#73](https://github.com/jannekbuengener/sample-brain/issues/73) CLAP Tier-B, [#74](https://github.com/jannekbuengener/sample-brain/issues/74) sqlite-vec ANN
- **Local Workbench:** `sample-brain workbench` — tkinter MVP shipped; parent epic [#117](https://github.com/jannekbuengener/sample-brain/issues/117) **closed** 2026-07-10
  - Shipped under #117: folder analysis, playlist/filter/sort, library cache + multi-folder view, catalog read-only bridge, catalog→cache import (#192), FL export (#191), analysis-limit persistence (#190), cue/loop/attack metadata, audio preview + waveform, structured search UI, runtime hotfix PR #199
  - Open follow-up: [#198](https://github.com/jannekbuengener/sample-brain/issues/198) Matching-/Vorschlagsansicht planen (planning only; semantic search remains #73; sqlite-vec/ANN remains #74)
- **Dependency HOLD:** [#196](https://github.com/jannekbuengener/sample-brain/issues/196) — `numpy>=2.5` blocked by `numba` pin; Dependabot PR #103 closed (not merged)
- **Product pillars:** All 5 specs under [`docs/product/`](../docs/product/README.md) — #90 closed via PR #107; no open product-docs issues
- **Recently closed:** [#117](https://github.com/jannekbuengener/sample-brain/issues/117) Workbench epic (2026-07-10); [#72](https://github.com/jannekbuengener/sample-brain/issues/72) key confidence evidence via PR #108 — [KEY_CONF_EVIDENCE.md](../docs/benchmarks/KEY_CONF_EVIDENCE.md)
- **Current focus:** EPIC-2 follow-ups — #198 Workbench matching plan; #196 dependency HOLD; #73 vocal/no-vocal deferred after proxy spike HOLD; genre/mood data strategy; #74 ANN tracking
- **Tests:** CI green on `main`; local `pytest -q` — 567 passed, 1 skipped (last full-suite run on `main`)

## Search Quality Campaign — Closed

Merged via PR #54 (`0673819`, 2026-05-31). Adds relevance evaluation on existing search infrastructure (no DB schema change, no sqlite-vec tuning):

| Deliverable | Status |
|-------------|--------|
| ADR-0005 Search Quality Spec | ✅ |
| Golden query suite (`golden_v1.yaml`, Tier A) | ✅ |
| `search_eval.py` + `collect_search_hits()` + `benchmark search-quality` | ✅ |
| Tier A regression (`test_search_quality.py`) | ✅ |
| Filter/hybrid E2E tests | ✅ |
| Tier B CLAP Phase 1+2 (`golden_v2_clap.yaml`, `@pytest.mark.clap`) | ✅ Phase 2 merged | 4/6 classes: kick_snare_perc, pad_texture, riser_impact, dry_wet; [SEARCH_QUALITY_EVIDENCE.md](../docs/benchmarks/SEARCH_QUALITY_EVIDENCE.md) |
| Tier B vocal proxy spike | 🔶 HOLD | Formant generators + isolated spike; **HOLD_VOCAL_PROXY_FAILED** — not in golden_v2 |
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
- **Export** — writes smart tags into FL Studio Browser (**legacy/fallback** CLI path; VST3 plugin is the product target)
- **Local Workbench** — tkinter MVP: enter or pick folder path (last folder restored from `~/.sample-brain/`), library folder list with add/remove (cache-only), cancel mid-analysis, filter/sort playlist, segment-wise detail paths + copy, CSV export, library cache for re-analysis skip, waveform play surface (left = saved cue, right = click position), double-click/Space preview, read-only waveform envelope + cue marker, run in-process analyze + rule-based type (`workbench` subcommand)
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
- **Tier B CLAP search-quality evidence** — Phase 1+2 merged; 4/6 classes on main; vocal/no-vocal proxy spike **HOLD_VOCAL_PROXY_FAILED**; genre/mood remain (#73 OPEN)
- **Workbench Matching-/Vorschlagsansicht** — planning only ([#198](https://github.com/jannekbuengener/sample-brain/issues/198) OPEN); #117 epic closed
- **numpy 2.5 / numba unblock** — tracked via [#196](https://github.com/jannekbuengener/sample-brain/issues/196) HOLD; do not merge until `numba` supports `numpy>=2.5`
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
| [WORKBENCH_CUE_METADATA_PLAN.md](../docs/WORKBENCH_CUE_METADATA_PLAN.md) | Cue/loop/attack metadata plan (workbench, #117 closed) |
