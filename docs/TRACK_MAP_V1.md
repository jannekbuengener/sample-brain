# Track Map v1 — Canonical Contract

**Issue:** [#232](https://github.com/jannekbuengener/sample-brain/issues/232)
**Parent:** [#227](https://github.com/jannekbuengener/sample-brain/issues/227)
**Status on issue tracker:** `OPEN` / `READY_TO_DOCUMENT` (not closed until PR is merged to `main`)
**Schema version:** `1.0.0`
**Document type:** `sample_brain.track_map`

This document is the canonical, machine-readable Track Map v1 contract for sample-brain. The Track Map is the portable, neutral technical description of a single complete track. It is the shared input for later contracts:

- Arrangement Map (#228 / #238–#243)
- Stem Manifest (#229 / #244–#249)
- Asset Manifest (#230 / #250–#256, #266, #267)
- Performance Pack (#231 / #257–#264)

These remain **separate** documents. The Track Map never embeds arrangement roles, technical stems, producer assets, or pack-specific fields.

---

## 1. Purpose

The Track Map is the stable identity of a single audio track plus the lightweight musical analysis that sample-brain can produce from it. It is the shared anchor for:

- bar-synchronous boundary analysis (StructureV1, #265)
- BeatGrid (BPM, beats, downbeats, #236)
- arrangement role signals (#238–#240)
- technical stem separation (#229 / #244–#249)
- producer-oriented assets (#230 / #250–#256)
- Performance Pack assembly (#231 / #257–#264)

A Track Map is **track-level only**: one audio file → one Track Map. It is not a sample-level catalog entry (that is `features` / `samples` in the SQLite catalog per the Library Intelligence spec §3).

---

## 2. Design Principles

| Principle | Rule |
|-----------|------|
| **Portable identity** | Content hash + file name + audio params identify the track; no absolute local paths, no `file://`, no drive letters, no UNC paths, no `..` segments. |
| **No invented values** | If a component did not run or produced no result, status reflects that; values are not fabricated. |
| **Status transparency** | Every sub-result has a status (`ok` / `partial` / `not_run` / `failed` / `no_result`); `not_run` does not degrade the overall analysis status. |
| **Provenance per component** | Every analysis step records its Sample-Brain component, version, backend, model, and relevant config in a centralized `provenance.components` registry; analysis values reference components via `source_ref`. |
| **Timebase stability** | All timeline positions share a common audio timebase in seconds, bound to the audio file referenced via `audio_ref`. Sample-accurate render boundaries are handled in later Asset/Rendering contracts. |
| **Additive evolution** | Future beat/bar-synced energy forms can be added without reinterpreting existing fields. v1 stores only actually used parameter values. |
| **Separation of concerns** | Arrangement roles, stems, producer assets, and pack fields live in their own documents. |

---

## 3. Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `document_type` | string | yes | Must be `"sample_brain.track_map"`. Identifies the document kind. |
| `schema_version` | string | yes | Must be `"1.0.0"`. String matching MAJOR.MINOR.PATCH. This document defines 1.0.0. |
| `source` | object | yes | Source identity (Section 4). |
| `timebase` | object | yes | Timebase reference (Section 5). |
| `analysis` | object | yes | Analysis status + musical/audio/timeline blocks (Section 6). |
| `provenance` | object | yes | Centralized component registry (Section 8). |
| `quality` | object | yes | Quality notes (Section 9). |

### Versioning

- **MAJOR** increments when a previously required field is removed or renamed in a breaking way.
- **MINOR** increments when new optional fields or additive status values are introduced.
- **PATCH** increments for non-breaking documentation or example corrections.
- Readers must reject any Track Map whose `schema_version` major number is unsupported. v1 consumers accept `1.x.x`.
- The status enum values (`ok`, `partial`, `not_run`, `failed`, `no_result`) are fixed for v1. New status values require a `MAJOR` increment.
- `analysis.status` accepts only `ok`, `partial`, `failed` in v1.

---

## 4. Source Identity

The Track Map must be portable: it must not embed absolute local paths, usernames, or machine-specific identifiers.

### `source.original` (required)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_name` | string | yes | Base name of the audio file (e.g. `my_track.wav`). Portable name only. |
| `relative_uri` | string | no | Relative URI to the audio file, relative to the Track Map file on disk. May be omitted when emitted to stdout. Not part of stable identity. |
| `size_bytes` | integer | no | File size in bytes, if available. |
| `hash.algorithm` | string | yes | Hash algorithm name (e.g. `sha1`). The current sample-brain runtime uses **SHA-1**. |
| `hash.value` | string | yes | Hex digest of the file content. |
| `audio_properties.duration_sec` | number | yes | Duration of the audio in seconds (float). |
| `audio_properties.sample_rate_hz` | integer | yes | Sample rate in Hz. |
| `audio_properties.channels` | integer | yes | Number of audio channels. |
| `source_ref` | string | yes | Key into `provenance.components` for the component that computed the hash and audio properties. |

### `source.working_audio` (optional — only when a working WAV exists)

Present only when a re-rendered/re-mixed working WAV has been produced and is portable-referenced (#234, #237). Has the same shape as `source.original` (`file_name`, optional `relative_uri`, optional `size_bytes`, `hash`, `audio_properties`, `source_ref`).

### Rules

- Absolute paths are never serialized in the identity block.
- `hash` is the **authoritative** identity key; file name and audio params are descriptive.
- `relative_uri`, if present, is for local resolution only and is not validated as stable identity.
- SHA-1 is the hash algorithm used by the current sample-brain runtime. The contract allows later algorithm identifiers; readers must check `hash.algorithm`.

---

## 5. Timebase

All timeline positions in the Track Map share a common audio timebase in seconds, bound to the audio file referenced via `audio_ref`. Sample-accurate render boundaries are handled in later Asset/Rendering contracts.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio_ref` | string | yes | JSON pointer to the audio source. Must be `"/source/original"` (default, no working audio) or `"/source/working_audio"` (when working audio exists and `source.working_audio` is present). |
| `unit` | string | yes | Must be `"seconds"`. The timebase uses seconds as its unit. |
| `origin_sec` | number | yes | Must be `0.0`. The origin is the absolute start of the referenced audio file. |

### Rules

- `audio_ref` is a JSON pointer (`/source/original` or `/source/working_audio`), not a flat string.
- `origin_sec` is always `0.0` — the origin is the absolute start of the referenced audio file.
- When no working audio has been generated, `audio_ref` must be `"/source/original"` and `source.working_audio` must be absent.
- Bar/beat positions are *derived* from the timebase, never replace it.

---

## 6. Analysis

The `analysis` block holds the overall status plus musical, audio-summary, and timeline sub-blocks. Each sub-block has its own status (Section 10) and `source_ref` into `provenance.components` when it produced data.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `analysis.status` | string | yes | Overall status: `ok`, `partial`, or `failed` (Section 10). |
| `analysis.musical` | object | yes | Musical analysis: BPM, Key (Section 6.2–6.3). |
| `analysis.audio_summary` | object | yes | Audio summary: Loudness, Brightness (Section 6.4–6.5). |
| `analysis.timeline` | object | yes | Timeline: Beats, Downbeats, Energy, Sections (Section 6.6–6.9). |

### 6.2 BPM

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `bpm.status` | string | yes | Individual status (Section 10). |
| `bpm.value` | number | conditional | Primary BPM value (float). Present when status is `ok` or `partial`. |
| `bpm.unit` | string | conditional | Must be `"bpm"` when `value` is present. |
| `bpm.normalization` | string | conditional | Actually applied tempo normalization strategy (e.g. `"none"`, `"heuristic"`). Part of the applied analysis configuration; not a display-only concern. |
| `bpm.source_ref` | string | conditional | Key into `provenance.components`. Required when `value` is present. |

**Rules:**

- No invented `bpm.confidence` field. Confidence is not part of the v1 BPM contract.
- `bpm.value` may be the raw librosa tempo estimate; BPM normalization is captured in `bpm.normalization` as the actually applied strategy (e.g. `"none"`, `"heuristic"`). No contract default for normalization semantics.
- `bpm.normalization` is part of the actually applied analysis configuration and must not be removed from the contract as a mere display topic.

### 6.3 Key

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key.status` | string | yes | Individual status (Section 10). |
| `key.root` | string | conditional | Root note name (e.g. `C`, `F#`). Present when available. |
| `key.key_conf` | number | conditional | Confidence as `chroma_peak_prominence` — the normalized chroma peak prominence (ratio, ~0-1). Not a calibrated probability. |
| `key.key_conf_kind` | string | conditional | Must be `"chroma_peak_prominence"` when `key_conf` is present. Documents the meaning of `key_conf`. |
| `key.source_ref` | string | conditional | Key into `provenance.components`. Required when a key value is present. |

**Rules:**

- `key.root` alone is valid — the public v1 contract contains only Root, `key_conf`, and `key_conf_kind`.
- `key.mode` is not part of v1. A later mode would be an additive future contract decision.
- `key_conf` is expressed as `chroma_peak_prominence` and explicitly **not** as a generic probability. See [`docs/benchmarks/KEY_CONF_EVIDENCE.md`](benchmarks/KEY_CONF_EVIDENCE.md) and issue [#72](https://github.com/jannekbuengener/sample-brain/issues/72).
- The `features.key` and `features.key_conf` columns in the Library catalog map to `key.root` and `key.key_conf` respectively.

### 6.4 Loudness

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `loudness.status` | string | yes | Individual status (Section 10). |
| `loudness.value` | number | conditional | Global RMS loudness in dBFS (float, typically negative). Present when status is `ok` or `partial`. |
| `loudness.unit` | string | conditional | Must be `"dBFS"` when `value` is present. |
| `loudness.method` | string | conditional | Must be `"global_rms"` when `value` is present. Documents the measuring method. |
| `loudness.source_ref` | string | conditional | Key into `provenance.components`. Required when `value` is present. |

**Rules:**

- Loudness is reported as global RMS in **dBFS**, not LUFS. LUFS is not part of the v1 contract.
- `features.loudness` in the Library catalog maps to `loudness.value`.

### 6.5 Brightness

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `brightness.status` | string | yes | Individual status (Section 10). |
| `brightness.value` | number | conditional | Mean spectral centroid in Hz (float). Present when status is `ok` or `partial`. |
| `brightness.unit` | string | conditional | Must be `"Hz"` when `value` is present. |
| `brightness.method` | string | conditional | Must be `"mean_spectral_centroid"` when `value` is present. |
| `brightness.source_ref` | string | conditional | Key into `provenance.components`. Required when `value` is present. |

**Rules:**

- Brightness is the mean spectral centroid in Hz.
- `features.brightness` in the Library catalog maps to `brightness.value`.

### 6.6 Beats

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `beats.status` | string | yes | Individual status (Section 10). |
| `beats.times_sec` | array of numbers | conditional | Sample-aligned beat positions in seconds on the shared timebase. Present when status is `ok` or `partial`. |
| `beats.source_ref` | string | conditional | Key into `provenance.components`. Required when data is present. |

### 6.7 Downbeats

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `downbeats.status` | string | yes | Individual status (Section 10). |
| `downbeats.times_sec` | array of numbers | conditional | Downbeat / bar positions in seconds on the shared timebase. Present when status is `ok` or `partial`. |
| `downbeats.beat_indices` | array of integers | no | Optional zero-based per-downbeat index into `beats.times_sec`. May be present only when `beats.status` is `ok` or `partial` and `beats.times_sec` is present. |
| `downbeats.source_ref` | string | conditional | Key into `provenance.components`. Required when data is present. |

**Rules:**

- When `downbeats.beat_indices` is present, `beats.status` must be `ok` or `partial` and `beats.times_sec` must be present.
- `downbeats.beat_indices` must contain exactly one entry per value in `downbeats.times_sec`.
- Indices are zero-based. Every index must satisfy `0 <= index < len(beats.times_sec)`.

### 6.8 Energy

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `energy.status` | string | yes | Individual status (Section 10). |
| `energy.grid_kind` | string | conditional | Must be `"uniform_time"` when values are present. |
| `energy.value_kind` | string | conditional | The actual kind of energy value produced (e.g. `rms_linear`, `rms_dbfs`, `spectral_flux`). No fixed default is assumed by the contract. |
| `energy.unit` | string | conditional | Unit of the values (e.g. `linear`, `dBFS`, `Hz`). No fixed default. |
| `energy.start_sec` | number | conditional | Start time of the grid on the shared timebase. |
| `energy.window_sec` | number | conditional | Analysis window in seconds. Required when `grid_kind` is `"uniform_time"` and status is `ok` or `partial`. |
| `energy.hop_sec` | number | conditional | Hop size in seconds. Required when `grid_kind` is `"uniform_time"` and status is `ok` or `partial`. |
| `energy.values` | array of numbers | conditional | Energy values at each grid point. |
| `energy.source_ref` | string | conditional | Key into `provenance.components`. Required when data is present. |

**Rules:**

- The contract stores only the parameter values the producing component actually used. No defaults are imposed for `window_sec`, `hop_sec`, or `value_kind`.
- When `grid_kind` is `"uniform_time"` and status is `ok` or `partial`, the fields `window_sec`, `hop_sec`, `value_kind`, `unit`, `start_sec`, `values`, and `source_ref` must all be present.
- Bar-synchronous energy forms (future) are additive: a future block may carry `value_kind` variants or a new sub-key without reinterpreting the existing `energy` block.

### 6.9 Sections

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sections.status` | string | yes | Individual status (Section 10). |
| `sections.items` | array of objects | conditional | Section items. Present when status is `ok` or `partial`. |
| `sections.items[].id` | string | yes | Unique identifier for the section within this Track Map. |
| `sections.items[].start_sec` | number | yes | Start position in seconds. **Inclusive.** |
| `sections.items[].end_sec` | number | yes | End position in seconds. **Exclusive.** |
| `sections.items[].label` | string | no | Neutral section label, if the component produced one. |
| `sections.items[].label_namespace` | string | conditional | Namespace of the label (e.g. `structure_v1`). Required when `label` is present. |
| `sections.source_ref` | string | conditional | Key into `provenance.components`. Required when data is present. |

**Rules:**

- Sections use `items[]` objects, **not** parallel arrays of `boundaries_sec` and `labels`.
- Start is inclusive; end is exclusive.
- Techno arrangement roles (`intro`, `drop`, `breakdown`, etc.) are **not** part of this block — they live in the Arrangement Map (#228 / #238–#243).
- MFCC / chroma raw arrays remain as **raw arrays outside the public v1 contract**. They are stored in the Library catalog as BLOBs (`features.mfcc_mean`, `features.chroma_mean`) and are not serialized into the Track Map v1 body. Future v2 contracts may reference them.

### Not-run blocks

When a timeline block has `status: "not_run"`, no position/value arrays are emitted. This is the expected state when beats, downbeats, energy, or sections have not been computed. `not_run` carries a `reason_code` (Section 10.1).

---

## 7. Analysis Status (overall)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `analysis.status` | string | yes | `ok`, `partial`, or `failed`. |

**Rules:**

- `analysis.status` = `ok` — all components required for the actual analysis purpose completed successfully. Components not requested or not yet available may be `not_run` and do not degrade the status.
- `analysis.status` = `partial` — the analysis purpose remains usable, but at least one **requested** component produced `partial`, `failed`, `no_result`, or could not be started.
- `analysis.status` = `failed` — the requested analysis purpose is not meaningfully fulfillable (a required top-level step failed).
- No separate `requested_modules` structure is added; the distinction between requested and optional components is implicit in the analysis purpose definition.

---

## 8. Provenance

The Track Map uses a **centralized** `provenance.components` registry. Each analysis value references its producing component via `source_ref`. Inline provenance is not part of the v1 contract.

`provenance.components` is a JSON object (map). Each key is a component identifier; each value is the component metadata. **Both `provenance` and `provenance.components` are required.**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `component` | string | yes | Sample-Brain component name (e.g. `scan`, `analyze`, `beat_grid`, `structure_v1`). |
| `sample_brain_version` | string | yes | Version of sample-brain (or the track-deconstruction sub-tool) that produced the result. |
| `backend.name` | string | conditional | Backend used (e.g. `librosa`, `beat_this`). Absent if no backend applies. |
| `backend.version` | string | conditional | Backend/library version, if applicable. |
| `model.name` | string | conditional | Model identifier, if a model was used. Absent for algorithmic components. |
| `model.version` | string | conditional | Model version, if a model was used. Either `model.version` or `model.revision` may be present. |
| `model.revision` | string | conditional | Model revision / hash, if a model was used. Either `model.version` or `model.revision` may be present. |
| `configuration` | object | yes | Relevant configuration values that affected the result. Must not contain secrets. If no special parameters are needed, use `{}`. |

### Rules

- Provenance records document **what was actually used**, not what was available.
- **Never** include: secrets, private absolute paths, model-cache paths, or private sample-directory paths.
- Each analysis block (source, bpm, key, loudness, brightness, beats, downbeats, energy, sections) has its own `source_ref` entry into `provenance.components` when it produced data.
- A component entry may be referenced by multiple analysis blocks (e.g. `analyze` may back BPM, key, loudness, and brightness).

---

## 9. Quality Notes

Machine-readable quality notes provide structured hints about data quality, confidence, or processing anomalies. Both `quality` and `quality.notes` are required; `quality.notes` may be an empty array.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `quality.notes` | array | yes | Array of quality note objects (may be empty). |
| `quality.notes[].code` | string | yes | Stable code identifier (e.g. `SHORT_SAMPLE`, `LOW_KEY_CONF`, `MISSING_DOWNBEAT`). |
| `quality.notes[].severity` | string | yes | `info`, `warning`, or `error`. |
| `quality.notes[].path` | string | yes | JSON Pointer path to the affected field (e.g. `/analysis/musical/key`). Must not contain private paths. |
| `quality.notes[].message` | string | yes | Human-readable message. |

### Rules

- Quality notes are advisory and machine-readable. They do not change the status model but annotate it.
- Each note's `path` must be a valid JSON Pointer pointing to a location within this v1 contract or to a known future extension point.

---

## 10. Status Model

### 10.1 Individual status

Each analysis sub-component and each timeline block carries one of:

| Status | Meaning | Required extra fields |
|--------|---------|-----------------------|
| `ok` | Component ran successfully and produced a complete result. | `source_ref` when data is present. |
| `partial` | Component ran but produced only partial result (e.g. detected some beats, not all). | `source_ref` when data is present. |
| `not_run` | Component was not requested or is not available. No data is produced and none is invented. | `reason_code` (required). No `source_ref`. |
| `failed` | Component was requested and attempted, but errored. | `error.code`, `error.message`, `source_ref`. Optional `error.retryable`. |
| `no_result` | Component ran successfully but produced no meaningful result (e.g. BPM undetectable). | `reason_code` (required), `source_ref`. |

### Status field details

- `reason_code` (string): A stable machine-readable code explaining why the component was `not_run` or produced `no_result` (e.g. `BEAT_GRID_NOT_REQUESTED`, `BPM_UNDETECTABLE`).
- `error` (object): Present when `status` is `failed`.
  - `error.code` (string): Stable error code.
  - `error.message` (string): Human-readable error message.
  - `error.retryable` (boolean): Optional. Whether retrying may succeed.

### 10.2 Status matrix

```
component status        -->  analysis.status contribution
ok                        -->  ok (no degradation)
partial                   -->  partial
failed                    -->  partial (or failed if required)
no_result                 -->  partial (component ran but had nothing to say)
not_run                   -->  ok (does NOT degrade overall; only if not requested)
```

---

## 11. Full Field Reference

| Field (dotted path) | Required | Type | Notes |
|---|---|---|---|
| `document_type` | yes | string | `"sample_brain.track_map"` |
| `schema_version` | yes | string | `"1.0.0"` |
| `source.original.file_name` | yes | string | Base name |
| `source.original.relative_uri` | no | string | Relative to Track Map file |
| `source.original.size_bytes` | no | integer | File size |
| `source.original.hash.algorithm` | yes | string | e.g. `sha1` |
| `source.original.hash.value` | yes | string | Hex digest |
| `source.original.audio_properties.duration_sec` | yes | number | Seconds |
| `source.original.audio_properties.sample_rate_hz` | yes | integer | Hz |
| `source.original.audio_properties.channels` | yes | integer | Channel count |
| `source.original.source_ref` | yes | string | Key into `provenance.components` |
| `source.working_audio` | no | object | Only when working WAV exists |
| `timebase.audio_ref` | yes | string | JSON pointer: `/source/original` or `/source/working_audio` |
| `timebase.unit` | yes | string | `"seconds"` |
| `timebase.origin_sec` | yes | number | `0.0` |
| `analysis.status` | yes | string | `ok`, `partial`, `failed` |
| `analysis.musical.bpm.status` | yes | string | Individual status |
| `analysis.musical.bpm.value` | conditional | number | When status ok/partial |
| `analysis.musical.bpm.unit` | conditional | string | `"bpm"` |
| `analysis.musical.bpm.normalization` | conditional | string | Applied tempo normalization |
| `analysis.musical.bpm.source_ref` | conditional | string | Key into `provenance.components` |
| `analysis.musical.key.status` | yes | string | Individual status |
| `analysis.musical.key.root` | conditional | string | When available |
| `analysis.musical.key.key_conf_kind` | conditional | string | Must be `chroma_peak_prominence` |
| `analysis.musical.key.key_conf` | conditional | number | Normalized prominence (0-1) |
| `analysis.musical.key.source_ref` | conditional | string | Key into `provenance.components` |
| `analysis.audio_summary.loudness.status` | yes | string | Individual status |
| `analysis.audio_summary.loudness.value` | conditional | number | dBFS |
| `analysis.audio_summary.loudness.unit` | conditional | string | `"dBFS"` |
| `analysis.audio_summary.loudness.method` | conditional | string | `"global_rms"` |
| `analysis.audio_summary.loudness.source_ref` | conditional | string | Key into `provenance.components` |
| `analysis.audio_summary.brightness.status` | yes | string | Individual status |
| `analysis.audio_summary.brightness.value` | conditional | number | Hz |
| `analysis.audio_summary.brightness.unit` | conditional | string | `"Hz"` |
| `analysis.audio_summary.brightness.method` | conditional | string | `"mean_spectral_centroid"` |
| `analysis.audio_summary.brightness.source_ref` | conditional | string | Key into `provenance.components` |
| `analysis.timeline.beats.status` | yes | string | Individual status |
| `analysis.timeline.beats.times_sec` | conditional | array | When status ok/partial |
| `analysis.timeline.beats.source_ref` | conditional | string | Key into `provenance.components` |
| `analysis.timeline.downbeats.status` | yes | string | Individual status |
| `analysis.timeline.downbeats.times_sec` | conditional | array | When status ok/partial |
| `analysis.timeline.downbeats.beat_indices` | no | array | Zero-based; requires resolvable `beats.times_sec`, matching downbeat count, and in-range indices |
| `analysis.timeline.downbeats.source_ref` | conditional | string | Key into `provenance.components` |
| `analysis.timeline.energy.status` | yes | string | Individual status |
| `analysis.timeline.energy.grid_kind` | conditional | string | `"uniform_time"` |
| `analysis.timeline.energy.value_kind` | conditional | string | Actually used kind; no default |
| `analysis.timeline.energy.unit` | conditional | string | No default |
| `analysis.timeline.energy.start_sec` | conditional | number | Grid start |
| `analysis.timeline.energy.window_sec` | conditional | number | Required when uniform_time and ok/partial |
| `analysis.timeline.energy.hop_sec` | conditional | number | Required when uniform_time and ok/partial |
| `analysis.timeline.energy.values` | conditional | array | When status ok/partial |
| `analysis.timeline.energy.source_ref` | conditional | string | Key into `provenance.components` |
| `analysis.timeline.sections.status` | yes | string | Individual status |
| `analysis.timeline.sections.items` | conditional | array | When status ok/partial |
| `analysis.timeline.sections.items[].id` | yes | string | Unique section ID |
| `analysis.timeline.sections.items[].start_sec` | yes | number | Start (inclusive) |
| `analysis.timeline.sections.items[].end_sec` | yes | number | End (exclusive) |
| `analysis.timeline.sections.items[].label` | no | string | Neutral label |
| `analysis.timeline.sections.items[].label_namespace` | conditional | string | Required when `label` present |
| `analysis.timeline.sections.source_ref` | conditional | string | Key into `provenance.components` |
| `provenance` | yes | object | Centralized component registry |
| `provenance.components` | yes | object | Map of component ID → metadata |
| `provenance.components[key].component` | yes | string | Component name |
| `provenance.components[key].sample_brain_version` | yes | string | Version |
| `provenance.components[key].backend.name` | conditional | string | Backend name |
| `provenance.components[key].backend.version` | conditional | string | Backend version |
| `provenance.components[key].model.name` | conditional | string | Model name |
| `provenance.components[key].model.version` | conditional | string | Model version |
| `provenance.components[key].model.revision` | conditional | string | Model revision |
| `provenance.components[key].configuration` | yes | object | Config values; no secrets; `{}` if none |
| `quality` | yes | object | Quality notes container |
| `quality.notes` | yes | array | Quality notes array (may be empty) |
| `quality.notes[].code` | yes | string | Stable code |
| `quality.notes[].severity` | yes | string | `info`, `warning`, `error` |
| `quality.notes[].path` | yes | string | JSON Pointer path (e.g. `/analysis/musical/key`); no private paths |
| `quality.notes[].message` | yes | string | Human-readable |

---

## 12. Complete JSON Example

This example reflects what the current runtime (as of `main`, without Track Deconstruction implementation) can produce. Timeline blocks are `not_run`; key has no mode; BPM has no confidence. The overall `analysis.status` is `ok` because `not_run` blocks do not degrade it.

```json
{
  "document_type": "sample_brain.track_map",
  "schema_version": "1.0.0",
  "source": {
    "original": {
      "file_name": "my_track.wav",
      "relative_uri": "./audio/my_track.wav",
      "size_bytes": 43218901,
      "hash": {
        "algorithm": "sha1",
        "value": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
      },
      "audio_properties": {
        "duration_sec": 312.04,
        "sample_rate_hz": 44100,
        "channels": 2
      },
      "source_ref": "scan"
    }
  },
  "timebase": {
    "audio_ref": "/source/original",
    "unit": "seconds",
    "origin_sec": 0.0
  },
  "analysis": {
    "status": "ok",
    "musical": {
      "bpm": {
        "status": "ok",
        "value": 128.0,
        "unit": "bpm",
        "normalization": "none",
        "source_ref": "analyze"
      },
      "key": {
        "status": "ok",
        "root": "C",
        "key_conf": 0.82,
        "key_conf_kind": "chroma_peak_prominence",
        "source_ref": "analyze"
      }
    },
    "audio_summary": {
      "loudness": {
        "status": "ok",
        "value": -14.2,
        "unit": "dBFS",
        "method": "global_rms",
        "source_ref": "analyze"
      },
      "brightness": {
        "status": "ok",
        "value": 4620.0,
        "unit": "Hz",
        "method": "mean_spectral_centroid",
        "source_ref": "analyze"
      }
    },
    "timeline": {
      "beats": {
        "status": "not_run",
        "reason_code": "BEAT_GRID_NOT_REQUESTED"
      },
      "downbeats": {
        "status": "not_run",
        "reason_code": "BEAT_GRID_NOT_REQUESTED"
      },
      "energy": {
        "status": "not_run",
        "reason_code": "ENERGY_NOT_REQUESTED"
      },
      "sections": {
        "status": "not_run",
        "reason_code": "STRUCTURE_NOT_REQUESTED"
      }
    }
  },
  "provenance": {
    "components": {
      "scan": {
        "component": "scan",
        "sample_brain_version": "0.9.0",
        "configuration": {
          "hash_algorithm": "sha1"
        }
      },
      "analyze": {
        "component": "analyze",
        "sample_brain_version": "0.9.0",
        "backend": {
          "name": "librosa",
          "version": "0.11.0"
        },
        "configuration": {
          "chroma_algorithm": "cqt"
        }
      }
    }
  },
  "quality": {
    "notes": []
  }
}
```

---

## 13. Acceptance Mapping (Issue #232)

| #232 Acceptance criterion | This document |
|---------------------------|---------------|
| Canonical repo documentation names `schema_version: 1.0.0` and `document_type` | Section 3 |
| Portable JSON example and field description are present | Sections 4–12, 13 |
| Required, optional, and status-based fields are clearly explained | Sections 4–12, 11 |
| No private absolute paths are part of the contract | Sections 2, 4, 8 |
| Key Root without invented Mode is valid | Section 6.3, 12 |
| BPM without invented confidence is valid | Section 6.2, 12 |
| Energy grid and provenance are per-component | Sections 6.8, 8, 12 |
| Arrangement, Stem, and Asset documents are separately referenced | Sections 1, 14 |
| Implementation is clearly distinguished from documentation | Sections 12, 15 |

---

## 14. Boundaries — What Is NOT in the Track Map v1

The Track Map deliberately excludes the following. They have or will have their own contracts:

| Not in Track Map v1 | Why | Separate contract (planned) |
|---------------------|-----|---------------------------|
| Techno arrangement roles (`intro`, `drop`, `breakdown`, etc.) | Functional interpretation over neutral boundaries | Arrangement Map (#228 / #238-#243) |
| Technical stems (`drums`, `bass`, `vocals`, `other`) | Separation output; separate model/cache | Stem Manifest (#229 / #244-#249) |
| Producer groups (`kick_bass`, `melodic`, etc.) | Musical grouping over technical stems | Asset Manifest (#230 / #250-#256) + #268 |
| Loops | 4/8/16-bar asset candidates | Asset Manifest (#230 / #250-#254) |
| Sections as finished assets | Rendered assets, not raw boundaries | Asset Manifest (#230 / #255, #266, #267) |
| Performance-Pack-specific fields | Pack manifest aggregates references | Performance Pack (#231 / #257-#264) |
| Track metadata (ISRC, artist, album, release_date, etc.) | Not part of the accepted v1 contract | -- |
| SQLite-internal data structures | Internal implementation detail | Library Intelligence spec, section 3 |
| MFCC / chroma raw arrays | Outside public v1 contract | Future v2 contract |

**Key distinction:** Technical stems are **not** the same as producer-ready assets. Stems are raw model outputs (`drums`, `bass`, `vocals`, `other`). Producer groups (e.g. `kick_bass` = kick + musical bassline) and assets (loops, sections) are downstream musical interpretations that consume stems but are never embedded in the Track Map.

---

## 15. Related Documents

| Document | Role |
|----------|------|
| [`docs/product/03_TRACK_CONTEXT_ANALYSIS_SPEC.md`](product/03_TRACK_CONTEXT_ANALYSIS_SPEC.md) | Track profile for VST/workspace context (sample-level) |
| [`docs/product/01_LIBRARY_INTELLIGENCE_SPEC.md`](product/01_LIBRARY_INTELLIGENCE_SPEC.md) | Catalog analysis: BPM, key, loudness, brightness, MFCC, chroma |
| [`docs/product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`](product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md) | Fit scoring on Track Map fields |
| [`docs/TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md) | Module boundaries, pipeline contracts |
| [`docs/DATA_AND_ARTIFACT_POLICY.md`](DATA_AND_ARTIFACT_POLICY.md) | Artifact hygiene (no DB/stems/audio in repo) |
| [Issue #227](https://github.com/jannekbuengener/sample-brain/issues/227) | Meta: Track Intelligence & Track Map |
| [Issue #232](https://github.com/jannekbuengener/sample-brain/issues/232) | This contract's tracking issue |
| [Issue #234](https://github.com/jannekbuengener/sample-brain/issues/234) | Canonical working WAV and shared timebase |
| [Issue #236](https://github.com/jannekbuengener/sample-brain/issues/236) | BeatGrid backend adapter |
| [Issue #265](https://github.com/jannekbuengener/sample-brain/issues/265) | StructureV1 bar-synchronous boundaries |
| [Issue #268](https://github.com/jannekbuengener/sample-brain/issues/268) | Producer-oriented stem grouping |
| [Issue #230](https://github.com/jannekbuengener/sample-brain/issues/230) | Intelligent loop & section asset generation |
| [Issue #231](https://github.com/jannekbuengener/sample-brain/issues/231) | Song to Performance Pack |

---

## 16. Implementation Status

| Component | Status on `main` | Track Map role |
|-----------|-----------------|----------------|
| Library analysis (BPM, key, loudness, brightness) | Shipped (`src/analyze.py`) | Feeds section 6 fields |
| BeatGrid (#236) | Not implemented | Feeds section 6.6 beats / 6.7 downbeats |
| StructureV1 (#265) | Not implemented | Feeds section 6.9 sections |
| Energy timeline | Not implemented | Feeds section 6.8 energy |
| Track Deconstruction orchestrator (#227) | Not implemented | Assembles full Track Map |
| Stem separation (#244-#249) | Not implemented | Stem Manifest (separate) |
| Asset generation (#250-#256) | Not implemented | Asset Manifest (separate) |
| Performance Pack (#257-#264) | Not implemented | Pack manifest (separate) |

The Track Map v1 contract is **produced by future Track Deconstruction steps**, not by current `main`. This document defines the canonical contract; runtime production is a separate issue (#233).
