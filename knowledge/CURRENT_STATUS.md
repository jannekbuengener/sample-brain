# CURRENT_STATUS

## Live State

- **Branch:** `main` @ `5aa7e25` (feat: add matching suggestions V1 for loaded rows; PRs #206/#208)
- **Open PRs:** none
- **Open issues:** 42 — Track Deconstruction (#227-#268); EPIC-2 follow-ups (#196 HOLD, #73 partial, #74 tracking); recent (#212-#219). [#198](https://github.com/jannekbuengener/sample-brain/issues/198) **closed** 2026-08 (matching suggestions shipped via #208).
- **Local Workbench:** `sample-brain workbench` — tkinter MVP shipped; parent epic [#117](https://github.com/jannekbuengener/sample-brain/issues/117) **closed** 2026-07-10; matching suggestions V1 shipped via [#208](https://github.com/jannekbuengener/sample-brain/issues/208) (PR #209); [#198](https://github.com/jannekbuengener/sample-brain/issues/198) **closed** 2026-08
  - Shipped under #117: folder analysis, sample table filter/sort, library cache + multi-folder view, catalog read-only bridge, catalog→cache import (#192), FL export (#191), analysis-limit persistence (#190), cue/loop/attack metadata, audio preview + waveform, structured search UI, runtime hotfix PR #199
  - **Playlist workflow V1 shipped:** [#203](https://github.com/jannekbuengener/sample-brain/issues/203) closed (PR #204) — per-row `+ Playlist`, dialog, local song-context assignment; [#205](https://github.com/jannekbuengener/sample-brain/issues/205) closed (PR #206) — sidebar **Playlists**, load assigned samples into existing table
- **Dependency HOLD:** [#196](https://github.com/jannekbuengener/sample-brain/issues/196) — `numpy>=2.5` blocked by `numba` pin; Dependabot PR #103 closed (not merged)
- **Product pillars:** All 5 specs under [`docs/product/`](../docs/product/README.md) — #90 closed via PR #107; no open product-docs issues
- **Recently closed:** [#205](https://github.com/jannekbuengener/sample-brain/issues/205) playlist detail view (PR #206); [#203](https://github.com/jannekbuengener/sample-brain/issues/203) playlist assignment (PR #204); [#117](https://github.com/jannekbuengener/sample-brain/issues/117) Workbench epic (2026-07-10); [#72](https://github.com/jannekbuengener/sample-brain/issues/72) key confidence evidence via PR #108 — [KEY_CONF_EVIDENCE.md](../docs/benchmarks/KEY_CONF_EVIDENCE.md)
- **Current focus:** Track Deconstruction docs (#227-#268); EPIC-2 follow-ups — #196 dependency HOLD; #73 vocal/no-vocal deferred after proxy spike HOLD; genre/mood data strategy; #74 ANN tracking
- **Tests:** CI green on `main`; local `pytest -q` — 583 passed, 1 skipped (last full-suite run on `main`)

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
- **Local Workbench** — tkinter MVP: enter or pick folder path (last folder restored from `~/.sample-brain/`), library folder list with add/remove (cache-only), cancel mid-analysis, filter/sort sample table, segment-wise detail paths, CSV export, library cache for re-analysis skip, waveform play surface (left = saved cue, right = click position), double-click/Space preview, read-only waveform envelope + cue marker, run in-process analyze + rule-based type; **song-context playlists V1** — per-row `+ Playlist` assignment ([#203](https://github.com/jannekbuengener/sample-brain/issues/203), PR #204), sidebar playlist list and load into table ([#205](https://github.com/jannekbuengener/sample-brain/issues/205), PR #206) (`workbench` subcommand)
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

## Track Deconstruction (#227-#268)

GitHub reconciliation complete. Five meta-parents are **OPEN** with docs contracts in progress or planned. No runtime implementation exists on `main`.

### Parent hierarchy

```text
#227 [META][TRACK] Track Intelligence & Track Map
  └── #232 Track Map JSON contract  [READY_TO_DOCUMENT] → docs/TRACK_MAP_V1.md
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

### Track Map v1 contract

[#232](https://github.com/jannekbuengener/sample-brain/issues/232) is `OPEN` / `READY_TO_DOCUMENT`. The canonical contract is documented in [`docs/TRACK_MAP_V1.md`](docs/TRACK_MAP_V1.md) (PR #269, docs-only). Runtime production is tracked in #233 and downstream slices.

### Research decisions (recorded, not implemented)

| Topic | Finding |
|-------|---------|
| Beat/Downbeat | Beat This `final0` is provisional primary candidate (backend #236); `librosa` is the lightweight fallback. Not yet confirmed by private Techno audio tests. |
| Structure | StructureV1 (#265) uses classical audio analysis: self-similarity, recurrence, novelty, energy/low-end/onsets/timbre. No large Techno model as Core. |
| All-In-One | #235 is comparison/experimental only — not a Core path. |
| Stems | `python-audio-separator` is the integration wrapper; `htdemucs` / `htdemucs_ft` are provisional baselines. Exact checkpoint/weight-license review required before any default selection (#246, #247). |
| Loops | No own ML model for loop selection; candidates are bar-aligned from downbeat indices (#251, #266). |
| Producer groups | `kick_bass` = kick attack/body + musical bassline, not `drums + bass` (#268). No perfect mixer-spur reconstruction promised. |
| Private test data | Own tracks and sample library exist for private pilots; no private audio, paths, or outputs in repo documentation. |

---

## What Is Not Done

- **Default switch to sqlite-vec** — blocked until latency gates PASS
- **Tier B CLAP search-quality evidence** — Phase 1+2 merged; 4/6 classes on main; vocal/no-vocal proxy spike **HOLD_VOCAL_PROXY_FAILED**; genre/mood remain (#73 OPEN)
- **Workbench Matching-/Vorschlagsansicht** — [#208](https://github.com/jannekbuengener/sample-brain/issues/208) shipped (PR #209); [#198](https://github.com/jannekbuengener/sample-brain/issues/198) closed (plan drafted in `WORKBENCH_MATCHING_SUGGESTIONS_PLAN.md`); semantic search remains #73; sqlite-vec/ANN remains #74
- **Workbench playlist management (optional later)** — rename/delete playlist; remove sample from playlist — not scoped; no open issue
- **numpy 2.5 / numba unblock** — tracked via [#196](https://github.com/jannekbuengener/sample-brain/issues/196) HOLD; do not merge until `numba` supports `numpy>=2.5`
- **Phase 5 tags + FTS5 MVP** — not started (roadmap Phase 5)
- **Large-scale private-sample validation** — synthetic/benchmark fixtures only
- **EPIC 3–6** — not started
- **Track Deconstruction** (#227-#268) — docs contracts only; no runtime on `main`. Track Map v1 contract documented ([`TRACK_MAP_V1.md`](docs/TRACK_MAP_V1.md)); runtime (#233, #236, #265) and downstream contracts (Arrangement, Stems, Assets, Pack) remain future work.

## Key Docs

| Document | Purpose |
|----------|---------|
| [ADR-0004](../docs/adr/ADR-0004-sqlite-vec-search-backend.md) | Accepted sqlite-vec strategy |
| [ADR-0005](../docs/adr/ADR-0005-search-quality-evaluation.md) | Search quality evaluation (Tier A/B) |
| [SQLITE_VEC_ROADMAP.md](../docs/SQLITE_VEC_ROADMAP.md) | Phases 0–8 (all done) |
| [SQLITE_VEC_GATE_EVIDENCE.md](../docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md) | Measured backend gates |
| [SEARCH_QUALITY_EVIDENCE.md](../docs/benchmarks/SEARCH_QUALITY_EVIDENCE.md) | Tier A relevance gates |
| [WORKBENCH_CUE_METADATA_PLAN.md](../docs/WORKBENCH_CUE_METADATA_PLAN.md) | Cue/loop/attack metadata plan (workbench, #117 closed) |
| [WORKBENCH_GUI_SMOKE.md](../docs/WORKBENCH_GUI_SMOKE.md) | Workbench GUI smoke status (incl. playlist V1) |
| [WORKBENCH_MATCHING_SUGGESTIONS_PLAN.md](../docs/WORKBENCH_MATCHING_SUGGESTIONS_PLAN.md) | Matching-/Vorschlagsansicht V1 plan (#198) |
| [TRACK_MAP_V1.md](../docs/TRACK_MAP_V1.md) | Canonical Track Map v1 contract (#232, parent #227) |
