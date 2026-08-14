# Performance Pack Manifest v1 — Canonical Contract

**Issue:** [#257](https://github.com/jannekbuengener/sample-brain/issues/257)
**Parent:** [#231](https://github.com/jannekbuengener/sample-brain/issues/231) — Song to Sample / Performance Pack
**Depends on:** [#227](https://github.com/jannekbuengener/sample-brain/issues/227) (Track Intelligence & Track Map), [#250](https://github.com/jannekbuengener/sample-brain/issues/250) (Loop & Section Asset Manifest)
**Status on issue tracker:** `OPEN` / documented on branch `docs/performance-pack-manifest-v1`
**Schema version:** `1.0.0`
**Document type:** `sample_brain.performance_pack_manifest`

This document defines the canonical, portable **Performance Pack manifest** contract for Sample Brain (#231). A Performance Pack is the aggregation of the separately-produced, track-level documents of a single original track:

- the **Track Map** (#232 / #227),
- the **Arrangement Map** (#228),
- **Asset Manifests** for loops and sections (#250 / #230),
- optional **Stem Manifests** (#229).

The Performance Pack manifest references those documents by portable ID and portable relative path. It never embeds their bodies, never stores SQLite internals, and never contains absolute, private, or machine-local paths.

---

## 1. Purpose

The Performance Pack manifest is the single portable entry point that lets an external consumer reconstruct, audit, or re-import a deconstructed track without access to the Sample-Brain SQLite catalog. It:

- identifies the original track portably (content hash + portable ID),
- references the Track Map, Arrangement Map, Asset Manifests, and optional Stem Manifests,
- keeps every referenced document as a **separate** file,
- records per-component status so missing optional results do not invalidate an otherwise valid pack,
- records provenance for the pack assembly and for the components that produced the referenced outputs.

A Performance Pack is a **collection of references plus their traceable summaries** — not a merged copy of the referenced documents.

---

## 2. Design Principles

| Principle | Rule |
|-----------|------|
| **Portable IDs, not local paths** | Content hash + portable IDs identify the track, sources, and assets. No absolute local paths, no `file://`, no drive letters, no UNC paths, no `..` segments. |
| **No SQLite-internal IDs as external identity** | The pack never requires a SQLite row id to be consumed. `track_id` / `asset_id` / `stem_id` are portable, opaque, or hash-derived identities. |
| **Separate documents stay separate** | Track Map, Arrangement Map, Stem Manifest, and Asset Manifest remain separate files. The pack references them; it does not semantically merge them. |
| **Technical stems ≠ producer assets** | Technical stems (#229) and producer groups (#268) are distinct concepts. The pack references Stem Manifests separately from Asset Manifests. |
| **Status, not invented data** | Every referenced component carries a status (`ok` / `partial` / `not_run` / `failed` / `no_result`). Missing optional results are represented, never fabricated. |
| **Provenance describes only what was used** | Provenance records the components actually used to build the pack and the referenced outputs. No secrets, no private paths, no model-cache paths. |
| **Additive evolution** | New optional fields and optional document kinds can be added in `1.x.x` without reinterpreting existing fields. |
| **External consumer needs only the pack + referenced files** | A consumer needs the Performance Pack manifest, the referenced portable documents, and the referenced audio files. It must not require the SQLite DB, local absolute paths, internal worktree structure, or private model caches. |

---

## 3. Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `document_type` | string | yes | Must be `"sample_brain.performance_pack_manifest"`. |
| `schema_version` | string | yes | SemVer `MAJOR.MINOR.PATCH`. This revision is `"1.0.0"`; compatible v1 documents may use `1.x.x`. |
| `pack_id` | string | yes | Portable, unique identity of this pack. Synthetic/opaque; typically derived from `track_id` plus a run suffix. |
| `source_track` | object | yes | Portable identity of the original track (Section 5). |
| `documents` | object | yes | References to the separate documents (Section 6). `track_map` is required; `arrangement` and `stem_manifest` are optional. |
| `assets` | array | yes | Asset Manifest references, one per loop/section asset (Section 7). May be empty if no assets were produced. |
| `stems` | array | no | Optional Stem Manifest references (Section 8). Omit or empty when no stems were produced. |
| `status` | string | yes | Overall pack status: `complete`, `partial`, or `failed` (Section 10). |
| `provenance` | object | yes | Centralized component registry (Section 11). |
| `quality` | object | yes | Quality notes (Section 12). |

### Versioning

- **MAJOR** increments when a previously required field is removed/renamed in a breaking way, or when the status enum or a referenced document-type contract changes in a breaking way.
- **MINOR** increments when new optional fields or additive optional structures are introduced, provided existing v1 fields and enums retain their meaning.
- **PATCH** increments for non-breaking documentation or example corrections.
- The current frozen revision is `1.0.0`; this document does not raise that version.
- Readers must **reject** (fail-closed) any Performance Pack whose `schema_version` major number is unsupported. v1 consumers accept compatible `1.x.x` documents.

---

## 4. Identifiers and Portable References

All references in this contract are **portable**:

- `pack_id`, `track_id`, `asset_id`, `stem_id` — portable, stable identities. No semantic meaning is required; a hash-derived or synthetic opaque value is acceptable.
- `ref` fields (`source_track.track_ref`, `documents.*.ref`, `assets[].asset_ref`, `stems[].stem_ref`) — portable references to the referenced file, expressed as a **relative URI** relative to the Performance Pack manifest file (e.g. `analysis/track_map.json`, `analysis/arrangement_map.json`, `loops/loop_asset_loop_xxx.json`, `sections/section_asset_section_xxx.json`, `stems/stem_drums_01.json`). The concrete directory and file-naming standard for these relative URIs is defined in #258 (Performance Pack Layout v1).

**Forbidden in any `ref` or identity field:** absolute filesystem paths, drive letters (`C:\`), UNC paths (`\\host`), `file://` URLs, and `..` path segments.

---

## 5. Source Track

The `source_track` block gives the portable identity and technical audio properties of the original track. It is the anchor for all traceability back to the original track.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_track.track_id` | string | yes | Portable identity of the original track. Typically derived from the content hash. |
| `source_track.track_ref` | string | yes | Portable reference to the Track Map document for this track (relative URI). Must equal `documents.track_map.ref`. |
| `source_track.file_name` | string | yes | Portable base file name of the original track (no path). |
| `source_track.hash` | object | yes | Content hash: `{ "algorithm": string, "value": string }`. Authoritative identity key. |
| `source_track.audio_properties` | object | yes | `{ "duration_sec": number, "sample_rate_hz": integer, "channels": integer }`. Technical audio properties of the original track. |

**Rules**

- `source_track.hash.value` is the authoritative identity key; `file_name` and `audio_properties` are descriptive.
- No absolute path, private library root, or SQLite row id is serialized as the external identity.
- `source_track.track_ref` and `documents.track_map.ref` must agree (same portable reference to the Track Map).

---

## 6. Documents

`documents` references the separate documents that make up the pack. Each entry has:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ref` | string | yes | Portable relative reference to the document file. |
| `document_type` | string | yes | Document type of the referenced file. |
| `schema_version` | string | yes | Schema version of the referenced document (SemVer). |
| `status` | string | yes | `ok`, `partial`, `not_run`, `failed`, or `no_result`. |
| `reason_code` | string | conditional | Required when `status` is `not_run` or `no_result`. |
| `hash` | object | no | Content hash of the referenced document file: `{ "algorithm": string, "value": string }`. Recommended for integrity. |

### 6.1 `documents.track_map` (required)

| Field | Value |
|-------|-------|
| `document_type` | `"sample_brain.track_map"` |
| `schema_version` | Compatible v1 (`1.x.x`); current Track Map is `1.0.0`. |

The Track Map is the **required** anchor of every pack. A pack without a resolvable, non-`failed` Track Map is invalid (see Section 10).

### 6.2 `documents.arrangement` (optional)

| Field | Value |
|-------|-------|
| `document_type` | `"sample_brain.arrangement_map"` (finalized in #228) |
| `schema_version` | Compatible v1 once #228 lands; provisional drafts use a `-draft` suffix (e.g. `0.1.0-draft`). |

The Arrangement Map is optional. Its absence (or `not_run` / `no_result` status) does not invalidate the pack. A `partial` Arrangement Map marks the pack `partial` but keeps it valid.

### 6.3 `documents.stem_manifest` (optional)

| Field | Value |
|-------|-------|
| `document_type` | `"sample_brain.stem_manifest"` (finalized in #229 / #244–#249) |
| `schema_version` | Compatible v1 (`1.x.x`); current canonical version is `1.0.0`. |

The Stem Manifest is optional. Absence means no technical stems were produced; this is a normal, valid state.

---

## 7. Assets

`assets` is an array of references to Asset Manifests (#250), one entry per loop or section asset. Each entry:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `asset_id` | string | yes | Portable identity of the asset. Must match the referenced Asset Manifest `asset_id`. |
| `asset_ref` | string | yes | Portable relative reference to the Asset Manifest file. |
| `document_type` | string | yes | Must be `"sample_brain.asset_manifest"`. |
| `schema_version` | string | yes | Asset Manifest schema version. Current Asset Manifest is `1.1.0`. |
| `asset_kind` | string | yes | `"loop"` or `"section"`. The asset kind is explicit, never inferred from file name. |
| `source_kind` | string | yes | `"master"`, `"stem"`, or `"producer_group"`. |
| `track_ref` | string | yes | Portable reference to the original track. Must equal `source_track.track_id`. |
| `range` | object | yes | Authoritative sample range summary (Section 7.1). |
| `stem_id` | string | conditional | Technical stem ID. Required when `source_kind = "stem"`. `null` otherwise. |
| `stem_ref` | string | conditional | Portable reference to the Stem Manifest entry. Required when `source_kind = "stem"`. `null` otherwise. |
| `producer_group_id` | string | conditional | Producer-group ID. Required when `source_kind = "producer_group"`. `null` otherwise. |
| `producer_group_ref` | string | conditional | Portable reference to the producer-group definition. Required when `source_kind = "producer_group"`. `null` otherwise. |
| `status` | string | yes | `ok`, `partial`, `not_run`, `failed`, or `no_result`. |
| `hash` | object | no | Content hash of the referenced Asset Manifest file. Recommended. |

### 7.1 Asset range summary

To make every asset traceable to its sample-time region from the pack alone (without opening each Asset Manifest), each asset entry carries a `range` summary:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `range.start_sample` | integer | yes | Inclusive first sample on the original-track timebase. `>= 0`. |
| `range.end_sample_exclusive` | integer | yes | Exclusive end sample. `> start_sample`. |
| `range.n_samples` | integer | yes | `end_sample_exclusive - start_sample`. Must be `> 0`. |
| `range.sample_rate_hz` | integer | yes | Sample rate of the referenced audio. |

### 7.2 Rules

- `asset_kind` is authoritative; a consumer must never infer loop vs section from `asset_id`, file name, or position.
- `source_kind` distinguishes master / stem / producer_group. Technical stems and producer groups are never equated.
- When `source_kind = "stem"`, `stem_id` and `stem_ref` are required and link the asset back to its Stem Manifest and, via `track_ref`, to the original track.
- `track_ref` provides whole-track traceability for every asset.
- A `failed` asset marks the pack `partial` (degraded but consumable); it does not make the whole pack `failed`.

---

## 8. Stems (optional)

`stems` is an array of references to Stem Manifests (#229). It is **optional** — omit it or leave it empty when no technical stems were produced. Each entry:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `stem_id` | string | yes | Portable technical stem identity (e.g. `stem_drums_01`). |
| `stem_ref` | string | yes | Portable relative reference to the Stem Manifest file. |
| `document_type` | string | yes | Must be `"sample_brain.stem_manifest"`. |
| `schema_version` | string | yes | Stem Manifest schema version. Current canonical version is `1.0.0`. |
| `track_ref` | string | yes | Portable reference to the original track. Must equal `source_track.track_id`. |
| `status` | string | yes | `ok`, `partial`, `not_run`, `failed`, or `no_result`. |
| `hash` | object | no | Content hash of the referenced Stem Manifest file. Recommended. |

### 8.1 Rules

- An optional Stem Manifest that is `not_run` / `no_result` never invalidates the pack.
- A `failed` Stem Manifest marks the pack `partial`, not `failed`.
- Each stem keeps its traceability back to the original track via `track_ref`.

---

## 9. Relationships and Traceability

The following relationships must remain traceable from the pack:

| Relationship | Encoded by |
|--------------|-----------|
| Pack → Original track | `source_track.track_id` / `source_track.hash` |
| Pack → Track Map | `documents.track_map.ref` (+ `source_track.track_ref`) |
| Pack → Arrangement Map | `documents.arrangement.ref` (optional) |
| Pack → Asset Manifest | `assets[].asset_ref` |
| Pack → Stem Manifest | `stems[].stem_ref` (optional) |
| Asset → Original track | `assets[].track_ref` |
| Asset → Sample time region | `assets[].range` (`start_sample` / `end_sample_exclusive`) |
| Asset → master / stem / producer_group source | `assets[].source_kind` + `stem_id`/`stem_ref` or `producer_group_id`/`producer_group_ref` |
| Optional Stem → Original track | `stems[].track_ref` |

No relationship requires SQLite internals or private paths.

---

## 10. Status Model

### 10.1 Overall pack status

`status` is one of:

| Status | Meaning | Rule |
|--------|---------|------|
| `complete` | All referenced components are `ok`, `no_result`, or `not_run`. No referenced component is `partial` or `failed`. The pack is fully consumable. | Default when no degradation present. |
| `partial` | At least one referenced component has status `partial` or `failed`, but the required Track Map is present and not `failed`. The pack is still consumable but degraded. | e.g. a `partial` Arrangement Map, or a `failed` optional asset/stem. |
| `failed` | The required Track Map is missing or has status `failed`. The pack cannot be meaningfully consumed. | Only the required anchor can force `failed`. |

### 10.2 Deterministic aggregation rules

1. If `documents.track_map` is missing, or `documents.track_map.status == "failed"` → `status = "failed"`.
2. Else if any present referenced component (the optional `arrangement`, any `assets[]` entry, or any `stems[]` entry) has status `partial` or `failed` → `status = "partial"`.
3. Else → `status = "complete"`.

**Key guarantees**

- A missing or `no_result` / `not_run` **optional** component (Arrangement Map, Stem Manifest, or an asset that was simply not requested) does **not** downgrade a `complete` pack.
- An optional component that is `partial` or `failed` degrades the pack to `partial` but never to `failed`.
- Only the required Track Map can force `failed`.

### 10.3 Per-component status values

Each referenced document and asset/stem entry uses the shared status enum: `ok`, `partial`, `not_run`, `failed`, `no_result`. `not_run` / `no_result` carry a `reason_code` (for documents) and never invent result data.

---

## 11. Provenance

Reuses the centralized `provenance.components` registry convention from the Track Map (#232) and Asset Manifest (#250).

`provenance.components` is a JSON object (map). Each key is a component identifier; each value is component metadata. **Both `provenance` and `provenance.components` are required.**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `component` | string | yes | Sample-Brain component name (e.g. `pack_assembler`, `beat_grid`, `arrangement_map`). |
| `sample_brain_version` | string | yes | Version of sample-brain that produced the result. |
| `backend.name` | string | conditional | Backend used (e.g. `librosa`). Absent if no backend applies. |
| `backend.version` | string | conditional | Backend/library version, if applicable. |
| `model.name` | string | conditional | Model identifier, if a model was used. |
| `model.version` / `model.revision` | string | conditional | Model version/revision, if a model was used. |
| `configuration` | object | yes | Relevant configuration that affected the result. Must not contain secrets. Use `{}` if none. |

**Rules**

- Provenance records document **what was actually used**, not what was available.
- **Never** include: secrets, private absolute paths, model-cache paths, or private sample-directory paths.
- The pack assembler is recorded as `pack_assembler` (or an agreed component name); referenced analysis/renderer components may be mirrored here for auditability.

---

## 12. Quality Notes

Reuses the Track Map `quality.notes` convention.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `quality.notes` | array | yes | Array of quality note objects (may be empty). |
| `quality.notes[].code` | string | yes | Stable code (e.g. `PARTIAL_ARRANGEMENT`, `MISSING_STEM`). |
| `quality.notes[].severity` | string | yes | `info`, `warning`, or `error`. |
| `quality.notes[].path` | string | yes | JSON Pointer to the affected field. Must not contain private paths. |
| `quality.notes[].message` | string | yes | Human-readable message. |

---

## 13. Portability Contract for External Consumers

An external consumer must be able to fully consume a Performance Pack using **only**:

- the Performance Pack manifest,
- the referenced portable documents (Track Map, Arrangement Map, Asset Manifests, optional Stem Manifests),
- the referenced audio files.

It must **not** require:

- the Sample-Brain SQLite database,
- local absolute filesystem paths,
- internal worktree structure,
- private model caches.

All identities and references in the pack are portable; all paths are relative URIs resolved against the pack manifest file location.

---

## 14. Examples

All IDs, hashes, and paths below are **synthetic**. No private track names, sample names, or absolute paths are used. The machine-readable versions are in `performance_pack_manifest_v1_examples.json` and are validated by `tests/test_performance_pack_manifest_contract.py`.

### 14.1 Complete full pack (Track Map + Arrangement + Assets + Stems)

See `examples.complete_full_pack` in the JSON fixture. It references a Track Map (`1.0.0`), an Arrangement Map (`0.1.0-draft`), two Asset Manifests (one loop from master, one section from a stem), and one Stem Manifest. `status` is `complete`.

### 14.2 Valid pack without optional stems

See `examples.valid_without_optional_stems` in the JSON fixture. It omits the optional `stems` block entirely and has no Stem Manifest reference. Because stems are optional, the pack remains `complete`.

### 14.3 Pack with a partially produced optional result

See `examples.partial_optional_result` in the JSON fixture. The Track Map and one asset are `ok`, but the optional Arrangement Map is `partial`. Per Section 10, the pack status is `partial` — the missing optional quality degrades but does not destroy the pack.

---

## 15. Acceptance Mapping (Issue #257)

| #257 criterion | This document |
|----------------|---------------|
| Manifest v1 dokumentiert | Entire document. |
| Track, Sections, Loops und Stems abbildbar | `source_track` + `documents` + `assets` (loop/section) + optional `stems` (Sections 5–8). |
| externe Verbraucher benötigen keine SQLite-Details | Portable IDs/hashes/`ref` throughout; Section 13 explicit portability contract. |
| Schema ist versionierbar | SemVer `schema_version` with MAJOR/MINOR/PATCH rules (Section 3). |

---

## 16. Related Documents

- [Track Map v1](TRACK_MAP_V1.md) (#232 / #227) — track identity, timebase, sections, provenance registry. Current `1.0.0`.
- [Asset Manifest v1](ASSET_MANIFEST_V1.md) (#250 / #230) — loop/section asset contract. Current `1.1.0`.
- [Canonical Audio & Timebase](CANON_AUDIO_TIMEBASE.md) (#234) — authoritative sample timebase.
- Arrangement Map (#228 / #238–#243) — referenced via `documents.arrangement`; contract finalized separately.
- Stem Manifest (#229 / #244–#249) — referenced via `documents.stem_manifest` / `stems`; contract finalized separately.
- Standard pack directory and file naming (#258) — defines the relative-URI layout the pack `ref` fields assume.
- Song to Sample / Performance Pack meta (#231) — parent issue and downstream aggregation scope.

---

## 17. Non-Goals (v1)

- No pack directory/file naming implementation (#258).
- No headless orchestrator (#259), runtime integration (#260), stem runtime (#261), resume/cache (#262), re-import (#263), or end-to-end pilot (#264).
- No stem separation, producer-group generation (#268), new audio analysis, or new dependencies.
- No SQLite schema or migration.
- No private tracks, samples, stems, or paths in the contract or its examples.
- The pack does **not** embed Track Map / Arrangement / Asset / Stem bodies; it references them.
