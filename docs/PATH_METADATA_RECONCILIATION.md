# Path Metadata Pre-Pass & Evidence Reconciliation

**Status:** ACTIVE_SUPPORTING  
**Module:** `src/path_metadata.py`  
**Schema:** `path_metadata_claims`, `metadata_resolutions` in `src/db.py`

## Purpose

Deterministic, offline extraction of explicit metadata claims from sample
filenames and relative folder paths, followed by field-by-field reconciliation
against independent audio analysis and autotype evidence.

```text
filename/path evidence
        +
audio / classifier evidence
        ↓
deterministic reconciliation
        ↓
resolved metadata + explicit provenance
```

This is not an ML feature. No cloud or LLM dependency is introduced.

## Pipeline

```text
scan → path metadata pre-pass → analyze → autotype → reconcile → resolved catalog metadata
```

- The pre-pass runs on path strings only (no audio decoding).
- Reconciliation runs only after analyzer/classifier evidence is available.
- Filename claims never cause audio analysis to be skipped.

CLI:

- Implicit: pre-pass after `scan`; reconcile after `autotype`.
- Explicit: `metadata_parse`, `metadata_reconcile`.

## Claim fields

| Field | Path evidence | Analysis evidence |
|-------|---------------|-------------------|
| `bpm` | Explicit `NNN BPM` / `NNNbpm` tokens only | `features.bpm` |
| `key` | Modeful key tokens via `src/key_signature.py` | `features.key` / mode |
| `sample_class` | `loop` / `oneshot` word forms | `features.class` |
| `pred_type` | Configured instrument taxonomy tokens | `features.pred_type` |
| `genre` | Configured genre vocabulary | none (V1) |

Fail closed on ambiguous input (`sample_132_v3.wav`, `Bass_A.wav`, bare numbers).
Malformed paths never block scan or analyze.

## Provenance model

Every claim retains:

| Attribute | Meaning |
|-----------|---------|
| `field` | Claim field name |
| `normalized_value` | Canonical value |
| `source` | `filename` \| `folder` (claims); analysis side uses `audio` / `autotype` |
| `raw_evidence` | Matched substring / token |
| `parser_version` | `PATH_METADATA_PARSER_VERSION` |
| `path_fingerprint` | Hash of path identity used for parse |

## Persistence

### `path_metadata_claims`

Stores declarative path evidence only. Unique on
`(sample_id, field, source, normalized_value)` so genre (and similar multi-value
fields) may keep multiple values from the same source.

### `metadata_resolutions`

One row per `(sample_id, field)`. Stores reconciliation outcome:

- `resolution_status`
- `resolved_value` (nullable)
- `filename_value`, `analysis_value`
- `provenance_note`
- `parser_version`, `reconciled_at`

### Invariant

**Never** overwrite `features.bpm`, key-analysis columns, `features.class`, or
`features.pred_type` with filename values. Those columns remain analyzer /
classifier measurements for quality evaluation and conflict diagnosis.

Genre (and optional declared keywords) may also appear in `sample_tags` with
`source=filename` / `source=folder` for search. Path-derived tags are not
playback/runtime authority for Channel Rack / Live Kit.

## Resolution statuses

| Status | Meaning |
|--------|---------|
| `CONFIRMED` | Path and analysis agree after normalization |
| `COMPATIBLE` | Known half/double BPM relationship |
| `PARTIAL` | Partial agreement (e.g. key root only; mode unresolved) |
| `CONFLICT` | Hard disagreement; `resolved_value` is NULL |
| `DECLARED_ONLY` | Path claim with no independent analyzer (e.g. genre) |
| `ANALYSIS_ONLY` | No path claim; analysis value used |
| `UNKNOWN` | Neither side provides a value |

### Resolution value policy

| Case | `resolved_value` |
|------|------------------|
| `CONFIRMED` / `COMPATIBLE` | Normalized filename/path claim |
| `PARTIAL` (key root, mode unknown on analysis) | Root-only canonical key; mode remains unresolved in note |
| `CONFLICT` | `NULL` (both sides retained on the row) |
| `DECLARED_ONLY` | Path declaration |
| `ANALYSIS_ONLY` | Analysis value |
| `UNKNOWN` | `NULL` |

BPM agreement uses producer-facing rounding (`src/bpm_display.round_bpm_display`)
and half/double classification via `src/bpm_evidence.classify_bpm_error`.
Key comparison uses `parse_key_signature` / `is_same_root` / `is_same_mode`
after enharmonic normalization.

## Invalidation

Path claims depend on filename/path identity, not only content hash.

- `path_fingerprint` is derived from basename + `relpath`.
- Rename or path change invalidates / recomputes path claims even when
  `samples.hash` is unchanged.
- Analyzer evidence follows its own existing source/contract invalidation rules.

## Non-goals

- LLM / free-text semantic guessing
- Cloud metadata services
- Automatic file rename or audio modification
- New genre classifier
- Replacing BPM/key analyzers or AQ evaluation infrastructure
- Collapsing analyzer evidence and resolved metadata into one opaque value
- Granting path claims playback/runtime authority

## Related docs

- [`docs/TITLE_RULES.md`](TITLE_RULES.md) — title format; declarative evidence policy
- [`docs/product/01_LIBRARY_INTELLIGENCE_SPEC.md`](product/01_LIBRARY_INTELLIGENCE_SPEC.md)
- [`docs/KEY_MODE_ANALYSIS_V1.md`](KEY_MODE_ANALYSIS_V1.md)
- `src/key_signature.py`, `src/bpm_display.py`, `src/bpm_evidence.py`
