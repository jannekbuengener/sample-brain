# Product Requirements — Sample Brain

## 1. Product Vision

Sample Brain is a **local-first, agent-shepherded sample, harmony and producing assistant**.
The **primary producing path** is local Workbench-first with product modes:

`Edit → Arrangement → later Live`

Edit contains Library / Sources, Browser playlist, contextual Harmonic Matches, and the classic Live Kit as an Edit tool. Arrangement owns Step Sequencer / Pattern programming and song structure. Live is later and parked under [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088). Progressive disclosure and one Python-owned musical/session authority remain binding principles.

Canonical decisions: [`docs/PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md) ([#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076)); Edit geometry evidence in [`docs/WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md`](WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md) (exclusive #905 nav thesis superseded on conflict).
A VST3 / host plugin remains a **parked optional path** ([#469](https://github.com/jannekbuengener/sample-brain/issues/469)); it is **not** the main product interface. Historical pillar notes [#90](https://github.com/jannekbuengener/sample-brain/issues/90)–[#95](https://github.com/jannekbuengener/sample-brain/issues/95) describe library/matching/context/transform capabilities that still feed the Workbench, not a VST-first product body. The former multi-screen navigation model `Screen 1 → Screen 2 → Screen 3` and exclusive Single-Workspace-only navigation are superseded as product navigation.

## 2. Target Audience

### Primary

- **FL Studio producer** — uses FL Studio as primary DAW, has large local sample collections, wants browser tags and search without leaving the DAW
- **Beatmaker** — works with kicks, snares, loops, one-shots; needs fast access to the right sound
- **Sound Designer** — builds custom sample libraries, needs consistent metadata and similarity search across variants
- **Sample library power user** — owns 50k+ samples, has outgrown folder-based navigation
- **Privacy-conscious producer** — wants local processing, no cloud upload, ownership of analysis data
- **Local Workbench producer** — builds kits and (later) patterns inside Sample Brain without requiring a DAW host

### Not primary

- Streaming-only users without local sample libraries
- Cloud-first collaboration teams (Ableton Link, Splice Sounds)
- Users expecting fully generative / AI-authored music production
- Replacement for Splice, Loopcloud, or Output Arcade
- Users whose only goal is a VST plugin inside a third-party DAW (parked path #469)

## 3. Problem Statement

Local sample libraries are the backbone of music production, yet they remain chaotic and underexploited:

- **Filesystem search is insufficient** — folder names and filenames carry limited signal. Producers spend creative time hunting instead of producing.
- **Semantic information is missing** — BPM, key, timbre, type, and character are implicit in the audio but not exposed for search or filtering.
- **Session context is lost** — tags, ratings, and groupings exist inside the DAW project but cannot be queried across the library.
- **Cloud services conflict with workflow** — Splice and Loopcloud require online access, monthly fees, and sending audio data to third parties. Many producers prefer local ownership and offline access.
- **Leaving the library to produce is friction** — producers need kit assignment and (later) pattern programming in the same local tool that already analysed the library.
- **Sample-to-track fit is manual** — finding samples that match the current track's BPM, key, and groove requires manual auditioning and pitch/time adjustment.

Sample Brain solves this by providing a local-first producing intelligence stack — library analysis, harmonic matching, Live Kit, and a planned Channel Rack / Arrangement Workbench — without uploading a single sample.

## 4. Product Positioning

### What Sample Brain is

- **Local-first** — all processing runs on the producer's machine. No cloud dependency for core functionality.
- **Private by default** — audio data never leaves the local filesystem. Analysis results stay in a local SQLite database.
- **Library intelligence plus local producing surfaces** — the system analyzes, categorises, retrieves, and (progressively) lets producers assign kits and program patterns locally. It does not generate finished songs.
- **Workbench-first producing assistant** — one persistent Workbench with progressive disclosure is the primary product path ([`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md), [`WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md`](WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md)). VST/host plugin is parked, not primary.
- **Agent-shepherded** — the repository is curated by specialized agents, not human-audit-grade governance.

