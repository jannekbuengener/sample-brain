# Library Intelligence & Metadata/Naming Engine — Product Spec

**Issue:** [#94](https://github.com/jannekbuengener/sample-brain/issues/94)  
**Parent:** [#90](https://github.com/jannekbuengener/sample-brain/issues/90)  
**Status:** Spec (docs-only); runtime partially shipped on `main`

This document defines the **Library Intelligence** pillar: sample ingestion, audio analysis, classification, keyword enrichment, title normalisation, and canonical metadata. It is the data foundation for Matching, Context, Transform, and Workspace pillars.

---

## 1. Purpose

Sample Brain must turn chaotic local sample libraries into a **searchable, consistent catalog** without modifying original audio files by default. Library Intelligence is **pure analysis and metadata** — no matching scores, no track context, no variant generation.

---

## 2. Shipped vs target

| Capability | Shipped on `main` | Target (product) | Primary modules |
|------------|-------------------|------------------|-----------------|
| Recursive sample scan | ✅ | ✅ | `src/scan.py`, CLI `scan` |
| Content-hash deduplication | ✅ | ✅ | `src/scan.py`, `samples.hash` |
| Audio feature extraction (BPM, key, loudness, brightness, MFCC, chroma) | ✅ | ✅ | `src/analyze.py`, CLI `analyze` |
| Duration class (loop / oneshot) | ✅ | ✅ | `src/analyze.py` → `features.class` |
| Rule-based autotype (`pred_type`) | ✅ | ✅ | `src/classify.py`, CLI `autotype` |
| Optional kNN autotype | ✅ (seed CSV) | ✅ | `src/classify.py` |
| Configurable library roots (profiles) | ✅ | ✅ | `src/config_loader.py`, `config/profiles.example.yaml` |
| Tag table schema (`sample_tags`) | ✅ schema + partial writers | ✅ full pipeline | `src/db.py`, `src/search_filters.py` |
| Filename regex tags (export path) | ✅ export only | ✅ catalog tags | `src/export_fl.py`, `data/regex_map.json` |
| Keyword enrichment (audio + path + folder) | ❌ | ✅ | *planned* |
| Title normalisation | ❌ | ✅ | *planned* |
| Canonical display title per sample | ❌ | ✅ | *planned* |
| Optional reversible file rename/write | ❌ | opt-in only | *planned* |
| FL Browser tag export | ✅ legacy/fallback | fallback only | `src/export_fl.py` |

---

## 3. Canonical metadata model

### 3.1 Design principles

- **SQLite catalog is the source of truth** for Sample Brain product metadata.
- **Filesystem paths are references**, not the canonical naming layer.
- **Analysis is idempotent**: re-analyze updates features when source hash or pipeline version changes.
- **Confidence fields are explicit** — downstream export and UI must not treat low-confidence values as facts.
- **Original files stay untouched** unless the user explicitly opts into a reversible write path.

### 3.2 Current schema (`main`)

Implemented in `src/db.py`:

#### `samples` — file identity

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `id` | INTEGER PK | system | Stable catalog ID |
| `path` | TEXT UNIQUE | filesystem | Absolute path at scan time |
| `relpath` | TEXT | derived | Relative to configured library root |
| `samplerate` | INT | soundfile probe | May be NULL if unreadable |
| `channels` | INT | soundfile probe | May be NULL |
| `duration` | REAL | soundfile probe | Seconds |
| `size_bytes` | INT | filesystem | |
| `hash` | TEXT | content hash | Deduplication key |

#### `features` — analysis output

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `sample_id` | INTEGER PK/FK | `samples.id` | 1:1 with sample |
| `bpm` | REAL | librosa tempo | Optional BPM normalisation via profile (`analyze.bpm_normalization`); stored as analysis raw float. Producer-facing display uses `src/bpm_display.py` (whole integers, round half up). |
| `key` | TEXT | chroma peak | Root note only today (no maj/min in stored key) |
| `key_conf` | REAL | chroma prominence | Normalised peak/sum ratio; see §5.1 |
| `loudness` | REAL | RMS dBFS | |
| `brightness` | REAL | spectral centroid mean | Used by autotype + export tags |
| `mfcc_mean`, `mfcc_std` | BLOB | librosa MFCC | float32 serialised |
| `chroma_mean`, `chroma_std` | BLOB | librosa chroma | float32 serialised |
| `class` | TEXT | duration rules | `loop` or `oneshot` |
| `pred_type` | TEXT | autotype | e.g. Kick, Snare, Loop, Pad |

**Display vs storage:** `features.bpm` keeps the analysis raw float (optionally octave-normalised at analyze time). Workbench, FL export tags, title pipeline, search/match CLI text, and validation reports use `src/bpm_display.py` for producer-facing integers. Display rounding is **round half up** (`128.5` → `129`), not Python's built-in `round()` (banker's rounding).

#### `sample_tags` — multi-source tags (target: primary keyword store)

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `sample_id` | INTEGER FK | | |
| `tag` | TEXT | varies | Normalised tag string |
| `source` | TEXT | provenance | e.g. `pred_type`, `filename`, `folder`, `audio`, `manual` |

Unique on `(sample_id, tag, source)`. Today populated partially via search-filter sync (`source=pred_type`); full enrichment pipeline is **target**.

#### Embedding tables (semantic search — adjacent, not Library MVP)

`embedding_models`, `sample_embeddings`, `vector_index_state` support EPIC 2 search. Library Intelligence **feeds** embeddings but does not own vector index lifecycle.

### 3.3 Target extensions (not on `main`)

Documented here as **follow-up schema/API work** — no migration in this spec slice.

| Concept | Proposed storage | Purpose |
|---------|------------------|---------|
| `display_title` | `samples` column or `sample_metadata` table | Canonical UI/export title after normalisation |
| `original_filename` | derived from `path` | Audit trail for rename operations |
| `keywords` | `sample_tags` with `source=keyword` | Search/filter enrichment |
| `pipeline_version` | `features` or sidecar | Re-analyze when analyzer changes |
| `analysis_status` | `features` or sidecar | `ok`, `failed`, `skipped` per sample |

---

## 4. Keyword enrichment (target contract)

Keywords supplement `pred_type` and filename regex with structured, searchable tags.

### 4.1 Input sources (priority order)

| Priority | Source | Examples | Shipped |
|----------|--------|----------|---------|
| 1 | Audio features + autotype | `Kick`, `Dark`, `Punchy` | partial (`pred_type` + export heuristics) |
| 2 | Filename tokens | `808`, `riser`, `vocal` | partial (regex map at export) |
| 3 | Folder path segments | `Drums/Kicks`, `Cinematic/Impacts` | ❌ |
| 4 | Profile/genre seeds | Techno/Cinematic seed lists | partial (genre profiles in config) |
| 5 | Manual/user tags | user override | ❌ |

### 4.2 Rules

- Tags are **lowercase normalised** for search; display casing is a UI concern.
- Duplicate tags from different sources may coexist with distinct `source` values.
- Keyword generation must be **deterministic** for the same inputs and profile version.
- No tag implies certainty — low `key_conf` must not produce a key keyword.

### 4.3 Non-goals

- No LLM-generated tags in the default pipeline.
- No cloud keyword APIs.

---

## 5. Title normalisation (target contract)

### 5.1 Goals

- Produce a **canonical display title** per sample for plugin UI, export, and search.
- Reduce noise: `MY_KICK_128BPM_FINAL_v3.wav` → `My Kick` (example — exact rules TBD in implementation).
- Preserve traceability to original path and filename.

### 5.2 Conventions (target)

| Rule | Example |
|------|---------|
| Strip extension | `.wav` removed |
| Replace `_` and `-` with spaces | `dark_pad` → `dark pad` |
| Drop common noise tokens | `final`, `v1`, `wav`, BPM suffixes when redundant with features |
| Title-case with exceptions | `808` stays `808` |
| Do not invent genre/mood not supported by features or path | |

### 5.3 Optional file writes (opt-in only)

- **Default:** metadata-only in SQLite; filesystem unchanged.
- **Opt-in:** explicit CLI flag or profile key to rename or write sidecar metadata.
- Any write path must be **reversible** (log of old → new path) and never run without user GO.

---

## 6. Confidence and export semantics

### 6.1 `key_conf` today

`src/analyze.py` sets `key_conf` as normalised chroma peak prominence (ratio in ~0–1 range, not a calibrated probability).

`src/export_fl.py` uses `CONF_KEY_MIN = 0.55` — key tags are withheld below this threshold.

**Known risk:** historical notes in `knowledge/project/PROJECT_META.md` mention observed values outside 0–1 from legacy Krumhansl analysis; calibration evidence is in [KEY_CONF_EVIDENCE.md](../benchmarks/KEY_CONF_EVIDENCE.md) ([#72](https://github.com/jannekbuengener/sample-brain/issues/72)). Library spec treats confidence fields as **first-class metadata** with documented thresholds per consumer (export, plugin UI, matching).

### 6.2 Target confidence policy

| Consumer | Field | Policy |
|----------|-------|--------|
| FL export (fallback) | `key_conf` | Threshold buckets — evidence in #72 |
| Plugin UI | all features | Show value + confidence or “unknown” |
| Matching pillar | `key`, `bpm` | See [`02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`](02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md) |

---

## 7. Pipeline contract

```text
scan  →  analyze  →  autotype  →  [keyword enrich]  →  [title normalise]
  │          │            │              │                    │
  └──────────┴────────────┴──────────────┴────────────────────┘
                              SQLite catalog (canonical)
```

CLI today: `init` → `scan` → `analyze` → `autotype` → `export_fl` (optional, legacy).

Config precedence: profile YAML < environment variables < CLI flags (`src/config_loader.py`).

---

## 8. Safety boundaries

| Rule | Rationale |
|------|-----------|
| No sample audio in the repository | Legal/size; analyse in place only |
| No committed DBs, indexes, or model caches | `docs/DATA_AND_ARTIFACT_POLICY.md` |
| Prefer `SAMPLE_BRAIN_DB_PATH` outside repo for agent smoke | Keeps `git status` clean |
| No in-place audio modification by default | User owns files |
| No cloud upload for core library operations | Local-first product principle |

---

## 9. Boundaries vs other pillars

| This pillar | Not this pillar |
|-------------|-----------------|
| Extract and store BPM, key, type, timbre features | Score fit to track context → Matching (#91) |
| Classify instrument/loop type | Semitone/BPM fit suggestions → Matching (#91) |
| Build canonical catalog metadata | Derive track profile from host/marked file → Context (#95) |
| Keyword and title normalisation | Render synced variants → Transform (#92) |
| SQLite as catalog SoT | VST UI, preview, drag-drop → Workspace (#93) |

---

## 10. Follow-up runtime slices

| Slice | Scope | Depends on |
|-------|-------|------------|
| Keyword enrichment worker | Populate `sample_tags` from path/folder/audio rules | This spec §4 |
| Title normalisation | `display_title` + CLI `library normalize-titles` (name TBD) | This spec §5 |
| `key_conf` calibration evidence | #72 — thresholds only, no blind code change | §6 |
| Export tests | FL tag structure validation | `docs/DAW_INTEGRATION_SPEC.md` §7 |
| Schema migration | Target columns from §3.3 | Explicit schema GO + `src/db.py` coordination |

---

## 11. Acceptance mapping (Issue #94)

| Acceptance criterion | This spec |
|----------------------|-----------|
| Product scope of Library pillar defined | §1–2 |
| Metadata model derivable for follow-up work | §3 |
| Keywords / title / metadata as core features | §4–5 |
| Safety boundaries for original files | §8 |

**Implementation remains follow-up scope** — this document is the canonical contract; no `src/` changes are required to satisfy the spec slice.

---

## 12. References

- `src/scan.py`, `src/analyze.py`, `src/classify.py`, `src/db.py`, `src/export_fl.py`
- `docs/PRODUCT_REQUIREMENTS.md` §5.1
- `docs/EPIC_1_CONFIG_PROFILES.md`
- `config/profiles.example.yaml`
