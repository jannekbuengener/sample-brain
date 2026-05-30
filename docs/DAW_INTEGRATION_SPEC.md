# DAW Integration Spec — Sample Brain

## 1. Purpose

This document defines the current and planned DAW integration strategy for Sample Brain. It covers the short-term anchor (FL Studio Browser tags), medium-term improvements, and long-term research for additional DAWs.

**Key principle:** DAW integration is a metadata export layer, not a real-time plugin. Sample Brain runs its pipeline independently; the DAW consumes the enriched metadata through its native browsing and tagging mechanisms.

---

## 2. Current State

### 2.1 FL Studio Browser Tags (Stable)

The only implemented DAW integration is FL Studio Browser tag export via `sample-brain export_fl`.

**How it works:**

1. `export_fl.py` reads sample metadata from the SQLite catalog (path, BPM, key, type, brightness, loudness, loop/oneshot)
2. Assembles tag strings per sample (max 5 tags by default)
3. Writes a `Tags` file to the FL Studio User Data directory at:
   `<FL_USER_DATA>\FL Studio\Settings\Browser\Tags`
4. FL Studio reads this file on startup and displays tags in the Browser

**Tag sources per sample:**

| Tag Source | Example | Priority |
|------------|---------|----------|
| `pred_type` (from autotype) | `Kick`, `Snare`, `Pad`, `Loop` | 1 (highest) |
| Filename regex match | `808`, `riser`, `clap` | 2 (fallback) |
| Brightness | `Bright`, `Dark` | 3 |
| Loudness | `Punchy`, `Clean` | 4 |
| Duration class | `OneShot`, `Loop` | 5 |
| Key | `Cmaj`, `Fmin` | 6 |
| BPM | `128BPM` | 7 |

**Limitations of current implementation:**

- `SAMPLE_ROOTS` is hardcoded in `src/config.py` — tag file paths rely on it for relative path resolution
- `MAX_TAGS = 5` is hardcoded in `src/export_fl.py` — not configurable via CLI
- No test fixtures for export output validation
- Only FL Studio is supported
- Tag file format is FL Studio-specific (see Section 5.1)
- No incremental export — full rewrite on every run

---

## 3. Supported DAWs

### 3.1 FL Studio (Short-term Anchor)

**Integration method:** Browser Tag file

**File format:**

```
@TagCase=*
Kick,Snare,HiHat-Closed,Pad,Loop,Dark,Bright,Punchy,Atmospheric
"<SAMPLE_LIBRARY_ROOT>\Kick\my_kick.wav",Kick,Punchy,Bright,OneShot
"<SAMPLE_LIBRARY_ROOT>\Loop\drum_loop.wav",Loop,Bright,Drum Loop
```

- First line: `@TagCase=*` (case-insensitive matching)
- Second line: comma-separated list of all tags used in the file
- Subsequent lines: file path (quoted if contains commas or spaces) + assigned tags
- FL Studio reads this file on startup (no hot-reload; restart required)

**Current status:** ✅ Implemented and stable

**Known issues:**
- Path resolution assumes `SAMPLE_ROOTS` can derive a library root — this breaks if samples live on different drives
- No validation that the FL User Data path actually exists or is writable

**Near-term improvements (EPIC 5, Issue 23):**

| Improvement | Priority | Notes |
|-------------|----------|-------|
| Configurable `--max-tags` CLI flag | P1 | Currently hardcoded 5 |
| Validate FL User Data path before writing | P1 | Fail early with clear message |
| Document edge cases (unicode paths, missing features, BPM=0) | P1 | In README or export doc |
| Basic export output tests or validation | P1 | Compare tag file structure, not content |
| Incremental export (only update changed samples) | P2 | Reduce full rewrite overhead |

### 3.2 Ableton Live (Planned Research)

**Integration method:** Metadata file in Ableton's file database or `.alc` clip templates

**Current status:** ❌ Not implemented. Research required.

**Research questions (EPIC 5, Issue 25):**
- Can Ableton read external metadata files for its Browser search?
- Is there a programmatic way to inject tags into Ableton's `Library.cfg` or content database?
- Can sample analysis results be embedded into Ableton `.alc` clip files?
- What metadata formats does Ableton recognise (XMP, BWF, AATranslator)?

