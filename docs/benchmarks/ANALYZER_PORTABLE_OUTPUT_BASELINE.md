# Analyzer Portable Output Baseline (#960)

Parent: [#950](https://github.com/jannekbuengener/sample-brain/issues/950) (AQ8) · Program: [#942](https://github.com/jannekbuengener/sample-brain/issues/942) · Feeds: [#956](https://github.com/jannekbuengener/sample-brain/issues/956)

**Status:** audited baseline (audit + protection only). Not the #956 artifact contract.
**Method:** synthetic/public fixtures + code-contract inspection on `origin/main` at audit time.
**Helper:** `src/portable_analyzer_projection.py` (fail-closed JSON projection seam).
**Curated evidence:** `evidence/analyzer_portable_output_baseline_20261006.json`

## 1. Purpose

Establish which current analyzer/result surfaces can safely project into portable
benchmark evidence before #956 freezes a shared artifact/status/provenance contract.

This slice does **not** tune algorithms, change thresholds, implement ARVP core,
or repair independent analyzer bugs beyond the smallest serialization/protection
guards required for a reproducible baseline.

## 2. Classification taxonomy

| Class | Meaning |
|-------|---------|
| `PASS_EXISTING_CONTRACT` | Already fail-closed / portable-safe at the inspected seam |
| `KNOWN_DOMAIN_SEMANTIC` | Valid domain behavior; #956 or owning AQ must map status/semantics explicitly |
| `DEFECT_IN_SCOPE_TO_PROTECT` | Smallest regression protection defined in this slice |
| `INDEPENDENT_REPAIR_REQUIRED` | Follow-up owned by the analyzer/module; not silently fixed here |

## 3. Surface inventory (AQ1–AQ7 relevant)

| Surface | Public modules / seams | Portable projection notes |
|---------|------------------------|---------------------------|
| BPM / BeatGrid | `src/analyze.py` (`Features.bpm`, `normalize_bpm`), `src/beat_grid.py` (`BeatGridSeries`/`BeatGridResult.as_dict`) | BPM may be `None` (unknown). BeatGrid rejects non-finite times at construction. |
| Key / Mode / Tonality | `src/analyze.py` (`estimate_key`, `estimate_key_mode`, `Features.key*`), `src/key_analysis_v2.py`, `src/joint_key_profile_benchmark.py`, `src/fsld_current_analyzer_eval.py` | V2/FSLD/cache use `allow_nan=False`. V1 `key_mode_evidence` serialization is protected in this slice. |
| Onset / Gesture | `src/gesture_analysis.py` (`GestureAnalysis`, `GestureEvent`) | Fail-soft zeros for non-finite window features; portable evidence must carry explicit status, not treat zero as measured. |
| Classification / Type / Tags | `src/classify.py` (`pred_type`), sample tags via `src/db.py` | String labels; portable when no private path/filename is embedded. |
| Search / Ranking | `src/search.py`, `src/index.py`, `src/hybrid_rank.py` | Scores are floats; CLI/runtime hits expose absolute `path` — **not** portable evidence fields. |
| Harmonic Match | `src/workbench_harmony.py` (`HarmonySuggestion`, relation scores) | Relation/scores are in-memory product results; portable export must omit row paths and require finite scores. |
| Structure / Arrangement | `src/structure_v1.py` (`StructureV1Result.as_dict`), deconstruct Track Map writers | Explicit `status` / `reason_code` (`ok`/`partial`/`no_result`/`failed`). Non-finite audio fails closed. |
| Loudness / Brightness / MFCC / Chroma | `src/analyze.py` `Features` blobs + scalars | Scalars use `None` for failure. MFCC/chroma are float32 byte blobs (shape 13/12 on happy path); portable decode must require finite vectors. |
| Shared eval / cache seams | `src/fsld_current_analyzer_eval.py`, `src/track_analysis_cache.py`, `src/db.py` V2 evidence | Canonical JSON with `allow_nan=False` (except historical gaps closed below). |

## 4. Findings (measured / inspected)

| ID | Finding | Class | Owner / routing |
|----|---------|-------|-----------------|
| F1 | `BeatGridSeries` rejects non-finite `times_sec` | `PASS_EXISTING_CONTRACT` | `src/beat_grid.py` |
| F2 | `structure_v1` fails closed on non-finite audio; status/reason_code distinguish no-result | `PASS_EXISTING_CONTRACT` | `src/structure_v1.py` |
| F3 | FSLD current-analyzer eval + joint-key benchmark + track-analysis cache serialize with `allow_nan=False` | `PASS_EXISTING_CONTRACT` | eval/cache modules |
| F4 | Key V2 evidence serialization uses `allow_nan=False` | `PASS_EXISTING_CONTRACT` | `src/key_analysis_v2.py`, `src/db.py` |
| F5 | V1 `_serialize_key_mode_evidence` accepted `NaN` under default `json.dumps` (`allow_nan=True`) | `DEFECT_IN_SCOPE_TO_PROTECT` | fixed: `allow_nan=False` + projection helper tests |
| F6 | Gesture feature extraction coerces non-finite dims to `0.0` (documented fail-soft) | `KNOWN_DOMAIN_SEMANTIC` | #956 must not treat bare zeros as measured success; gesture AQ owns semantics |
| F7 | Silent synthetic audio can still emit a tonal root (`key='C'`) with `bpm=None` | `INDEPENDENT_REPAIR_REQUIRED` | key/analyzer quality epics under #942/#950 — do not coerce in #960 |
| F8 | `SearchHit.path` / CLI search printing absolute local paths | `KNOWN_DOMAIN_SEMANTIC` | runtime UX OK; portable evidence must use public ids/hashes only (#956) |
| F9 | MFCC/chroma blobs are raw bytes without an explicit portable status wrapper | `KNOWN_DOMAIN_SEMANTIC` | #956 mapping: decode + finite check or omit; helper provides finite-vector check |
| F10 | Harmonic-match suggestions are not a versioned portable artifact today | `KNOWN_DOMAIN_SEMANTIC` | #956 inventory only; no ARVP core here |
| F11 | Shared projection helper was missing (each eval reimplemented JSON rules) | `DEFECT_IN_SCOPE_TO_PROTECT` | `src/portable_analyzer_projection.py` |

## 5. #956 mapping inventory (safe / unsafe)

| Value class | Portable? | Required artifact semantics (#956) |
|-------------|-----------|------------------------------------|
| Finite JSON number / bool / string / null | Yes | Direct field |
| `None` analyzer miss (`bpm`, `key_mode`, loudness, …) | Yes as `null` + explicit status/eligibility | Must not become `0` |
| Non-finite float (`NaN`/`±Inf`) | No | Reject at projection; preserve failure/unknown status |
| `numpy` arrays / `Path` / `bytes` / sets | No as raw objects | Encode only via declared codecs (e.g. finite float list, content hash) |
| Absolute paths, usernames, private filenames | No | Forbidden in curated evidence (`tests/test_evidence_policy.py`) |
| Gesture/search zero scores without status | Ambiguous | Require status enum; zero alone is not “measured ok” |
| Structure/BeatGrid status enums | Yes | Carry `status` + optional `reason_code` unchanged |

ARVP boundary: ARVP receives already-safe portable values. Sample Brain owns
sanitization/projection. ARVP #7 (typed metrics) is CLOSED; #11/#12 remain OPEN
and are **not** implemented here.

## 6. Reproduction (synthetic only)

```powershell
python -m pytest -q tests/test_portable_analyzer_projection.py
```

Do not scan private sample libraries. Do not commit audio, DB, or cache files.

## 7. Exit

`ANALYZER_PORTABLE_OUTPUT_BASELINE_AUDITED`