### What Sample Brain is not

- Not a Splice/Loopcloud clone — no marketplace, no streaming, no social features.
- Not a generative songwriter — no AI melody/chord invention, no automatic full-track arrangement authorship, no mastering.
- Not a full DAW replacement — no mixer/sends/buses/plugin racks as core product; Channel Rack and later Arrangement stay inside the Workbench boundary.
- Not a cloud sample service — no sync, no multi-user, no hosted index.
- Not a replacement for manual curation — the system augments human decisions, it does not replace them.
- Not a system that commits sample audio to version control — samples are analysed in place; only metadata and configuration live in the repository.
- Not an FL-native tool — no FLP manipulation, no FL-native reverse engineering; FL Browser export is legacy/fallback only.

## 5. MVP Scope

This section separates what is **shipped on `main` today** (CLI + Workbench baseline) from the **Workbench-first producing target**. See [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md). Historical pillar notes [#90](https://github.com/jannekbuengener/sample-brain/issues/90)–[#95](https://github.com/jannekbuengener/sample-brain/issues/95) remain useful for library/matching/context/transform capability language; their VST-first workspace framing is superseded.

### 5.1 Shipped CLI Baseline (`main`)

The CLI pipeline is implemented, stable, and remains the **data foundation** for all product incarnations.

| Capability | Description | Status |
|---|---|---|
| **Scan** | Recursively index a local sample library into a SQLite catalog, deduplicated by content hash | ✅ Shipped |
| **Analyze** | Extract audio features via librosa: BPM, key, loudness, brightness, MFCCs, chroma | ✅ Shipped |
| **Autotype** | Classify samples by instrument type (kick, snare, pad, etc.) using rules + optional kNN | ✅ Shipped |
| **Export (FL Browser)** | Write FL Studio Browser-compatible tags from analysis results — **legacy/fallback data path**, not the main product interface | ✅ Shipped |
| **Embed / Index / Search** | Semantic search via optional CLAP embeddings, NumPy index (default), optional sqlite-vec backend (EPIC 2) | ✅ Shipped |
| **CLI** | All operations accessible via a single `sample-brain` entry point with argparse subcommands | ✅ Shipped |
| **Local Workbench (MVP)** | Folder pick, analyze, playlist/table, detail panel, audio preview, read-only waveform (`sample-brain workbench`) | ✅ Shipped (MVP) |
| **Local database** | SQLite catalog as the single source of truth for all metadata | ✅ Shipped |
| **Artifact hygiene** | No generated artifacts (database, analysis outputs, cache) committed to version control | ✅ Shipped |

```text
Scan  →  Analyze  →  Autotype  →  Export (FL fallback)
                  └→  Embed  →  Index  →  Search

Local Workbench (MVP): folder → analyze in-process → playlist + detail. Shipped follow-ups (#117, PRs #119–#149): cancel, path entry, filter, sort, detail path polish, last-folder memory, CSV export, library cache v1, library folder list, audio preview, read-only waveform envelope, **cue metadata v1**, preview from saved cue, **waveform play controls**, **Shift+click permanent cue set**, **loop region display + loop edit mode**, **attack marker + attack edit mode**, **attack suggestion (analysis + UI)**, **loop once-preview (`Loop vorhören`)**. Endless loop playback: follow-up. Original sample files never modified by workbench.
```

**Local Workbench MVP** started as a tkinter-based local purpose UI and now also has a locked QML Workbench renderer path (`LOCK_PYSIDE6_QML`; CLI flag `--qml-screen1` is historical naming). It exposes scan/analyze/classify logic plus Live Kit assignment without requiring a DAW host. **Shipped:** waveform as play surface; cue/loop/attack metadata; attack suggestion; loop once/repeat preview; library folder cache; **global library view + cross-folder text search** ([`WORKBENCH_CATALOG_UNIFICATION_PLAN.md`](WORKBENCH_CATALOG_UNIFICATION_PLAN.md)); **read-only catalog bridge** ([`WORKBENCH_CATALOG_READONLY_BRIDGE_PLAN.md`](WORKBENCH_CATALOG_READONLY_BRIDGE_PLAN.md)); Live Kit taxonomy + QML Live Kit baseline; Channel Rack / Pattern domain foundations (historical delivery [#675](https://github.com/jannekbuengener/sample-brain/issues/675)/[#678](https://github.com/jannekbuengener/sample-brain/issues/678)). **Planned (Edit → Arrangement → later Live):** classic Live Kit Edit module ([#1077](https://github.com/jannekbuengener/sample-brain/issues/1077)); Arrangement contracts/domain/UI under ACTIVE owner [#679](https://github.com/jannekbuengener/sample-brain/issues/679); later Live [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088); closed [#908](https://github.com/jannekbuengener/sample-brain/issues/908) is historical Rack projection evidence; structured local filters ([`WORKBENCH_SEARCH_UI_PLAN.md`](WORKBENCH_SEARCH_UI_PLAN.md)); controlled catalog→cache import ([`WORKBENCH_CATALOG_CACHE_IMPORT_PLAN.md`](WORKBENCH_CATALOG_CACHE_IMPORT_PLAN.md)). Start: `python -m src.cli workbench` (optional `--qml-screen1`). GUI smoke: [`WORKBENCH_GUI_SMOKE.md`](WORKBENCH_GUI_SMOKE.md).

On Windows, producer use starts from a dedicated, provenance-checked local runtime: run `git fetch origin --prune`, then `powershell -ExecutionPolicy Bypass -File .\tools\windows\install_runtime_workbench.ps1 -CreateShortcut` from a checkout. Direct `python -m src.cli workbench` remains the explicit developer-checkout path. See [`tools/windows/README.md`](../tools/windows/README.md).

### 5.2 Workbench-first producing target

Primary producing path: Edit → Arrangement → later Live (see [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md), [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075)/[#1076](https://github.com/jannekbuengener/sample-brain/issues/1076)). Capability pillars (library, matching, context, transform) still apply as **core services** consumed by the Workbench; historical VST workspace framing is superseded / parked (#469). The former multi-screen page model and exclusive Single-Workspace-only navigation are superseded.

| Capability | Description | Notes |
|---|---|---|
| **Library / Sources + playlist + Harmonic Matches** | Browse/select samples; Harmonic Matches contextual | Partially shipped (Tk + QML) in Edit |
| **Live Kit** | Assign samples into canonical kit slots | Shipped domain capability; Edit tool (#1077), not a top-level mode |
| **Channel Rack / Pattern / Step-Sequencer** | Pattern/trigger programming over kit-referenced and user channels | Domain foundations shipped (historical #675/#678); product placement in Arrangement workflow; #908 is historical projection evidence |
| **Arrangement** | Song-structure mode after Edit / Kit | **ACTIVE** owner [#679](https://github.com/jannekbuengener/sample-brain/issues/679); contracts #1082–#1084 |
| **Live** | Later performance perspective | Parked under [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088) |
| **Library browse / matching / context / transform** | Catalog intelligence feeding Workbench | Specs under [`docs/product/`](product/README.md); VST UI parts parked |
| **Optional VST/host plugin** | Parked DAW-inline surface over the same core | [#469](https://github.com/jannekbuengener/sample-brain/issues/469) — not primary |

**Not in the near Workbench slices:** mixer/sends/buses, piano-roll editor, vocal→pattern pipeline, pitching/stretch as Channel Rack prerequisite, VST shell, Live layout/MIDI/multi-track.

### 5.3 Explicitly out of scope

The following apply unless re-evaluated via [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md):

- **No cloud requirement** — no mandatory account, sync, or hosted index for core functionality
- **No marketplace** — no sample store, ratings, purchases, or community features
- **No generative songwriting** — no AI melody/chord invention, no automatic full-track arrangement authorship, no mastering
- **No heavy analysis in the audio thread** — scanning, DB access, ML, and variant rendering run asynchronously; realtime playback uses prepared/cached audio only
- **No full DAW replacement** — Channel Rack + later Arrangement are Workbench tools, not a generic DAW
- **No FL-Browser or VST dependency as the main product path** — FL export is CLI fallback; VST is parked (#469); Workbench is primary

## 6. Target Product Capabilities

### Current CLI Pipeline (stable)

```text
Scan  →  Analyze  →  Autotype  →  Export
```

All four steps are implemented and stable on `main`. The CLI pipeline remains the data foundation for all higher-level product incarnations.

### EPIC 2 — Semantic Search Foundation (completed on `main`)

```text
Scan  →  Analyze  →  Embed  →  Index  →  Search  →  Export
```

- Embedding backend with CLAP as primary candidate
- NumPy vector index (default) + optional sqlite-vec
- Text-to-sample and audio-to-audio similarity search

### Workbench-first Product Target

Canonical workflow: [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md), [`WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md`](WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md).

```text
Product modes:  Edit  →  Arrangement  →  later Live (#1088)

Edit contains:
  LIBRARY / SOURCES | ALL SAMPLES | HARMONIC MATCHES | classic LIVE KIT (tool)

Arrangement contains:
  STEP SEQUENCER / Pattern programming | song structure (#679 ACTIVE)

Live:
  later performance perspective — parked under #1088

  fed by: Library / Matching / Context / Transform cores
  optional parked path: VST/host plugin (#469)
```

- **Library Intelligence** — scan, audio analysis, autotype, keywords, title normalisation, canonical metadata
- **Harmonic & Rhythmic Matching** — key/BPM compatibility, semi-tone suggestions, groove-fit
- **Track Context Analysis** — derive track profile and missing-layer hypotheses from marked files or stems
- **Realtime Fit & Transform Engine** — variant-based recommendations (optional; not required for Pattern/Rack foundation)
- **Local Producing Workspace** — Edit → Arrangement → later Live; VST-first, multi-screen pages, and exclusive Single-Workspace-only navigation are superseded

### Long-term (EPIC 3-6 + beyond)

```text
CLI Library  →  Edit → Arrangement → later Live Workbench
                  │
                  ├── Hybrid ranking (semantic + structured metadata)
                  ├── Optional local FastAPI service
                  ├── Optional parked VST/host plugin over same core
                  └── DSP-based variant generation (pitch, time, stretch, reverse, slice) — not Arrangement v1 prerequisite
```

- FL Studio Browser export remains **legacy/fallback**
- External DAW hosting is optional, not the core workflow
- User-authored patterns are **in** product intent; Arrangement is an **ACTIVE** product mode under [#679](https://github.com/jannekbuengener/sample-brain/issues/679); generative songwriting remains **out**

## 7. User Stories

### P0 — Core pipeline

1. **As a producer**, I want to scan my sample library into a searchable catalog, so that I know which samples are available and can find them by structured criteria.

2. **As a beatmaker**, I want kicks, snares, loops, and one-shots to be auto-detected, so that I spend less time manually sorting and renaming files.

3. **As an FL Studio user**, I want browser-compatible tags exported automatically, so that my sample library is immediately usable inside my DAW workflow.

### P1 — Search and discovery

4. **As a sound designer**, I want to find samples similar to a reference audio file, so that I can quickly build layers and variations without manual listening.

5. **As a producer with a large library**, I want to search by natural language queries ("dark pad with rich low end"), so that I can find the right sound without navigating filesystem folders.

### P2 — Workflow enrichment

6. **As a privacy-conscious user**, I want all analysis to stay on my machine, so that my private audio data and creative metadata never leave my control.

7. **As a producer switching genres**, I want to reconfigure analysis and typing rules per project, so that classification matches the current musical context.

8. **As a power user**, I want reproducible and scriptable pipeline steps, so that I can batch-process libraries and integrate the toolkit into my own automation.

## 8. Product Principles

- **Local-first** — core functionality works fully offline. Cloud services are optional additions, never requirements.
- **Privacy by default** — no audio data or analysis results are sent anywhere unless the user explicitly opts in.
- **Rebuildable generated artifacts** — every artifact (database, index, cache) can be regenerated from source. Nothing generated is committed.
- **Explicit over magical** — the system explains what it knows, what it guesses, and why. No black-box scoring without traceability.
- **Small composable pipeline steps** — each CLI subcommand does one thing well. Pipes and scripting are first-class workflows.
- **No fake intelligence** — classification confidence, feature extraction certainty, and search ranking are surfaced honestly. The system does not pretend to understand music.
- **Workbench workflow over demo wow-factor** — kit → channel rack → arrangement inside Sample Brain beats a disconnected dashboard or a host-plugin detour.
- **Deterministic by default** — the same sample and same pipeline version must produce the same result. Stochastic elements are opt-in and documented.

## 9. Non-Goals

The following are explicitly **not** goals for Sample Brain. They are out of scope at all planned stages unless re-evaluated via [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md):

- **No sample audio in the repository** — samples are analysed in place. The repo contains only code, configuration, and documentation. No `.wav`, `.mp3`, `.flac`, or similar files are committed.
- **No cloud requirement** — no mandatory account, login, API key, or network call for core pipeline operations.
- **No automatic model download without explicit opt-in** — ML dependencies (torch, transformers, CLAP) are installed and downloaded only when the user activates the embedding pipeline.
- **No generative songwriting** — Sample Brain does not invent melodies, chord progressions, or automatic full-track arrangements. **User-authored** Channel Rack patterns and Arrangement mode (**ACTIVE** under [#679](https://github.com/jannekbuengener/sample-brain/issues/679)) **are** in product intent.
- **No marketplace or sample sharing** — no store, no ratings, no user profiles, no community features.
- **No social or collaboration features** — single-user local tool. Multi-user support is not planned.
- **No FAISS or vector search in MVP** — semantic search is EPIC 2, explicitly gated behind a stable foundation pipeline. Vector dependencies are introduced deliberately, not organically.
- **No real-time audio analysis in the audio thread** — heavy scanning, DB access, indexing, and ML inference must not run in the audio thread. Realtime playback uses prepared/cached audio and precomputed metadata only.
- **No FL-native reverse engineering** — no FLP parsing/manipulation, no FL Studio internal API access. Integration uses documented public interfaces (filesystem tags; optional later plugin APIs if unparked).
- **No FL-Browser or VST dependency as the main product path** — FL export is legacy/fallback; VST is parked (#469); Workbench is primary.
- **No committed runtime state** — no private samples, DBs, indexes, model caches, or local sample paths in the repository.

## 10. Success Criteria

### MVP success

The MVP is successful when:

1. A producer can scan a local library of any size with `sample-brain scan <root>`
2. Samples are consistently catalogued in SQLite with deduplication by content hash
3. `sample-brain analyze` extracts BPM, key, loudness, brightness, MFCCs, and chroma without crashing on supported formats
4. `sample-brain autotype` produces usable instrument-type tags (kick, snare, pad, loop, etc.) without requiring a GPU or cloud service
5. `sample-brain export_fl` writes tags to an FL Studio Browser location that the DAW can read
6. All generated artifacts (DB, reports, caches) are excluded from version control
7. The CLI workflow is documented and reproducible from a fresh clone

### EPIC 2 success

EPIC 2 (Semantic Search Foundation) is successful when:

1. Embedding models are versioned and registered in the SQLite catalog
2. Sample embeddings are reproducible: the same sample + same model version → same vector
3. Semantic search (text-to-sample) works locally without cloud calls
4. Audio-to-audio similarity search works from a reference file
5. All FAISS index artifacts are rebuildable and excluded from version control
6. The CLI `embed`, `index_build`, and `search` subcommands are stable and documented
7. Optional dependencies (torch, transformers) are cleanly separated from the core install
