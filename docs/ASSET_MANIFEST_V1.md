# Asset Manifest v1 — Canonical Contract

**Issue:** [#250](https://github.com/jannekbuengener/sample-brain/issues/250)
**Parent:** [#230](https://github.com/jannekbuengener/sample-brain/issues/230)
**Depends on:** [#232](https://github.com/jannekbuengener/sample-brain/issues/232) (Track Map v1), [#234](https://github.com/jannekbuengener/sample-brain/issues/234) (Canonical Audio & Timebase)
**Status on issue tracker:** `OPEN` / documented on branch `docs/asset-manifest-v1`
**Schema version:** `1.0.0`
**Document type:** `sample_brain.asset_manifest`

This document defines the portable asset manifest contract for Loop and Section
candidates and for rendered assets produced by the Sample-Brain deconstruction
pipeline (#230). It describes how loop/section assets are identified, bounded,
scored, rendered, and traced back to their original track — without embedding
private paths, audio, databases, or SQLite internals.

The Asset Manifest is a **separate document** from the Track Map (#232), the
Arrangement Map (#228 / #238–#243), the Stem Manifest (#229 / #244–#249), and
the Performance Pack (#231 / #257–#264). It references those documents by
portable ID, never by absolute filesystem path.

---

## 1. Purpose

The Asset Manifest is the portable description of a single loop or section
asset cut from a track (or from one of its stems / producer groups). It is the
unit that later issues consume and aggregate:

- Loop candidate generation (#251)
- Loop scoring (#252)
- Section candidate generation (#266)
- Section scoring (#267)
- Producer-group assets (#268)
- Stem-based candidate generation (#255)
- Deterministic audio rendering (#253)
- Asset reanalysis (#254)
- Performance Pack assembly (#231 / #257)

A single Asset Manifest describes **one** asset (one loop, or one section).
A pack is a collection of such manifests plus the files they reference.

---

## 2. Design Principles

| Principle | Rule |
|-----------|------|
| **Portable identity** | Content hash + portable IDs identify track, source, and asset. No absolute local paths, no `file://`, no drive letters, no UNC paths, no `..` segments. |
| **Asset kind is explicit** | `asset_kind` (`loop` \| `section`) is a required field. Loop and section are never distinguished implicitly by file name or by position. |
| **Source kind is explicit** | `source.source_kind` (`master` \| `stem` \| `producer_group`) is required. Technical stems and producer groups are never equated. |
| **Authoritative sample range** | Boundaries are integer sample indices on the #234 timebase. Seconds are derived only, never authoritative. |
| **Boundary vs role separation** | Neutral boundary certainty and arrangement-role certainty are separate fields, following the Arrangement Confidence contract (#241). |
| **No invented confidence** | No generic `confidence` field. Scores, when present, are explicit and per-level. Missing score never implies low quality. |
| **Candidate vs rendering separation** | Selection/score metadata is kept apart from render/output metadata. |
| **Status transparency** | Every sub-result carries a status (`ok` / `partial` / `not_run` / `failed` / `no_result`). Missing optional results are not fabricated. |
| **Provenance per component** | Every analysis/renderer step records its component, version, backend, model, and config in a centralized `provenance.components` registry. |
| **Additive evolution** | New optional fields can be added in `1.x.x` without reinterpreting existing fields. |

---

## 3. Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `document_type` | string | yes | Must be `"sample_brain.asset_manifest"`. |
| `schema_version` | string | yes | SemVer `MAJOR.MINOR.PATCH`. This revision is `"1.0.0"`; compatible v1 documents may use `1.x.x`. |
| `asset_id` | string | yes | Portable, unique identity of this asset within the pipeline run. |
| `track_ref` | string | yes | Portable reference to the originating Track Map (#232). Identifies the original track. Not a filesystem path. |
| `asset_kind` | string | yes | `"loop"` or `"section"`. |
| `source` | object | yes | Source identity (Section 5). |
| `timebase` | object | yes | Sample-accurate timebase (Section 6). |
| `range` | object | yes | Authoritative sample interval of the asset (Section 6). |
| `loop` / `section` | object | conditional | Kind-specific fields (Section 7 / Section 8). Exactly one is present, matching `asset_kind`. |
| `boundary` | object | yes | Boundary provenance and quality (Section 9). |
| `candidate` | object | no | Candidate/selection metadata, separate from rendering (Section 10). |
| `rendering` | object | yes | Render status and output provenance; may report `not_rendered` (Section 11). |
| `analysis` | object | yes | Analysis/reanalysis provenance; may report `not_run` (Section 12). |
| `provenance` | object | yes | Centralized component registry (Section 13). |
| `quality` | object | yes | Quality notes (Section 14). |

### Versioning

- **MAJOR** increments when a previously required field is removed or renamed in a breaking way, or when the status enum changes.
- **MINOR** increments when new optional fields or additive structures are introduced, provided existing v1 fields and enums retain their meaning.
- **PATCH** increments for non-breaking documentation or example corrections.
- The current frozen revision is `1.0.0`; this document does not raise that version.
- Readers must reject any Asset Manifest whose `schema_version` major number is unsupported. v1 consumers accept compatible `1.x.x` documents.
- The status enum values (`ok`, `partial`, `not_run`, `failed`, `no_result`) are fixed for v1. New status values require a `MAJOR` increment.

---

## 4. Asset Identity

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `asset_id` | string | yes | Portable, unique ID of this asset. Synthetic/opaque; no semantic meaning required. |
| `track_ref` | string | yes | Portable reference to the originating Track Map. Stable identity only — typically the Track Map `source.original.hash.value` or an agreed portable track ID. Never an absolute path. |
| `asset_kind` | string | yes | `"loop"` or `"section"`. Determines which kind-specific block (`loop` or `section`) is present. |

**Rules**

- `asset_kind` is authoritative. A consumer must never infer loop vs section from `asset_id`, file name, or byte position.
- `track_ref` provides whole-track traceability. Source-level traceability (master/stem/producer_group) is in `source` (Section 5).

---

## 5. Source Identity

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source.source_kind` | string | yes | `"master"`, `"stem"`, or `"producer_group"`. |
| `source.audio` | object | yes | The concrete audio the asset is cut from. Same shape as Track Map `source.original` (`file_name`, optional `relative_uri`, optional `size_bytes`, `hash`, `audio_properties`, `source_ref`). |
| `source.track_audio_ref` | string | conditional | JSON pointer to the track-level audio in the referenced Track Map. Required when `source_kind = "master"`. Must be `"/source/original"` or `"/source/working_audio"`. |
| `source.stem_id` | string | conditional | Technical stem ID. Required when `source_kind = "stem"`. |
| `source.stem_ref` | string | conditional | Portable reference to the Stem Manifest entry for this stem. Required when `source_kind = "stem"`. |
| `source.producer_group_id` | string | conditional | Producer-group ID. Required when `source_kind = "producer_group"`. |
| `source.producer_group_ref` | string | conditional | Portable reference to the producer-group definition. Required when `source_kind = "producer_group"`. |

**Rules**

- `source_kind = "master"` → the asset is cut from the original track's canonical working audio. `track_audio_ref` links to the Track Map audio block. No `stem_id` / `producer_group_id`.
- `source_kind = "stem"` → the asset is cut from a **technical** stem. `stem_id` and `stem_ref` identify it. A technical stem is never a producer group.
- `source_kind = "producer_group"` → the asset is a producer-oriented group of material. `producer_group_id` and `producer_group_ref` identify it. A producer group is never a technical stem.
- Technical stems and producer groups are distinct source kinds and must never be equated or substituted.
- `source.audio` always describes the **actual audio the sample indices are measured against** (the stem audio for a stem source, the producer-group audio for a producer-group source, the track working audio for a master source).
- Absolute paths are never serialized in the source block. `hash` is the authoritative identity key; `file_name` and `audio_properties` are descriptive.

---

## 6. Timebase and Authoritative Range

All timeline positions in the Asset Manifest are **integer sample indices** on
the #234 canonical timebase. Seconds are derived only and never authoritative.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `timebase.audio_ref` | string | yes | JSON pointer to the audio the samples are measured against. Must be `"/source/audio"` (this document). |
| `timebase.unit` | string | yes | Must be `"samples"`. |
| `timebase.origin_sample` | integer | yes | Must be `0`. The origin is the absolute start of the referenced audio. |
| `timebase.sample_rate_hz` | integer | yes | Sample rate of the referenced audio (must equal `source.audio.audio_properties.sample_rate_hz`). |

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `range.start_sample` | integer | yes | Inclusive first sample of the asset. `>= 0`. |
| `range.end_sample_exclusive` | integer | yes | Exclusive end sample (sample immediately after the asset). Half-open interval `[start_sample, end_sample_exclusive)`. |
| `range.n_samples` | integer | yes | `end_sample_exclusive - start_sample`. Must be `> 0`. |
| `range.start_sec` | number | no | Derived seconds for convenience. Not authoritative. |
| `range.end_sec_exclusive` | number | no | Derived seconds for convenience. Not authoritative. |

**Rules**

- The interval is half-open: `[start_sample, end_sample_exclusive)`. This reuses the #234 `AudioRange` semantics.
- `end_sample_exclusive > start_sample` (so `n_samples > 0`). Invalid ranges are rejected by consumers (fail-closed).
- Sample indices are measured against `timebase.audio_ref` (the audio in `source.audio`), which itself is hash-linked to the original track per #234.
- Seconds, when present, are derived via `samples / sample_rate_hz` and must not be used as the authoritative boundary.
- Bar/downbeat positions (loops) and section/role references are derived references layered on top of this sample range; they never replace it.

---

## 7. Loop Fields (`asset_kind = "loop"`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `loop.bars.start_bar` | integer | yes | Inclusive zero-based bar index of the loop start, on the referenced track's bar grid. |
| `loop.bars.end_bar_exclusive` | integer | yes | Exclusive bar index of the loop end. `end_bar_exclusive > start_bar`. |
| `loop.downbeat_start_sample` | integer | no | Sample index of the downbeat that begins the loop. Convenience; must equal `range.start_sample` when the loop is downbeat-aligned. |
| `loop.bar_count` | integer | yes | `end_bar_exclusive - start_bar`. Must be `> 0`. |
| `loop.bar_grid_ref` | string | no | Reference to the bar/downbeat grid the bar indices are derived from (e.g. the Track Map `analysis.timeline.downbeats`). |

**Rules**

- Bar indices are derived from the track's beat/downbeat grid (Track Map #232 / BeatGrid #236). They are a **convenience reference**, not the authoritative boundary. The authoritative boundary is always `range` in samples.
- Future 4/8/16-bar candidate shapes from #251 are expressible as `[start_bar, start_bar + N)` bar ranges over the same grid — no BPM×seconds approximation is needed, because both the sample range and the bar indices are anchored on the shared canonical grid.
- A loop is **not** required to be downbeat-aligned; when it is, `downbeat_start_sample` equals `range.start_sample`.

---

## 8. Section Fields (`asset_kind = "section"`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `section.section_ref` | string | no | Portable reference to the neutral section in the Track Map (`analysis.timeline.sections.items[].id`) this asset corresponds to. |
| `section.arrangement_role` | string | no | Arrangement role from the role vocabulary (#238): `intro`, `groove`, `build`, `drop`, `breakdown`, `outro`, `unknown`. |
| `section.arrangement_role_status` | string | conditional | Status of the role assignment: `available`, `uncertain`, `unknown`, `unavailable`, `failed` (per the Arrangement Confidence contract #241). Required when `arrangement_role` is present. |
| `section.arrangement_role_ref` | string | no | Portable reference to the Arrangement Map entry that assigned the role. |
| `section.bars` | object | no | Optional bar span `{start_bar, end_bar_exclusive, bar_count}` on the referenced track's bar grid. Bars are optional for sections (unlike loops). |

**Rules**

- A section asset may or may not map to a Track Map section id; `section_ref` is optional but recommended when the section originated from neutral boundaries.
- Arrangement role and role status are **separate** from boundary certainty (Section 9). A strong neutral boundary can carry `unknown` role; a strong role hint does not create a boundary.
- `arrangement_role = "unknown"` is a valid, normal result — never a placeholder requiring a dummy confidence value.
- Bars are optional for sections. When present, they follow the same derived-reference rule as loops (Section 7).

---

## 9. Boundary Evidence

Boundary provenance and quality are recorded separately from any arrangement
role. This enforces the strict boundary/role separation from the Arrangement
Confidence contract (#241).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `boundary.status` | string | yes | `ok`, `partial`, `no_result`, or `failed` (neutral boundary layer). |
| `boundary.source` | string | yes | Where the boundary originated. One of: `structure_v1`, `beat_grid`, `arrangement_map`, `stem_split`, `producer_group`, `manual`. |
| `boundary.source_ref` | string | conditional | Key into `provenance.components`. Required when the boundary was produced by a component. |
| `boundary.kind` | string | no | Boundary kind, e.g. `neutral_section`, `bar_grid`, `stem_split`, `producer_group_split`. |
| `boundary.quality` | number | no | Relative boundary strength in `[0, 1]`. Mirrors the `boundary_quality` metric of the Arrangement Confidence contract. Optional; never a generic confidence. |
| `boundary.reason_code` | string | conditional | Stable code for `no_result` / `failed` boundaries. |

**Rules**

- `boundary.quality` is a **relative strength** signal (0–1), not a calibrated probability and not a role confidence. It may be omitted; omission never implies low quality.
- No single universal `confidence` field bridges the boundary layer and the role layer.
- The start and end boundaries each inherit this evidence; a single `boundary` object describes the asset's boundary provenance as a pair. When start/end differ in provenance, implementations may extend this to per-edge detail in a future `1.x` addendum without breaking v1.

---

## 10. Candidate Selection (separate from rendering)

The `candidate` block records **selection/score metadata** for the asset as a
candidate. It is strictly separate from `rendering` (Section 11). It does not
assert that the asset was rendered.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `candidate.status` | string | yes | Candidate status: `candidate`, `selected`, `rejected`, or `not_evaluated`. |
| `candidate.score_components` | object | no | Per-component scores, each with explicit semantics (name, value, range, meaning). Loop and section scores use **separate** component sets; they are never merged into one value. |
| `candidate.excluded` | boolean | no | Whether the asset was hard-excluded from selection. |
| `candidate.reject_reasons` | array of strings | conditional | Stable reason codes for hard exclusion (e.g. `TOO_SHORT`, `SILENT`, `OVERLAP`). Required when `excluded` is `true`. |

**Rules**

- Loop scoring (#252) and section scoring (#267) have **independent** score logic. This contract defines the *container*; it does **not** prescribe shared score fields or a unified score.
- No concrete global scoring thresholds are defined here. Threshold definition belongs to #252 / #267.
- `score_components` entries must each carry defined semantics if present; absent scores are omitted (no placeholder values).
- `excluded` / `reject_reasons` capture hard rejection separately from soft scoring, so downstream consumers can distinguish "low score" from "invalid".

---

## 11. Rendering

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `rendering.status` | string | yes | `rendered`, `not_rendered`, `partial`, or `failed`. |
| `rendering.renderer` | object | conditional | Renderer provenance. Required when `status` is `rendered` or `partial`. |
| `rendering.output` | object | conditional | Output file reference. Required when `status` is `rendered` or `partial`. |
| `rendering.error` | object | conditional | Present when `status` is `failed`. |

`rendering.renderer`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `component` | string | yes | Renderer component name (e.g. `asset_renderer`). |
| `sample_brain_version` | string | yes | Version that produced the output. |
| `configuration` | object | yes | Relevant render config (no secrets). |
| `source_ref` | string | yes | Key into `provenance.components`. |

`rendering.output`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_ref` | string | yes | **Portable** reference to the rendered file (relative URI / portable asset name). Never an absolute private path. |
| `file_name` | string | no | Base file name. Auxiliary only — not the sole source of truth. |
| `hash.algorithm` | string | yes | Hash algorithm (e.g. `sha1`). |
| `hash.value` | string | yes | Hex digest of the rendered file. |
| `audio_properties.sample_rate_hz` | integer | yes | Sample rate of the rendered file. |
| `audio_properties.channels` | integer | yes | Channel count. |
| `audio_properties.n_samples` | integer | yes | Sample count of the rendered file. |
| `format` | string | yes | Container/subtype (e.g. `wav/pcm_16`). |

**Rules**

- `rendering.status = "not_rendered"` is a valid, normal state for a candidate-only manifest. The asset still fully describes its identity, range, and provenance.
- `file_name` is auxiliary. The portable `file_ref` is the authoritative handle; consumers must not rely on the file name alone.
- No absolute private paths, drive letters, or `..` segments in `file_ref`.
- `hash` provides portable content identity for the rendered artifact.

---

## 12. Analysis / Reanalysis

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `analysis.status` | string | yes | `ok`, `partial`, `not_run`, `failed`, or `no_result`. |
| `analysis.components` | array of strings | no | Component IDs analyzed for this asset. |
| `analysis.source_ref` | string | conditional | Key into `provenance.components`. Required when analysis produced data. |
| `analysis.reason_code` | string | conditional | Stable code for `not_run` / `no_result`. |
| `analysis.bpm` | number | no | Tempo in BPM. `None`/absent for short clips or when not determined. No invented BPM-confidence. |
| `analysis.key_root` | string | no | Estimated tonal **root** pitch class (`C`…`B`). Root only — no invented mode. |
| `analysis.sample_type` | string | no | Lightweight rules-only type (e.g. `Loop`, `Drum Loop`, `Drone`, `Bright`). No kNN/CLAP. |
| `analysis.loudness` | number | no | RMS-based loudness in dBFS. |
| `analysis.brightness` | number | no | Spectral centroid in Hz. |
| `analysis.analyzed_output` | object | conditional | Reference to the actually analyzed render output: `{file_ref, hash, audio_properties}`. Required when analysis produced data. |
| `analysis.config` | object | no | Analyzer config used (no secrets): `bpm_normalization`, `short_clip`, `duration_sec`. |
| `analysis.error` | object | conditional | Present when `status` is `failed`: `{code, message}`. |

**Rules**

- `analysis.status = "not_run"` is the expected state before asset reanalysis (#254) is implemented. No analysis values are fabricated.
- This block records provenance for (re)analyzed assets. The reanalysis behavior, integrity gate, status model, and fail-closed codes are defined in `ASSET_REANALYSIS_V1.md` (#254) as an **additive `1.x` extension** of this frozen `1.0.0` contract.
- The reanalysis fields above are optional and only present when a meaningful value was produced. Absent fields never imply a low-quality result.
- No generic confidence is invented for analyzed assets. No Dur/Moll mode is inferred. No BPM-confidence is invented.
- `asset_kind` and `source.source_kind` are never reinterpreted by analysis. `source`, `range`, `loop`/`section`, `boundary`, `candidate`, and `rendering` blocks are preserved unchanged by reanalysis.

---

## 13. Provenance

Reuses the centralized `provenance.components` registry convention from the
Track Map (#232).

`provenance.components` is a JSON object (map). Each key is a component
identifier; each value is component metadata. **Both `provenance` and
`provenance.components` are required.**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `component` | string | yes | Sample-Brain component name (e.g. `structure_v1`, `beat_grid`, `asset_renderer`, `asset_analyzer`). |
| `sample_brain_version` | string | yes | Version of sample-brain that produced the result. |
| `backend.name` | string | conditional | Backend used (e.g. `librosa`, `beat_this`). Absent if no backend applies. |
| `backend.version` | string | conditional | Backend/library version, if applicable. |
| `model.name` | string | conditional | Model identifier, if a model was used. Absent for algorithmic components. |
| `model.version` / `model.revision` | string | conditional | Model version/revision, if a model was used. |
| `configuration` | object | yes | Relevant configuration that affected the result. Must not contain secrets. Use `{}` if none. |

**Rules**

- Provenance records document **what was actually used**, not what was available.
- **Never** include: secrets, private absolute paths, model-cache paths, or private sample-directory paths.
- Analysis, boundary, and renderer blocks reference their component via `source_ref` into `provenance.components`.

---

## 14. Quality Notes

Reuses the Track Map `quality.notes` convention.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `quality.notes` | array | yes | Array of quality note objects (may be empty). |
| `quality.notes[].code` | string | yes | Stable code (e.g. `SHORT_ASSET`, `WEAK_BOUNDARY`, `MISSING_ROLE`). |
| `quality.notes[].severity` | string | yes | `info`, `warning`, or `error`. |
| `quality.notes[].path` | string | yes | JSON Pointer to the affected field. Must not contain private paths. |
| `quality.notes[].message` | string | yes | Human-readable message. |

---

## 15. Status Model

### 15.1 Individual status

Each sub-component (`boundary`, `analysis`) carries one of:

| Status | Meaning | Required extra fields |
|--------|---------|-----------------------|
| `ok` | Ran successfully, complete result. | `source_ref` when data present. |
| `partial` | Ran but produced only partial result. | `source_ref` when data present. |
| `not_run` | Not requested, or unavailable before execution. No data invented. | `reason_code`. No `source_ref`. |
| `failed` | Requested and attempted, but errored. | `error.code`, `error.message`, `source_ref`. Optional `error.retryable`. |
| `no_result` | Ran successfully but produced no meaningful result. | `reason_code`, `source_ref`. |

`rendering.status` uses `rendered` / `not_rendered` / `partial` / `failed`.
`candidate.status` uses `candidate` / `selected` / `rejected` / `not_evaluated`.
`section.arrangement_role_status` uses `available` / `uncertain` / `unknown` / `unavailable` / `failed`.

### 15.2 Rules

- Missing optional results are represented by their non-`ok` status; values are never fabricated.
- `error` (object) is present when `status` is `failed`: `error.code`, `error.message`, optional `error.retryable`.
- `reason_code` (string) explains `not_run` / `no_result` (e.g. `BOUNDARY_NOT_REQUESTED`, `ANALYSIS_NOT_REQUESTED`, `NO_MEANINGFUL_BOUNDARY`).

---

## 16. Downstream Traceability

- **Whole-track traceability:** `track_ref` links every asset to its originating Track Map (#232) without SQLite internals.
- **Source traceability:** `source.source_kind` + `source.stem_ref` / `source.producer_group_ref` distinguish master / stem / producer_group origins.
- **Parent/child:** a rendered asset may reference its candidate via an optional `parent_asset_ref` (portable `asset_id`). This is additive and optional in v1.
- **Performance Pack aggregation (#231 / #257):** a Performance Pack manifest aggregates Asset Manifests by `track_ref` and `asset_id`; the Asset Manifest is self-contained and requires neither SQLite nor private paths to be consumed.
- **Reuse for #251 / #252 / #253 / #254:** the `loop` block, `candidate` block, `rendering` block, and `analysis` block are the exact extension points those issues fill in.

---

## 17. Examples

All IDs, hashes, and paths below are **synthetic**. No private track names,
sample names, or absolute paths are used.

### 17.1 Loop from master (downbeat-aligned, 8 bars)

```json
{
  "document_type": "sample_brain.asset_manifest",
  "schema_version": "1.0.0",
  "asset_id": "asset_loop_8bar_master_01a2b3c4",
  "track_ref": "track_9f8e7d6c5b4a",
  "asset_kind": "loop",
  "source": {
    "source_kind": "master",
    "track_audio_ref": "/source/working_audio",
    "audio": {
      "file_name": "demo_track_working.wav",
      "hash": { "algorithm": "sha1", "value": "da39a3ee5e6b4b0d3255bfef95601890afd80709" },
      "audio_properties": { "duration_sec": 240.0, "sample_rate_hz": 44100, "channels": 1 }
    }
  },
  "timebase": {
    "audio_ref": "/source/audio",
    "unit": "samples",
    "origin_sample": 0,
    "sample_rate_hz": 44100
  },
  "range": {
    "start_sample": 441000,
    "end_sample_exclusive": 882000,
    "n_samples": 441000,
    "start_sec": 10.0,
    "end_sec_exclusive": 20.0
  },
  "loop": {
    "bars": { "start_bar": 8, "end_bar_exclusive": 16 },
    "bar_count": 8,
    "downbeat_start_sample": 441000,
    "bar_grid_ref": "/analysis/timeline/downbeats"
  },
  "boundary": {
    "status": "ok",
    "source": "beat_grid",
    "source_ref": "comp_beat_grid",
    "kind": "bar_grid",
    "quality": 0.92
  },
  "candidate": {
    "status": "selected",
    "score_components": {
      "energy_stability": { "value": 0.81, "range": [0, 1], "meaning": "per-bar RMS stability" }
    },
    "excluded": false
  },
  "rendering": {
    "status": "rendered",
    "renderer": {
      "component": "asset_renderer",
      "sample_brain_version": "0.1.0",
      "configuration": { "format": "wav/pcm_16", "normalize": false },
      "source_ref": "comp_renderer"
    },
    "output": {
      "file_ref": "assets/loop_8bar_master_01a2b3c4.wav",
      "file_name": "loop_8bar_master_01a2b3c4.wav",
      "hash": { "algorithm": "sha1", "value": "b5e3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1" },
      "audio_properties": { "sample_rate_hz": 44100, "channels": 1, "n_samples": 441000 },
      "format": "wav/pcm_16"
    }
  },
  "analysis": { "status": "not_run", "reason_code": "ANALYSIS_NOT_REQUESTED" },
  "provenance": {
    "components": {
      "comp_beat_grid": {
        "component": "beat_grid",
        "sample_brain_version": "0.1.0",
        "backend": { "name": "librosa", "version": "0.10.0" },
        "configuration": {}
      },
      "comp_renderer": {
        "component": "asset_renderer",
        "sample_brain_version": "0.1.0",
        "configuration": { "format": "wav/pcm_16" }
      }
    }
  },
  "quality": { "notes": [] }
}
```

### 17.2 Section from a technical stem

```json
{
  "document_type": "sample_brain.asset_manifest",
  "schema_version": "1.0.0",
  "asset_id": "asset_section_stem_drop_05f6e7d8",
  "track_ref": "track_9f8e7d6c5b4a",
  "asset_kind": "section",
  "source": {
    "source_kind": "stem",
    "stem_id": "stem_drums_01",
    "stem_ref": "stemmanifest_drums_01",
    "audio": {
      "file_name": "demo_track_drums.wav",
      "hash": { "algorithm": "sha1", "value": "c0ffee1234567890abcdef1234567890abcdef12" },
      "audio_properties": { "duration_sec": 240.0, "sample_rate_hz": 44100, "channels": 1 }
    }
  },
  "timebase": {
    "audio_ref": "/source/audio",
    "unit": "samples",
    "origin_sample": 0,
    "sample_rate_hz": 44100
  },
  "range": {
    "start_sample": 1323000,
    "end_sample_exclusive": 1764000,
    "n_samples": 441000
  },
  "section": {
    "section_ref": "section_03",
    "arrangement_role": "drop",
    "arrangement_role_status": "available",
    "arrangement_role_ref": "arrangement_section_03",
    "bars": { "start_bar": 24, "end_bar_exclusive": 32, "bar_count": 8 }
  },
  "boundary": {
    "status": "ok",
    "source": "arrangement_map",
    "source_ref": "comp_arrangement",
    "kind": "neutral_section",
    "quality": 0.78
  },
  "candidate": { "status": "candidate" },
  "rendering": { "status": "not_rendered" },
  "analysis": { "status": "not_run", "reason_code": "ANALYSIS_NOT_REQUESTED" },
  "provenance": {
    "components": {
      "comp_arrangement": {
        "component": "arrangement_map",
        "sample_brain_version": "0.1.0",
        "configuration": {}
      }
    }
  },
  "quality": {
    "notes": [
      { "code": "WEAK_BOUNDARY", "severity": "warning", "path": "/boundary", "message": "End boundary partially uncertain" }
    ]
  }
}
```

### 17.3 Loop from a producer group

```json
{
  "document_type": "sample_brain.asset_manifest",
  "schema_version": "1.0.0",
  "asset_id": "asset_loop_pg_bridge_09a8b7c6",
  "track_ref": "track_9f8e7d6c5b4a",
  "asset_kind": "loop",
  "source": {
    "source_kind": "producer_group",
    "producer_group_id": "pg_bridge_fx",
    "producer_group_ref": "producergroup_bridge_fx",
    "audio": {
      "file_name": "pg_bridge_fx.wav",
      "hash": { "algorithm": "sha1", "value": "feedface1234567890abcdef1234567890abcdef" },
      "audio_properties": { "duration_sec": 32.0, "sample_rate_hz": 44100, "channels": 1 }
    }
  },
  "timebase": {
    "audio_ref": "/source/audio",
    "unit": "samples",
    "origin_sample": 0,
    "sample_rate_hz": 44100
  },
  "range": {
    "start_sample": 0,
    "end_sample_exclusive": 88200,
    "n_samples": 88200
  },
  "loop": {
    "bars": { "start_bar": 0, "end_bar_exclusive": 2, "bar_count": 2 },
    "downbeat_start_sample": 0
  },
  "boundary": {
    "status": "partial",
    "source": "producer_group",
    "source_ref": "comp_pg",
    "kind": "producer_group_split",
    "quality": 0.6
  },
  "candidate": { "status": "rejected", "excluded": true, "reject_reasons": ["TOO_SHORT"] },
  "rendering": { "status": "not_rendered" },
  "analysis": { "status": "not_run", "reason_code": "ANALYSIS_NOT_REQUESTED" },
  "provenance": {
    "components": {
      "comp_pg": { "component": "producer_group", "sample_brain_version": "0.1.0", "configuration": {} }
    }
  },
  "quality": { "notes": [] }
}
```

---

## 18. Acceptance Mapping (Issue #250)

| #250 criterion | This document |
|----------------|---------------|
| Vertrag dokumentiert | Entire document. |
| Loop und Section sind eindeutig getrennt | `asset_kind` (`loop` \| `section`); separate `loop` / `section` blocks (Sections 4, 7, 8). Never by file name. |
| Master-, Stem- und Producer-Group-Quellen sind abbildbar | `source.source_kind` (`master` \| `stem` \| `producer_group`) with distinct IDs/refs (Section 5). Examples §17.1–17.3. |
| ganzzahlige Sample-Grenzen und Boundary-Provenance sind Pflicht | `range.start_sample` / `end_sample_exclusive` on the #234 timebase (Section 6); mandatory `boundary` block (Section 9). |
| für #231 wiederverwendbar | Section 16 (Performance Pack aggregation by `track_ref` / `asset_id`); no SQLite/private paths required. |
| keine privaten absoluten Pfade oder internen DB-Details erforderlich | Portable IDs/hashes/`file_ref` throughout; `provenance` never stores paths/secrets (Sections 5, 11, 13). |

---

## 19. Related Documents

- [Track Map v1](TRACK_MAP_V1.md) (#232) — track identity, timebase, sections, provenance registry.
- [Canonical Audio & Timebase](CANON_AUDIO_TIMEBASE.md) (#234) — authoritative sample timebase, half-open `AudioRange`.
- [StructureV1 Boundary Backend](STRUCTURE_V1.md) (#265) — neutral boundaries.
- [Arrangement Role Vocabulary v1](ARRANGEMENT_ROLE_VOCABULARY_V1.md) (#238) — section role vocabulary.
- [Arrangement Confidence & Override v1](ARRANGEMENT_CONFIDENCE_OVERRIDE_V1.md) (#241) — boundary/role separation, no universal confidence.
- [Stem Manifest](#) (#229 / #244–#249) — technical stem identity (referenced via `stem_ref`).
- [Performance Pack manifest v1](#) (#231 / #257) — downstream aggregation.

---

## 20. Non-Goals (v1)

- No audio rendering implementation (#253), candidate generation (#251 / #266), or scoring logic (#252 / #267).
- No reanalysis implementation (#254).
- No producer-group generation implementation (#268) or stem-generation implementation (#255).
- No SQLite internals, DB schemas, or indexes exposed.
- No private absolute filesystem paths, private samples, or secrets.
- No unified loop/section score, and no invented generic `confidence` field.
- File name is auxiliary, never the sole source of truth.
