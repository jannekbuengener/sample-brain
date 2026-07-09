# Product Requirements — Sample Brain

## 1. Product Vision

Sample Brain is a **local-first, agent-shepherded sample, harmony and producing assistant**.  
The first product incarnation is a **VST3 browser/assistant plugin**. A **standalone producing application** follows later from the same core.  
The product is organized around 5 pillars: **Library Intelligence**, **Harmonic & Rhythmic Matching**, **Track Context Analysis**, **Realtime Fit & Transform Engine**, and **VST-first Producing Workspace**.

See Product Target Issues [#90](https://github.com/jannekbuengener/sample-brain/issues/90)–[#95](https://github.com/jannekbuengener/sample-brain/issues/95) for the full target definition.

## 2. Target Audience

### Primary

- **FL Studio producer** — uses FL Studio as primary DAW, has large local sample collections, wants browser tags and search without leaving the DAW
- **Beatmaker** — works with kicks, snares, loops, one-shots; needs fast access to the right sound
- **Sound Designer** — builds custom sample libraries, needs consistent metadata and similarity search across variants
- **Sample library power user** — owns 50k+ samples, has outgrown folder-based navigation
- **Privacy-conscious producer** — wants local processing, no cloud upload, ownership of analysis data
- **VST3-host user** — works in any VST3-capable DAW and wants inline sample intelligence without leaving the DAW

### Not primary

- Streaming-only users without local sample libraries
- Cloud-first collaboration teams (Ableton Link, Splice Sounds)
- Users expecting fully generative music production
- Replacement for Splice, Loopcloud, or Output Arcade

## 3. Problem Statement

Local sample libraries are the backbone of music production, yet they remain chaotic and underexploited:

- **Filesystem search is insufficient** — folder names and filenames carry limited signal. Producers spend creative time hunting instead of producing.
- **Semantic information is missing** — BPM, key, timbre, type, and character are implicit in the audio but not exposed for search or filtering.
- **Session context is lost** — tags, ratings, and groupings exist inside the DAW project but cannot be queried across the library.
- **Cloud services conflict with workflow** — Splice and Loopcloud require online access, monthly fees, and sending audio data to third parties. Many producers prefer local ownership and offline access.
- **DAW integration is brittle** — existing integration relies on filesystem browser tags (FL Studio) or export formats. A native VST3 plugin provides inline access without context switches.
- **Sample-to-track fit is manual** — finding samples that match the current track's BPM, key, and groove requires manual auditioning and pitch/time adjustment.

Sample Brain solves this by providing a local-first producing intelligence stack — from library analysis and harmonic matching through to a VST3 producing workspace — without uploading a single sample.

## 4. Product Positioning

### What Sample Brain is

- **Local-first** — all processing runs on the producer's machine. No cloud dependency for core functionality.
- **Private by default** — audio data never leaves the local filesystem. Analysis results stay in a local SQLite database.
- **Library intelligence, not co-producer** — the system analyzes, categorises, and retrieves. It does not generate finished music.
- **VST3-first producing assistant** — the primary product interface is a VST3 browser/assistant plugin. A standalone producing app follows later from the same core.
- **Agent-shepherded** — the repository is curated by specialized agents, not human-audit-grade governance.

### What Sample Brain is not

- Not a Splice/Loopcloud clone — no marketplace, no streaming, no social features.
- Not a generative songwriter — no melody generation, no arrangement, no mastering.
- Not a cloud sample service — no sync, no multi-user, no hosted index.
- Not a replacement for manual curation — the system augments human decisions, it does not replace them.
- Not a system that commits sample audio to version control — samples are analysed in place; only metadata and configuration live in the repository.
- Not an FL-native tool — no FLP manipulation, no FL-native reverse engineering, no FL-Browser dependency as the main product path.

## 5. MVP Scope

This section separates what is **shipped on `main` today** (CLI baseline) from the **VST-first product MVP** (target). See Product Target Issues [#90](https://github.com/jannekbuengener/sample-brain/issues/90) (parent) and [#91](https://github.com/jannekbuengener/sample-brain/issues/91)–[#95](https://github.com/jannekbuengener/sample-brain/issues/95) (five pillars) for the full target definition.

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

**Local Workbench MVP** is a tkinter-based local purpose UI — not the VST product target. It exposes scan/analyze/classify logic on a chosen folder without FL Studio export, semantic search, or cloud sync. **Shipped:** waveform as play surface; cue/loop/attack metadata edit modes; attack suggestion; loop once/repeat preview; library folder cache. **Planned next:** global multi-folder library view, catalog unification ([`WORKBENCH_CATALOG_UNIFICATION_PLAN.md`](WORKBENCH_CATALOG_UNIFICATION_PLAN.md)). Start: `python -m src.cli workbench`. GUI smoke: [`WORKBENCH_GUI_SMOKE.md`](WORKBENCH_GUI_SMOKE.md).

On Windows, a desktop shortcut can be created locally (not shipped as an installer): run `powershell -ExecutionPolicy Bypass -File .\tools\windows\create_workbench_desktop_shortcut.ps1` from the repo root. See [`tools/windows/README.md`](../tools/windows/README.md).

### 5.2 VST-first Product MVP (target)

The first product incarnation is a **VST3 browser/assistant plugin** sharing the same SQLite-backed core. A standalone producing app follows later. Pillars map to Issues [#94](https://github.com/jannekbuengener/sample-brain/issues/94) (Library), [#91](https://github.com/jannekbuengener/sample-brain/issues/91) (Matching), [#95](https://github.com/jannekbuengener/sample-brain/issues/95) (Context), [#92](https://github.com/jannekbuengener/sample-brain/issues/92) (Transform), [#93](https://github.com/jannekbuengener/sample-brain/issues/93) (Workspace).

**Pillar contracts:** implementable specs for all five pillars live under [`docs/product/`](product/README.md). PRD §5–6 remain the vision layer; pillar specs define fields, boundaries, and shipped-vs-target gaps.

| Capability | Description | Pillar |
|---|---|---|
| **VST3 plugin** | First product body; CLAP plugin format optional later; FL Studio is first target host, not a hard dependency | [#93](https://github.com/jannekbuengener/sample-brain/issues/93) Workspace |
| **Library browse** | Sample grid/list with filter and search over the SQLite catalog | [#94](https://github.com/jannekbuengener/sample-brain/issues/94) Library |
| **Preview** | Audio preview with waveform; playback of prepared audio only (no heavy work in the audio thread) | [#93](https://github.com/jannekbuengener/sample-brain/issues/93) Workspace |
| **Basis matching** | Key/BPM compatibility scoring and fit suggestions for the current context | [#91](https://github.com/jannekbuengener/sample-brain/issues/91) Matching |
| **Simple variant preview** | Variant-based recommendations (target BPM, semitone shift) with async background rendering | [#92](https://github.com/jannekbuengener/sample-brain/issues/92) Transform |
| **Drag & drop** | Drag samples or variants into the host DAW (MIDI/audio) | [#93](https://github.com/jannekbuengener/sample-brain/issues/93) Workspace |

**Not in the product MVP (later):** full track context analysis from host integration ([#95](https://github.com/jannekbuengener/sample-brain/issues/95)), advanced transform pitch/sync modes, standalone app, hybrid recommendation engine (EPIC 3).

### 5.3 Explicitly out of scope

The following apply to **both** the shipped CLI baseline and the VST-first product target unless re-evaluated:

- **No cloud requirement** — no mandatory account, sync, or hosted index for core functionality
- **No marketplace** — no sample store, ratings, purchases, or community features
- **No generative music production** — no melody generation, arrangement, or mastering
- **No heavy analysis in the audio thread** — scanning, DB access, ML, and variant rendering run asynchronously; the plugin plays back prepared data only
- **No DAW replacement** — Sample Brain is a producing assistant, not a full DAW or arrangement tool
- **No FL-Browser dependency as the main product path** — FL Studio Browser export remains a CLI fallback; the VST3 plugin is the primary interface

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

### VST-first Product Target (Issues #90–#95)

All five pillar specs are documented under [`docs/product/`](product/README.md) (merged via PR #105 and PR #106). Parent scope #90 closes when backlog/status docs reflect the completed spec set.

The product target reorganizes into 5 pillars:

```text
┌────────────────────────────────────────────────────────┐
│                    VST3 / Standalone                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ Library  │  │ Matching │  │ Context  │  │Transf. │ │
│  │Intell.   │  │Harmonic  │  │Analysis  │  │Engine  │ │
│  │          │  │Rhythmic  │  │          │  │Fit+Var │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───┬────┘ │
│       └──────────────┴──────────────┴────────────┘      │
│                           │                              │
│                    ┌──────┴──────┐                       │
│                    │  Producing  │                       │
│                    │  Workspace  │                       │
│                    │ (VST3/SA)   │                       │
│                    └─────────────┘                       │
└────────────────────────────────────────────────────────┘
```

- **Library Intelligence** — scan, audio analysis, autotype, keywords, title normalisation, canonical metadata
- **Harmonic & Rhythmic Matching** — key/BPM compatibility, semi-tone suggestions, groove-fit
- **Track Context Analysis** — derive track profile and missing-layer hypotheses from marked files or stems
- **Realtime Fit & Transform Engine** — variant-based recommendations (-12/+12 semitones, pitch/sync modes)
- **VST-first Producing Workspace** — VST3 browser/assistant plugin (CLAP optional later); standalone later from same core

### Long-term (EPIC 3-6 + beyond)

```text
CLI Library  →  Plugin / Standalone App
                  │
                  ├── Hybrid ranking (semantic + structured metadata)
                  ├── Local FastAPI service
                  ├── Standalone producing app (from same core)
                  └── DSP-based variant generation (pitch, time, stretch, reverse, slice)
```

- FL Studio Browser export becomes **legacy/fallback** — not the main product path
- FL Studio remains the first target host but is **not a hard product dependency**
- All VST3-capable DAWs are potential hosts

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
- **DAW workflow over demo wow-factor** — integration beats flashy standalone UI. Exporting useful metadata into the DAW is more valuable than a pretty but disconnected dashboard.
- **Deterministic by default** — the same sample and same pipeline version must produce the same result. Stochastic elements are opt-in and documented.

## 9. Non-Goals

The following are explicitly **not** goals for Sample Brain. They are out of scope at all planned stages unless re-evaluated:

- **No sample audio in the repository** — samples are analysed in place. The repo contains only code, configuration, and documentation. No `.wav`, `.mp3`, `.flac`, or similar files are committed.
- **No cloud requirement** — no mandatory account, login, API key, or network call for core pipeline operations.
- **No automatic model download without explicit opt-in** — ML dependencies (torch, transformers, CLAP) are installed and downloaded only when the user activates the embedding pipeline.
- **No generative music production** — Sample Brain does not create melodies, chord progressions, drum patterns, or arrangements.
- **No marketplace or sample sharing** — no store, no ratings, no user profiles, no community features.
- **No social or collaboration features** — single-user local tool. Multi-user support is not planned.
- **No FAISS or vector search in MVP** — semantic search is EPIC 2, explicitly gated behind a stable foundation pipeline. Vector dependencies are introduced deliberately, not organically.
- **No real-time audio analysis in the audio thread** — heavy scanning, DB access, indexing, and ML inference must not run in the audio thread. The pipeline generates data ahead of time; the plugin only plays back prepared audio and displays precomputed metadata.
- **No FL-native reverse engineering** — no FLP parsing/manipulation, no FL Studio internal API access. Integration uses documented public interfaces (VST3, filesystem tags).
- **No FL-Browser dependency as the main product path** — FL Studio Browser export is a legacy/fallback integration. The main product path is the VST3 plugin.
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