**Initial assessment (needs verification):** Ableton's Browser relies on its own content analysis. External metadata injection is not a documented extension point. Candidate integration paths to evaluate:
- Add metadata to broadcast wave (BWF) chunks in `.wav` files (requires write access verification)
- Explore Ableton's `Library.cfg` or content database (fragile, version-specific — needs validation)
- Accept that Ableton integration is limited without a plugin SDK

### 3.3 Reaper (Planned Research)

**Integration method:** Reaper uses filesystem-based media explorer metadata. It supports:
- BWF (broadcast wave) chunks for embedded metadata
- Sidecar `.rpp` or `.reapeaks` files
- Native `Media Explorer` database with custom tag columns

**Current status:** ❌ Not implemented. Research required.

**Initial assessment (needs verification):** Reaper appears more open to external metadata than FL Studio or Ableton. Candidate integration paths to evaluate:
- Write BWF chunks (iXML or bext) with BPM/key/type data — needs DAW-specific validation
- Generate `.reapeaks` files with embedded tags — format research required
- Media Explorer user-defined metadata fields — access path needs verification

### 3.4 Other DAWs (Not Planned)

| DAW | Assessment | Priority |
|-----|-----------|----------|
| **Logic Pro** | macOS-only, closed metadata format | Not planned |
| **Bitwig** | Linux/macOS/Windows, scriptable via API | Future research candidate |
| **Studio One** | Closed format, limited extension points | Not planned |
| **Cubase/Nuendo** | MediaBay has metadata import, but format is proprietary | Not planned |
| **MPC (Akai)** | Standalone/hybrid, no public metadata integration | Not planned |

---

## 4. Integration Strategy

### 4.1 Short-term (Current — EPIC 5)

```
FL Studio  ←──  CLI export_fl  ←──  SQLite catalog
```

- FL Studio Browser Tags are the only supported export
- Focus on stability, configurable limits, and edge-case handling
- Documentation of tag format and export workflow

### 4.2 Medium-term (Planned — EPIC 5+)

```
FL Studio  ←──  CLI export_fl  ←──  SQLite catalog
Ableton    ←──  research/adapt   ←──  SQLite catalog
Reaper     ←──  BWF chunks      ←──  SQLite catalog
```

- Research Ableton and Reaper integration paths
- Implement metadata embedding (BWF chunks) as a candidate cross-DAW metadata strategy, subject to DAW-specific validation
- Support project-context search fields (BPM, key, target type) as search filters

### 4.3 Long-term (Future)

```
FL Studio  ←──  CLI export_fl  ←──  SQLite catalog
Ableton    ←──  dedicated export  ←──  SQLite catalog
Reaper     ←──  BWF + peaks      ←──  SQLite catalog
Local API  ←──  FastAPI layer    ←──  SQLite catalog
Desktop UI ←──  audio preview    ←──  SQLite catalog
```

- DAW-agnostic metadata export layer
- Local API so DAW scripts can query the catalog without CLI overhead
- Desktop UI with drag-and-drop from sample search results into DAW

---

## 5. Format Specifications

### 5.1 FL Studio Browser Tag File

```
Location: <FL_USER_DATA>/FL Studio/Settings/Browser/Tags
Encoding: UTF-8
Line separator: \n
```

**Format rules:**
- Line 1: `@TagCase=*`
- Line 2: comma-separated, sorted tag vocabulary
- Lines 3+: `<quoted_path>,<tag1>,<tag2>,...`
- Paths are quoted (`"..."`) if they contain commas, spaces, or double quotes
- Tags are plain text, no quoting unless they contain commas or spaces
- Current implementation uses a default/hardcoded max tag limit; future CLI work should make it configurable
- Missing or null features result in an empty tag slot (not a crash)

### 5.2 Broadcast Wave Format (BWF) — Planned

**Not implemented.** Intended for Reaper and DAWs that read embedded audio metadata.

- Standard EBU Tech 3285 (broadcast wave)
- iXML chunk for BPM and key metadata
- bext chunk for description and originator info
- Preservation of original audio data (metadata chunks are additive)

---

## 6. Export Layer Architecture

### 6.1 Current architecture

