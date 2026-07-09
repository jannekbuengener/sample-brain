# CURRENT_STATUS

## Live State

- **Branch:** `main` @ `f196f41` (loop repeat preview #152)
- **Open PRs:** 1 Dependabot — **#103** (numpy 2.5.1) → **HOLD_DEPENDENCY_VALIDATION** (`numba` requires `numpy<2.5`)
- **Open issues:** 3 — [#117](https://github.com/jannekbuengener/sample-brain/issues/117) Workbench follow-ups (global library view, catalog unification), [#73](https://github.com/jannekbuengener/sample-brain/issues/73) CLAP Tier-B, [#74](https://github.com/jannekbuengener/sample-brain/issues/74) sqlite-vec ANN
- **Local Workbench MVP:** `sample-brain workbench` — tkinter folder analysis + playlist/detail + waveform-as-play-surface + cue/loop metadata + loop edit mode (toggle + two-click set + clear)
- **Workbench P0 (#117, merged):** cancel analysis (#119), folder path entry (#118), playlist filter (#120), column sort (#121), detail path polish + copy (#122)
- **Workbench P1 (#117, merged):** last-folder memory (#124), CSV playlist export (#125)
- **Workbench library cache v1 (#117):** user-local SQLite (`~/.sample-brain/workbench_library.db`) remembers analyzed folders/samples; invalidation via path + size + mtime; internal `display_name` only — original files unchanged
- **Workbench library folder list (#117, merged):** sidebar lists known library folders; `+` adds folder to cache; `−` removes cache metadata only; **Alle Library-Samples** loads all cached rows across folders
- **Workbench audio preview v1 (#117, merged PR #129):** platform playback (winsound/afplay/aplay); non-WAV via temp PCM decode; original files never modified
- **Workbench preview controls (#117, merged PR #130):** double-click row to play; Space toggles play/stop; selection preserved across filter/sort; preview disabled during analysis
- **Workbench waveform panel v1 (#117, merged PR #131):** read-only peak envelope under detail panel (`workbench_waveform`); original files unchanged
- **Workbench cue metadata v1 (#117, merged PR #133):** schema v2 in `workbench_library.db`; load/save API; read-only cue marker on waveform
- **Workbench preview cue offset (#117, merged PR #135):** play starts at saved `cue_start_ms` via temp in-memory slice; original files unchanged
- **Workbench waveform play controls (#117, merged PR #136):** visible Play/Stop buttons removed; left-click on waveform plays from saved cue (no cue write); right-click plays temporarily from click position; double-click/Space unchanged
- **Workbench Shift+click cue set (#117, merged PR #137):** Shift+left-click on waveform sets `cue_start_ms` permanently in local library metadata; attack/loop fields preserved; original files unchanged
- **Workbench UX polish:** progress bar + status counter during analysis; classified error messages (not generic "Could not extract features")
- **Workbench short-clip handling:** samples under 0.5s skip BPM/key overclaim; UI shows Kurzclip hint; targeted librosa warning suppression
- **Workbench Windows shortcut:** optional desktop `.lnk` via `tools/windows/create_workbench_desktop_shortcut.ps1` (local helper, no installer)
- **Product pillars:** All 5 specs under [`docs/product/`](../docs/product/README.md) — #90 closed via PR #107; no open product-docs issues
- **Recently closed:** [#72](https://github.com/jannekbuengener/sample-brain/issues/72) key confidence evidence via PR #108 — [KEY_CONF_EVIDENCE.md](../docs/benchmarks/KEY_CONF_EVIDENCE.md)
- **Current focus:** EPIC-2 follow-ups — #73 vocal/no-vocal deferred after proxy spike HOLD; genre/mood data strategy; #74 ANN tracking
- **Tests:** 318 passed, 1 skipped (`pytest -q`); optional `[clap]` tests skip on HOLD vocal spike margins

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
- **Workbench cue/loop/attack metadata** — loop + attack edit modes; attack suggestion API + UI (#147–#148); loop once-preview (#149); loop repeat preview shipped (#117 follow-up)
- **Workbench global multi-folder library view** — shipped: **Alle Library-Samples** in sidebar; catalog unification planned ([`WORKBENCH_CATALOG_UNIFICATION_PLAN.md`](../docs/WORKBENCH_CATALOG_UNIFICATION_PLAN.md)) (#117 remains open)
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
| [WORKBENCH_CUE_METADATA_PLAN.md](../docs/WORKBENCH_CUE_METADATA_PLAN.md) | Cue/loop/attack metadata plan (workbench, #117) |
