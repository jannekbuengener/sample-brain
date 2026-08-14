# Asset Reanalysis v1 — Canonical Contract

**Issue:** [#254](https://github.com/jannekbuengener/sample-brain/issues/254)
**Parent:** [#230](https://github.com/jannekbuengener/sample-brain/issues/230)
**Depends on:** [#250](https://github.com/jannekbuengener/sample-brain/issues/250) (Asset Manifest v1), [#253](https://github.com/jannekbuengener/sample-brain/issues/253) (deterministic rendering)
**Status on issue tracker:** `OPEN`
**Schema relationship:** establishes `1.1.0` — an additive MINOR extension of `ASSET_MANIFEST_V1.md` `1.0.0` (a compatible `1.x` addendum). It raises the frozen `schema_version` from `1.0.0` to `1.1.0` per the manifest's own MINOR rule for new optional fields.

This document defines the lightweight reanalysis of already rendered loop and
section assets (#253) and how the resulting metadata is attached to the Asset
Manifest v1 `analysis` block. It deliberately stays inside the #254 scope:
no heavy track/stem analysis, no model/embedding, no DB, no network, no invented
confidence, and no invented mode.

---

## 1. Purpose

Rendered assets carry sample-accurate identity and render provenance, but no
musical/technical metadata yet. Reanalysis attaches consistent, portable
Sample-Brain metadata so the assets are usable in the Performance Pack and later
in Sample Brain without re-running heavy analysis on every short asset.

---

## 2. Design Principles (inherit from #250)

| Principle | Rule |
|-----------|------|
| **Local-first / offline-first** | Pure local computation. No DB, network, model download, or embedding. |
| **Lightweight only** | Reuse `analyze.extract_features()` (librosa-based, rules-only) and `classify.rule_type()` (rules-only, no kNN/CLAP). No second BPM/key analyzer, no second renderer, no Track Map regeneration. |
| **Status transparency** | Every result carries a status (`ok` / `partial` / `not_run` / `failed` / `no_result`). Missing optional values are never fabricated. |
| **No invented confidence** | No generic `confidence`. No BPM-confidence. No invented Dur/Moll mode. `key_root` is a root pitch class only. |
| **Source integrity gate** | Before analysis, the render output is verified against the manifest (status, portable `file_ref`, existence, hash, audio properties). Fail-closed on any mismatch. |
| **Provenance per asset** | The analysis records its component, version, backend, config, and a reference to the actually analyzed render output. |
| **Additive evolution** | New analysis fields extend the manifest (added at `1.1.0`) without reinterpreting existing fields. `schema_version` is raised to `1.1.0` (MINOR); v1 consumers accept `1.x`. |

---

## 3. Entry Points

`src/asset_analysis.py` exposes three functions:

| Function | Purpose |
|----------|---------|
| `reanalyze_rendered_output(output, audio_root, ...)` | Verify a `rendering.output` block against the file on disk and produce analysis metadata. Core integrity + feature step. |
| `analyze_rendered_asset(manifest, audio_root, ...)` | Validate the Asset Manifest, then call the output-level step. |
| `attach_rendered_asset_analysis(manifest, audio_root, ...)` | Return a **new** manifest dict with the `analysis` block and `provenance.components` entry merged in. Never mutates unrelated blocks. |

`audio_root` is the base directory the portable `file_ref` is resolved against
(typically the directory that contains the `assets/` folder produced by #253).

---

## 4. Analysis Fields

All analysis fields are **optional** and only present when a meaningful value
was produced. Missing values are represented by their non-`ok` status, never by
a fabricated number.

| Field | Type | Meaning |
|-------|------|---------|
| `bpm` | number | Tempo in BPM from `extract_features` (no heuristic doubling invented; `bpm_normalization="none"`). `None` for short clips. |
| `key_root` | string | Estimated tonal root pitch class (`C`, `C#`, ..., `B`). **Root only — no mode is inferred or stored.** |
| `sample_type` | string | Lightweight rules-only type from `classify.rule_type()` (e.g. `Loop`, `Drum Loop`, `Drone`, `Bright`). No kNN/CLAP. |
| `loudness` | number | RMS-based loudness in dBFS from `extract_features`. |
| `brightness` | number | Spectral centroid (Hz) from `extract_features`. |

The `analysis` block also carries:

| Field | Type | Meaning |
|-------|------|---------|
| `status` | string | `ok` / `partial` / `not_run` / `failed` / `no_result`. |
| `components` | array | Component IDs that produced this analysis (always `["comp_asset_analyzer"]`). |
| `source_ref` | string | Key into `provenance.components` (`"comp_asset_analyzer"`). |
| `analyzed_output` | object | Reference to the actually analyzed render output: `{file_ref, hash, audio_properties}` (verified during the integrity gate). |
| `config` | object | Analyzer config used (no secrets): `bpm_normalization`, `short_clip`, `duration_sec`. |
| `reason_code` | string | Only for `not_run` / `no_result`. |
| `error` | object | Only for `failed`: `{code, message}` (see §6). |

### Status model

| Status | Meaning | Required extra fields |
|--------|---------|----------------------|
| `ok` | BPM, key_root, sample_type, loudness, and brightness all present. | `source_ref`, analysis fields. |
| `partial` | Analysis ran, at least one value present, but BPM or key_root missing (e.g. short clip). | `source_ref`, present analysis fields, `reason_code` (e.g. `PARTIAL_MISSING_BPM_KEY`). |
| `not_run` | Asset not rendered, or render output absent. No data invented. | `reason_code` (`ASSET_NOT_RENDERED` / `RENDERING_BLOCK_MISSING`). |
| `failed` | Integrity gate or audio load failed. | `error.code`, `error.message`, `source_ref`. |
| `no_result` | Analysis ran but no meaningful value was produced (e.g. silent asset). | `reason_code` (`NO_MEANINGFUL_ANALYSIS`), `source_ref`. |

---

## 5. Source Integrity Gate (before analysis)

Run in order. Any failure is fail-closed (`failed` with a stable code).

1. **Manifest version** — `schema_version` major must be `1`. Any other major (or missing version) → `failed` / `UNSUPPORTED_MANIFEST_VERSION`.
2. **Render status** — `rendering.status` must be `rendered`. Otherwise → `not_run` (`ASSET_NOT_RENDERED`).
3. **Portable `file_ref`** — must be relative and must not be absolute and must not contain `..` traversal. Otherwise → `failed` / `INVALID_ASSET_FILE_REF`.
4. **Existence** — the resolved file must exist. Otherwise → `failed` / `RENDERED_ASSET_NOT_FOUND`.
5. **Hash check** — the actual file hash must equal `output.hash.value`. Otherwise → `failed` / `RENDERED_ASSET_HASH_MISMATCH`.
6. **Audio properties** — actual sample rate / channels / n_samples must match `output.audio_properties`. Otherwise → `failed` / `RENDERED_ASSET_PROPS_MISMATCH`.
7. **Load** — features must be extractable. Otherwise → `failed` / `AUDIO_LOAD_FAILED`.

Fail-closed codes: `UNSUPPORTED_MANIFEST_VERSION`, `INVALID_ASSET_FILE_REF`,
`RENDERED_ASSET_NOT_FOUND`, `RENDERED_ASSET_HASH_MISMATCH`,
`RENDERED_ASSET_PROPS_MISMATCH`, `AUDIO_LOAD_FAILED`.

---

## 6. Provenance

The analysis registers one component in the centralized `provenance.components`
registry (compatible with #250 §13):

```json
{
  "comp_asset_analyzer": {
    "component": "asset_analyzer",
    "sample_brain_version": "0.1.0",
    "backend": { "name": "librosa", "version": "0.10.x" },
    "configuration": {
      "bpm_normalization": "none",
      "short_clip": false,
      "duration_sec": 8.0
    }
  }
}
```

`analysis.source_ref` points at `comp_asset_analyzer`. No secrets, no private
paths, no model-cache paths are ever stored.

---

## 7. Invariants (acceptance criteria mapping)

| #254 criterion | This document |
|----------------|---------------|
| Loops/Sections get consistent metadata | §4 fields apply identically to `asset_kind=loop` and `asset_kind=section`. |
| Missing/uncertain values stay status-based | §4 status model; never fabricated. |
| Parent/Source/Producer-Group refs preserved | `attach_*` merges only `analysis` + `provenance`; `source`, `range`, `loop`/`section`, `boundary`, `candidate`, `rendering`, `track_ref` untouched. |
| No unnecessary heavy model runs | §2 lightweight-only; reuses existing `extract_features` / `rule_type`. |
| Outputs ready for pack / re-import | `analyzed_output` reference + portable `file_ref`; no absolute paths. |
| `asset_kind` / `source_kind` preserved | Not reinterpreted by analysis. |
| No invented confidence / mode / BPM-confidence | §2. |

---

## 8. Non-Goals (v1)

- No stem separation, no `#268` producer groups implementation, no `#255` stem candidates.
- No `#256` techno quality pilot.
- No performance-pack assembly (`#257`+).
- No CLAP / embeddings / network / model download.
- No DB schema or migration; no new CLI command required for #254.
- No invented confidence, mode, or BPM-confidence.

---

## 9. Relationship to `ASSET_MANIFEST_V1.md`

This is an **additive** `1.x` extension. `ASSET_MANIFEST_V1.md` §12 is updated to
describe the reanalysis fields; `schema_version` is `1.1.0`. Readers that
accept compatible `1.x.x` documents consume the new `analysis` fields without
change.
