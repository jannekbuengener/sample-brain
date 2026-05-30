# Product Requirements — Sample Brain

## 1. Product Vision

Sample Brain is a local-first sample intelligence toolkit for producers that turns private sample libraries into searchable, explainable, DAW-friendly creative infrastructure.

## 2. Target Audience

### Primary

- **FL Studio producer** — uses FL Studio as primary DAW, has large local sample collections, wants browser tags and search without leaving the DAW
- **Beatmaker** — works with kicks, snares, loops, one-shots; needs fast access to the right sound
- **Sound Designer** — builds custom sample libraries, needs consistent metadata and similarity search across variants
- **Sample library power user** — owns 50k+ samples, has outgrown folder-based navigation
- **Privacy-conscious producer** — wants local processing, no cloud upload, ownership of analysis data

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
- **DAW integration is brittle** — FL Studio's browser works with filesystem tags, but no open-source tool systematically generates them from audio content.

Sample Brain solves this by running a local analysis pipeline that enriches a producer's library with structured, searchable metadata — without uploading a single sample.

## 4. Product Positioning

### What Sample Brain is

- **Local-first** — all processing runs on the producer's machine. No cloud dependency for core functionality.
- **Private by default** — audio data never leaves the local filesystem. Analysis results stay in a local SQLite database.
- **Library intelligence, not co-producer** — the system analyzes, categorises, and retrieves. It does not generate finished music.
- **Analysis and search system** — a CLI toolkit that reads samples and produces structured metadata and tags.
- **DAW-near, not DAW-dependent** — the pipeline works independently; DAW export is a convenience layer, not the product core.

### What Sample Brain is not

- Not a Splice/Loopcloud clone — no marketplace, no streaming, no social features.
- Not a generative songwriter — no melody generation, no arrangement, no mastering.
- Not a cloud sample service — no sync, no multi-user, no hosted index.
- Not a replacement for manual curation — the system augments human decisions, it does not replace them.
- Not a system that commits sample audio to version control — samples are analysed in place; only metadata and configuration live in the repository.

## 5. MVP Scope

### MVP must support

| Capability | Description |
|---|---|
| **Scan** | Recursively index a local sample library into a SQLite catalog, deduplicated by content hash |
| **Analyze** | Extract audio features via librosa: BPM, key, loudness, brightness, MFCCs, chroma |
| **Autotype** | Classify samples by instrument type (kick, snare, pad, etc.) using rules + optional kNN |
| **Export** | Write FL Studio Browser-compatible tags from analysis results |
| **CLI** | All operations accessible via a single `sample-brain` entry point with argparse subcommands |
| **Local database** | SQLite catalog as the single source of truth for all metadata |
| **Artifact hygiene** | No generated artifacts (database, analysis outputs, cache) committed to version control |

### MVP explicitly does not include

- Semantic / vector search (FAISS, CLAP)
- Desktop graphical user interface
- HTTP API / FastAPI service
- Recommendation engine
- Cloud sync or multi-user
- Real-time audio analysis
- DAWs other than FL Studio
- Sample generation or transformation

## 6. Target Product Capabilities

### Short-term (current MVP)

```text
Scan  →  Analyze  →  Autotype  →  Export
```

All four steps are implemented and stable on `main`.

### Medium-term (EPIC 2 — Semantic Search Foundation)

```text
Scan  →  Analyze  →  Embed  →  Index  →  Search  →  Export
```

- Embedding backend with CLAP as primary candidate
- Local vector index via FAISS
- Text-to-sample and audio-to-audio similarity search

### Long-term (EPIC 3-6)

```text
Scan  →  Analyze  →  Embed  →  Index  →  Search  →  Recommend  →  Export / DAW Workflow
```

- Hybrid ranking (semantic + structured metadata)
- Local FastAPI service
- Desktop UI (React/Tauri)
- DAW workflow integration (FL Studio, Ableton, Reaper)
- DSP-based re-imagine / variant generation

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
- **No real-time audio processing** — the pipeline is batch-oriented. Real-time analysis within the DAW is not a goal.
- **No DAW plugin SDK** — integration happens through metadata export (FL Studio tags, future Reaper/Ableton formats). VST3, AU, or AAX plugins are not planned.

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