```
CLI (export_fl)  →  export_fl.py  →  SQLAlchemy query  →  Tag file write
```

- Single file: `src/export_fl.py`
- Direct dependency on `src/config.py` for `SAMPLE_ROOTS`
- Single output format (FL Studio Tags)

### 6.2 Target architecture

```
CLI (export_fl)  →  ExportDispatcher  →  FormatEncoder
                              │                    ├── FLStudioTagEncoder
                              │                    ├── BwfEncoder (future)
                              │                    └── ... (future)
                              │
                              ▼
                        SQLite catalog
```

- `ExportDispatcher` selects encoder based on CLI flag (`--format`)
- Each encoder implements a common interface:
  - `encode(sample_data: list[dict]) -> str | bytes`
  - `write(output_path: Path) -> None`
  - `supported_formats() -> list[str]`
- Encoders do not own SQLite queries — they receive structured sample data

### 6.3 Encoder rules

- Encoders must not crash on missing metadata (graceful omission)
- Encoders must not modify the SQLite catalog
- Encoders must not export sample audio files
- Encoders must document their output format and limitations
- Encoders may validate output paths but must not create files outside the specified destination

---

## 7. Test Fixtures and Validation

### 7.1 Current state
- No test fixtures for export output
- Manual verification only

### 7.2 Target state

- Synthetic sample seeds with known BPM/key/type for reproducible tag output
- Tag file comparison against expected format (structure, not exact values)
- Edge-case seeds: missing features, BPM=0, key=None, unicode paths, very long paths, special characters in tags

### 7.3 Validation criteria

| Criterion | Validation |
|-----------|------------|
| Tag file header is correct | First line `@TagCase=*`, second line sorted tag vocabulary |
| All expected samples appear | One line per sample in the catalog |
| MAX_TAGS is respected | No sample line exceeds configured tag count |
| Null features are handled | Sample with missing BPM still produces a valid line |
| FL Studio can parse the file | Manual test: place file in Browser directory, restart FL, verify tags appear |
| Invalid path is reported | Non-existent FL User Data gives clear error before writing |

---

## 8. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| FL Studio tag file format changes with DAW update | Medium — tags break silently | Low | Document format version, test with latest FL Studio release |
| Hardcoded SAMPLE_ROOTS breaks path resolution | Medium — wrong or missing tags | Medium | EPIC 1 will introduce configurable library profiles |
| Unicode paths in tag file cause FL Studio parsing issues | Medium — some samples untagged | Low | Test with common unicode characters; quote aggressively |
| BWF chunk writes modify original audio files | High — irreversible data change | Low | BWF encoder must default to sidecar files, not in-place modification |
| Ableton has no supported metadata injection path | Medium — limited integration | Medium | Research phase may conclude "not feasible"; document and move on |
| User expects bidirectional sync (DAW → Sample Brain) | Medium — feature creep | Medium | Document explicitly: export is unidirectional (Sample Brain → DAW) |

---

## 9. Non-Goals

- **No bidirectional sync.** Sample Brain does not read DAW project files or detect changes made inside the DAW.
- **No real-time DAW plugin.** VST3, AU, and AAX plugins are not planned.
- **No sample transfer into the DAW.** Export produces metadata and tags, not audio files.
- **No cloud sync.** DAW integration is entirely local.
- **No DAW-specific project file parsing.** Sample Brain does not read `.flp`, `.als`, `.rpp`, or similar project files.
- **No automated DAW detection.** The user must specify the DAW type and export path manually or via config.

---

## 10. Related Documents

| Document | Relevance |
|----------|-----------|
| `docs/PRODUCT_REQUIREMENTS.md` | Target audience (FL Studio producer as primary), product positioning (DAW-near) |
| `docs/SYSTEM_REQUIREMENTS.md` | Functional requirements for export (`src/export_fl.py`), system constraints |
| `docs/TARGET_ARCHITECTURE.md` | Export layer component boundaries, future components |
| `docs/DATA_AND_ARTIFACT_POLICY.md` | Export output is local runtime state, never committed |
| `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md` | Search results as richer export content in future |
| `docs/ISSUE_BACKLOG.md` | EPIC 5 tasks (#23-#25) |
