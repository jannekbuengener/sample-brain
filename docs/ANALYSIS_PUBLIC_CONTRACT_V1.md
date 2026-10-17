# Analysis Public Contract v1

**Status:** ACTIVE_SUPPORTING
**Issue:** #1148
**Code owner:** `src/analysis_contracts.py`

## Purpose

Freeze the smallest neutral contract shared by Sample Brain analysis computation before package extraction. This contract is intentionally narrower than a global `AnalysisConfig`: application/profile/session/persistence state is not Analysis input merely because callers already have it available.

## Shared analysis authority

`src/analysis_contracts.py` is the canonical owner of the shared values/types below:

| Contract | v1 semantics |
|---|---|
| `ANALYZE_SR` | `44100` Hz feature-analysis target sample rate |
| `ANALYZE_HOP_LENGTH` | `512` samples |
| `BPMNormalizationMode` | `none \| heuristic \| domain_110_170` |
| `VALID_BPM_NORMALIZATION_MODES` | exact frozen set of the three modes above |
| `Features` | immutable neutral feature-analysis result |

`src.config` may re-export analyzer constants for compatibility, but it is not their semantic owner. Profile/config loading may validate and adapt user/runtime choices into these narrow Analysis inputs; it must not create a second vocabulary authority.

## `Features` v1

`Features` remains a frozen value object with these fields and meanings:

| Field | Type / meaning |
|---|---|
| `bpm` | detected/normalized BPM or `None` |
| `key` | canonical key string or `None` |
| `key_conf` | relative root evidence, not calibrated probability |
| `loudness` | global RMS dBFS or `None` |
| `brightness` | mean spectral centroid Hz or `None` |
| `mfcc_mean` / `mfcc_std` | serialized float32 MFCC aggregates or `None` |
| `chroma_mean` / `chroma_std` | serialized float32 chroma aggregates or `None` |
| `clazz` | duration-derived `oneshot` / `loop` or `None` |
| `quality_note` | optional quality warning text |
| `key_mode` | `maj` / `min` / `None` |
| `key_mode_evidence` | optional structured mode evidence |

Existing callers may continue importing `Features` through `src.analyze`; that surface is a compatibility re-export of the neutral owner.

## Dependency direction

```text
application config / CLI / Workbench
             |
             | adapt explicit values
             v
      analysis_contracts
             |
             v
   analysis computation
             |
             v
     neutral result values
```

The neutral shared contract must not import or accept as public domain inputs:

- `src.config` / profile resolution;
- `src.db`, SQLAlchemy engines/connections/rows, or catalog sessions;
- Workbench rows/controllers/session state;
- QML/PySide6 types;
- product document/cache state;
- machine-local paths other than explicit audio-file inputs supplied by callers.

## No global `AnalysisConfig`

There is no v1 mega configuration object. Attack, harmony, gesture, key and other domains keep their narrow explicit parameters and domain-local DTOs unless a real shared contract is proven later.

The following remain domain-local rather than being centralized for appearance:

- `AttackSuggestion`;
- `HarmonyInput` / `HarmonySuggestion`;
- `ParsedKey`;
- `GestureEvent` / `GestureAnalysis`;
- product-adapter results such as `AssetAnalysisResult` and Track Map documents.

## Current orchestration boundary

This slice does **not** claim that `src.analyze.py` is already a package-ready module. On current `main`, `extract_features` consumes the neutral contract, while `run_analyze` still owns catalog batching/upsert/progress behavior. Likewise classification and key-v2 modules still mix computation with persistence/orchestration in places.

Issue #1149 owns that next decoupling. SQLite/catalog persistence remains one Sample Brain application authority; no second Analysis database or state store is introduced.

## Compatibility requirements

For v1:

- `src.config.ANALYZE_SR == 44100` and `ANALYZE_HOP_LENGTH == 512` remain compatible re-exports;
- the accepted BPM-normalization modes and invalid-mode rejection behavior remain unchanged;
- `src.analyze.Features` is the same type object as `src.analysis_contracts.Features`;
- analyzer algorithms, thresholds, cache fingerprints and failure semantics are unchanged by this ownership move;
- offline-first behavior remains unchanged.

## Validation

Primary machine checks:

- `tests/test_analysis_public_contract.py` — constants, modes, `Features`, compatibility aliases;
- `tests/test_analysis_contract_boundary.py` — product/application-free contract closure and removal of application-config ownership from package-candidate modules;
- existing config/analyze/canonical-audio/gesture/cache/key/harmony regression tests — behavior parity.

This contract is normative for the shared Analysis config/result seam. Execution history, base SHAs and migration steps remain in Issue/PR evidence rather than this document.
