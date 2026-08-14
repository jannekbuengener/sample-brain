# Technical Stem Manifest v1 — Canonical Contract

**Issue:** [#244](https://github.com/jannekbuengener/sample-brain/issues/244)
**Parent:** [#229](https://github.com/jannekbuengener/sample-brain/issues/229) — Stem Separation for Track Deconstruction
**Status on issue tracker:** `OPEN` / documented on `main`
**Schema version:** `1.0.0`
**Document type:** `sample_brain.stem_manifest`

This document defines the canonical, portable **Technical Stem Manifest v1** contract for Sample Brain. It defines how a single separated technical stem is described, bounded, and traced back to its original track — without installing models or executing separations in this contract slice.

---

## 1. Purpose

Technical stems are raw separation outputs (e.g. drums, bass, vocals, other). They serve as the raw materials for downstream producer-oriented assets (loops, sections, producer groups). They are distinct from producer groups (#268).

The Technical Stem Manifest is a **separate document** from the Track Map (#232), the Arrangement Map (#228), the Asset Manifest (#250), and the Performance Pack Manifest (#257). It describes **one single technical stem** (e.g. the drums stem or the bass stem of a track) to allow robust, parallel, and optional stem extraction.

---

## 2. Design Principles

| Principle | Rule |
|-----------|------|
| **Model Independence** | The contract is completely independent of the separation backend (e.g. `demucs`, `python-audio-separator`). No default model is prescribed. |
| **Standard Kinds** | The standard technical stem vocabulary for v1 is strictly `"drums"`, `"bass"`, `"vocals"`, and `"other"`. Additional technical stem classes remain additively possible in later schema versions. |
| **Track Identity & Portability** | Stems reference the original track via `track_ref` (portable track ID/content-hash). Absolute filesystem paths, local DB row IDs, UNC paths, `file://` URLs, and `..` traversals are rejected. |
| **Source Timebase Traceability** | The separated stem must be sample-accurately traceable to the original track. The manifest stores the exact separation-input details (original or working audio, hash, sample rate, channels, sample length) and starts at sample `0`. |
| **Separated Provenance & Lizenzen** | Full model, checkpoint, and license provenance are mandatory for attempted runs. Code license and weight/checkpoint license are getrennte (separate) fields and must never be merged. |
| **Status Transparency** | Every stem manifest reports its status: `ok`, `partial`, `not_run`, `no_result`, or `failed`. Missing optional results are never fabricated. |
| **Technical Quality, No Taste** | Quality notes indicate technical anomalies (e.g. `LENGTH_MISMATCH`, `CHANNEL_MISMATCH`). Musical/subjective judgments like "good bass" or "producer ready" are forbidden. |

---

## 3. Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `document_type` | string | yes | Must be `"sample_brain.stem_manifest"`. |
| `schema_version` | string | yes | SemVer matching `MAJOR.MINOR.PATCH`. This canonical revision is `"1.0.0"`. |
| `stem_id` | string | yes | Portable, deterministic stem identifier (e.g., `stem_drums_01`). No timestamps, no random UUIDs, no local database IDs. |
| `stem_kind` | string | yes | Must be one of: `"drums"`, `"bass"`, `"vocals"`, `"other"`. |
| `track_ref` | string | yes | Portable Track ID (content hash of the original track). Identifies the track this stem belongs to. |
| `status` | string | yes | Stem status: `"ok"`, `"partial"`, `"not_run"`, `"no_result"`, or `"failed"`. |
| `source` | object | yes | Source audio and timebase details of the separation input (Section 4). |
| `provenance` | object | yes | Centralized component, model, checkpoint, and license metadata (Section 6). |
| `output` | object | conditional | Required when status is `"ok"` or `"partial"`. Describes the output stem audio (Section 5). Absent otherwise. |
| `reason_code` | string | conditional | Required when status is `"not_run"` or `"no_result"`. Absent otherwise (Section 7). |
| `error` | object | conditional | Required when status is `"failed"`. Describes the failure (Section 7). Absent otherwise. |
| `quality` | object | yes | Quality notes container (Section 8). Required (may be empty). |

---

## 4. Source Identity & Timebase Traceability

To ensure sample-accurate alignment, the stem manifest contains full details of the audio that was separated.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source.audio_ref` | string | yes | JSON Pointer referencing the track audio, typically `"/source/original"` or `"/source/working_audio"`. |
| `source.hash` | object | yes | Content hash of the separation input: `{ "algorithm": string, "value": string }`. |
| `source.audio_properties` | object | yes | Audio properties of the input. |
| `source.audio_properties.sample_rate_hz` | integer | yes | Input sample rate in Hz. Must be positive. |
| `source.audio_properties.channels` | integer | yes | Input channel count. Must be positive. |
| `source.audio_properties.n_samples` | integer | yes | Exact input length in samples. Must be positive. |
| `source.audio_properties.duration_sec` | number | no | Optional derived duration in seconds (float). |
| `source.origin_sample` | integer | yes | Must be `0`. Separation always starts at the absolute beginning of the input audio. |

---

## 5. Output Contract

Required when `status` is `"ok"` or `"partial"`. Describes the generated technical stem audio.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `output.file_ref` | string | yes | **Portable, relative** reference to the rendered stem audio file (relative to this manifest file). |
| `output.hash` | object | yes | Content hash of the output audio file: `{ "algorithm": string, "value": string }`. |
| `output.audio_properties` | object | yes | Audio properties of the output. |
| `output.audio_properties.sample_rate_hz` | integer | yes | Output sample rate in Hz. Must be positive. |
| `output.audio_properties.channels` | integer | yes | Output channel count. Must be positive. |
| `output.audio_properties.n_samples` | integer | yes | Exact output length in samples. Must be positive. |
| `output.audio_properties.duration_sec` | number | no | Optional derived duration in seconds (float). |

### Portability Rules for `file_ref`
The `file_ref` must be portable. The following are strictly **rejected**:
*   Absolute Windows paths (e.g. `C:\stems\drums.wav`)
*   Absolute POSIX paths (e.g. `/var/stems/drums.wav`)
*   UNC paths (e.g. `\\server\share\drums.wav`)
*   `file://` URLs (e.g. `file:///stems/drums.wav`)
*   `..` path traversal (e.g. `../outside/drums.wav`)
*   Private worktree/cache paths

---

## 6. Provenance Contract

Every attempted run must document what was actually used. No fictional model or checkpoint details are allowed when `status == "not_run"`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `provenance.component` | string | yes | Name of the separation component (e.g., `"stem_separator"`). |
| `provenance.sample_brain_version` | string | yes | Version of the sample-brain tool. |
| `provenance.backend` | object | no | Optional wrapper details (e.g., name and version of `python-audio-separator`). |
| `provenance.backend.name` | string | yes | Name of the backend/wrapper. |
| `provenance.backend.version` | string | yes | Version of the backend/wrapper. |
| `provenance.model` | object | conditional | Required for attempted runs. Describes the separation model. |
| `provenance.model.family` | string | yes | Model family / architecture (e.g., `"htdemucs"`). |
| `provenance.model.name` | string | yes | Concrete model identifier (e.g., `"htdemucs_ft"`). |
| `provenance.model.checkpoint` | string | yes | Exact checkpoint/revision identifier. |
| `provenance.model.weight_hash` | object | yes | Hash of the model weights: `{ "algorithm": string, "value": string }`. |
| `provenance.model.code_license` | string | yes | License of the source code (e.g. `"MIT"`, `"GPL-3.0"`). |
| `provenance.model.weight_license` | string | yes | License of the model weights/checkpoint (e.g. `"CC-BY-NC-4.0"`). |
| `provenance.configuration` | object | yes | Separation parameters actually used (e.g., `{ "overlap": 0.25 }`). Use `{}` if none. |

### Hard Rule on Licenses
The code license (`code_license`) and the weights/checkpoint license (`weight_license`) are two distinct fields. They must **never** be merged into a single field.

---

## 7. Status Model & Failure/Skip Contracts

### `status` Values

*   `ok`: Stem was successfully created and matches the timebase. `output` is required.
*   `partial`: Stem exists and is technically usable, but has documented limitations. `output` is required.
*   `not_run`: Stem was deliberately skipped or could not start. `reason_code` is required; `output` is forbidden.
*   `no_result`: Separation ran successfully but produced no usable stem. `reason_code` is required; `output` is forbidden.
*   `failed`: Separation was attempted but crashed/errored. `error` is required; `output` is forbidden.

### `reason_code` (Required for `not_run`, `no_result`)
Must be a stable machine-readable string, such as:
*   `STEM_NOT_REQUESTED`
*   `BACKEND_UNAVAILABLE`
*   `MODEL_UNAVAILABLE`
*   `SILENT_INPUT_SKIPPED`
*   `EMPTY_STEM_OUTPUT`

### `error` Object (Required for `failed`)
*   `error.code` (string): Stable error code.
*   `error.message` (string): Human-readable error message.
*   `error.retryable` (boolean): Optional flag indicating if retrying might succeed.

---

## 8. Quality Notes Contract

Quality notes indicate technical properties and processing anomalies. Subjective musical quality ratings are strictly forbidden.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `quality.notes` | array | yes | Array of quality notes (may be empty). |
| `quality.notes[].code` | string | yes | Stable code: `"LENGTH_MISMATCH"`, `"CHANNEL_MISMATCH"`, `"PARTIAL_OUTPUT"`, `"BACKEND_WARNING"`. |
| `quality.notes[].severity` | string | yes | `"info"`, `"warning"`, or `"error"`. |
| `quality.notes[].path` | string | yes | JSON Pointer to the affected field (e.g., `"/output"`). |
| `quality.notes[].message` | string | yes | Human-readable message. |

---

## 9. JSON Example (Drums Stem, Status OK)

This is a valid, portable Technical Stem Manifest.

```json
{
  "document_type": "sample_brain.stem_manifest",
  "schema_version": "1.0.0",
  "stem_id": "stem_drums_01",
  "stem_kind": "drums",
  "track_ref": "9f8e7d6c5b4a3c2d1e0f11223344556677889900",
  "status": "ok",
  "source": {
    "audio_ref": "/source/original",
    "hash": {
      "algorithm": "sha1",
      "value": "9f8e7d6c5b4a3c2d1e0f11223344556677889900"
    },
    "audio_properties": {
      "sample_rate_hz": 44100,
      "channels": 2,
      "n_samples": 10584000,
      "duration_sec": 240.0
    },
    "origin_sample": 0
  },
  "output": {
    "file_ref": "stem_drums_01.wav",
    "hash": {
      "algorithm": "sha1",
      "value": "ee55ff6677889900aabbcceedff1122334455667"
    },
    "audio_properties": {
      "sample_rate_hz": 44100,
      "channels": 2,
      "n_samples": 10584000,
      "duration_sec": 240.0
    }
  },
  "provenance": {
    "component": "stem_separator",
    "sample_brain_version": "0.9.0",
    "backend": {
      "name": "python-audio-separator",
      "version": "0.15.1"
    },
    "model": {
      "family": "htdemucs",
      "name": "htdemucs_ft",
      "checkpoint": "htdemucs_ft_v4",
      "weight_hash": {
        "algorithm": "sha1",
        "value": "11223344556677889900aabbccddeeff00112233"
      },
      "code_license": "MIT",
      "weight_license": "CC-BY-NC-4.0"
    },
    "configuration": {
      "overlap": 0.25,
      "segment": 10
    }
  },
  "quality": {
    "notes": []
  }
}
```
