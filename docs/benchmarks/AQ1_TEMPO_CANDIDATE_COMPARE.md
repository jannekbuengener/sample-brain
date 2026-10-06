# AQ1 Tempo Candidate Comparison (FSLD)

**Status:** ACTIVE_SUPPORTING — reproducible candidate comparison for [#977](https://github.com/jannekbuengener/sample-brain/issues/977)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#943](https://github.com/jannekbuengener/sample-brain/issues/943) (AQ1), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on:** [#973](https://github.com/jannekbuengener/sample-brain/issues/973) KPI contract, [#975](https://github.com/jannekbuengener/sample-brain/issues/975) tempo baseline  
**Normative KPI contract:** [`AQ1_TEMPO_BEATGRID_KPI_CONTRACT.md`](AQ1_TEMPO_BEATGRID_KPI_CONTRACT.md)  
**Baseline surface:** [`AQ1_TEMPO_BASELINE.md`](AQ1_TEMPO_BASELINE.md) / `python -m src.fsld_current_analyzer_eval`  
**Compare runner:** `python -m src.fsld_aq1_tempo_candidate_compare`

## Architecture outcome

```text
AQ1_TEMPO_CANDIDATE_COMPARE_REPRODUCIBLE
```

(or `AQ1_TEMPO_CANDIDATE_COMPARE_BLOCKED_PUBLIC_AUDIO_UNAVAILABLE` when neither live public audio nor baseline prediction JSON is available)

This document freezes a **small, fair tempo candidate set** and a **reproducible comparison harness** on the FSLD public baseline. It does **not** promote a candidate, set numeric gates, or change production defaults.

BeatGrid correctness remains **HOLD** (no public timed annotation corpus).

## Non-goals

- no production switch / no promotion thresholds
- no TEST/HOLDOUT threshold discovery or tuning
- no private audio or absolute host paths in committed artifacts
- no invented BeatGrid annotations
- no new ML tempo model / no broad `analyze.py` / `beat_grid.py` rewrite
- no reopening closed AQ8 foundation issues (#956–#959); reuse by reference

## Candidate identity (frozen ≤4)

All candidates are thin adapters over the **same** `librosa.beat.beat_track` raw BPM scalar from `src.analyze.extract_features`. They differ only by the already-exposed `bpm_normalization` mode applied after extraction via `src.analyze.normalize_bpm`.

| `candidate_id` | `bpm_normalization` | Identity notes |
|---|---|---|
| `extract_features.bpm_normalization.none` | `none` | AQ1 baseline path; raw half/double visibility for `classify_bpm_error` |
| `extract_features.bpm_normalization.heuristic` | `heuristic` | Existing heuristic fold (`<90 → ×2`, `>200 → ÷2`) |
| `extract_features.bpm_normalization.domain_110_170` | `domain_110_170` | Existing techno/dancefloor domain fold (#872) |

No other backends are in scope for this bake-off. BeatGrid `beat_backend` knobs are out of scope (BeatGrid KPI HOLD).

### Scoring rule (normative)

1. Shared raw BPM is always obtained with `bpm_normalization="none"` (live `extract_features` **or** an EVALUATED baseline prediction artifact that already recorded that path).
2. Each candidate’s reported `predicted_bpm` is `normalize_bpm(raw_bpm, mode=<candidate>)`.
3. Tempo metrics reuse `src.fsld_current_analyzer_eval._tempo_metrics` (absolute/relative error, ±0.5/±1/±2 accuracy, coverage/abstention, `classify_bpm_error` relation buckets).
4. Relation buckets are computed on the **candidate-reported** `predicted_bpm` against labels (no separate octave-normalized “success” score that hides half/double). The `none` candidate is the raw-visibility reference; folded candidates show how relation rates change after the declared normalization.
5. Do not invent thresholds from TEST/HOLDOUT.

## Partition policy

| FSLD split | AQ1 role | Allowed use in this slice |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration / comparison narrative only |
| `TEST` | TEST / HOLDOUT | frozen evidence report once; **no threshold discovery** |

## How to run

Public FSL10K audio and JSON outputs stay **outside** the repository. The runner rejects in-repo outputs (same policy as the baseline runner).

### Path A — live audio (preferred when available)

```powershell
python -m src.fsld_aq1_tempo_candidate_compare `
  --audio-root <FSL10K-audio-root> `
  --split CALIBRATION `
  --output <external-directory>/aq1-tempo-compare-calibration.json

python -m src.fsld_aq1_tempo_candidate_compare `
  --audio-root <FSL10K-audio-root> `
  --split TEST `
  --output <external-directory>/aq1-tempo-compare-test.json
```

Live path analyzes each present `.wav` once with `bpm_normalization="none"`, then applies the three in-tree normalization adapters. Missing audio / analysis failure semantics match the baseline runner (`PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY` when no record analyzes successfully).

### Path B — baseline prediction JSON (reproducible without re-analysis)

When live public audio is unavailable or host policy blocks the beat path, reuse an external EVALUATED artifact from `python -m src.fsld_current_analyzer_eval` (must be `bpm_normalization="none"` predictions):

```powershell
python -m src.fsld_aq1_tempo_candidate_compare `
  --baseline-predictions <external>/aq1-tempo-calibration.json `
  --split CALIBRATION `
  --output <external-directory>/aq1-tempo-compare-calibration.json

python -m src.fsld_aq1_tempo_candidate_compare `
  --baseline-predictions <external>/aq1-tempo-test.json `
  --split TEST `
  --output <external-directory>/aq1-tempo-compare-test.json
```

Exactly one of `--audio-root` or `--baseline-predictions` is required.

## Artifact schema (compare)

| Field | Notes |
|---|---|
| `document_type` | `sample_brain.fsld_aq1_tempo_candidate_compare` |
| `schema_version` | `1.0.0` |
| `split` | `CALIBRATION` or `TEST` |
| `run_status` | `EVALUATED` or `PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY` |
| `manifest_sha256` | verified frozen FSLD human-manifest digest |
| `raw_source` | `live_extract_features` or `baseline_predictions` |
| `beat_grid_status` | always `HOLD` in this slice |
| `candidates[]` | frozen registry entries + per-candidate `metrics.<ma\|sa>.tempo` |
| `records[]` | shared per-sample rows with `raw_predicted_bpm` (no absolute host paths) |

## BeatGrid

```text
BEATGRID_PUBLIC_ANNOTATION_CORPUS = HOLD
```

No BeatGrid correctness numbers are claimed. Runtime existence of `src/beat_grid.py` does not satisfy AQ1 BeatGrid KPI.

## AQ8 reuse (by reference)

| Closed surface | Reuse here |
|---|---|
| #956 analysis-eval envelope | domain token `aq1.tempo`; no new ARVP thresholds |
| #957 perturbation contract | not executed in this slice; expectations remain in the KPI contract |
| #958 runtime methodology | optional cold/steady timing remains out of band for this compare artifact |
| #959 semantic determinism | identical inputs + candidate config → comparable tempo projections |

## Measured summary (portable)

Public baseline prediction artifacts were available externally for both splits (EVALUATED `sample_brain.fsld_current_analyzer_eval` records with `bpm_normalization="none"`). Candidate metrics were derived by applying the in-tree `normalize_bpm` adapters (Path B / `raw_source=baseline_predictions`). Live FSL10K audio re-analysis was not required for this adapter bake-off. No absolute host paths and no private audio are committed. No candidate is promoted.

Rounded display values below; exact floats live in the external compare JSON.

### CALIBRATION → DEVELOPMENT/CALIBRATION (exploration)

| Candidate | Tier | cov | ±0.5 | ±1 | ±2 | correct | half | double | ambig | outlier |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | MA | 1.000 | 0.346 | 0.423 | 0.462 | 13 | 2 | 5 | 6 | 0 |
| none | SA | 0.981 | 0.308 | 0.423 | 0.462 | 25 | 3 | 3 | 20 | 1 |
| heuristic | MA | 1.000 | 0.385 | 0.462 | 0.500 | 15 | 1 | 4 | 6 | 0 |
| heuristic | SA | 0.981 | 0.308 | 0.442 | 0.500 | 27 | 0 | 4 | 20 | 1 |
| domain_110_170 | MA | 1.000 | 0.385 | 0.462 | 0.500 | 15 | 1 | 4 | 6 | 0 |
| domain_110_170 | SA | 0.981 | 0.327 | 0.462 | 0.519 | 28 | 0 | 3 | 20 | 1 |

`none` absolute error (mean / median / p95): MA 32.65 / 6.67 / 117.66; SA 23.54 / 10.90 / 83.39.

### TEST → TEST/HOLDOUT (frozen evidence; no tuning)

| Candidate | Tier | cov | ±0.5 | ±1 | ±2 | correct | half | double | ambig | outlier |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | MA | 0.989 | 0.322 | 0.500 | 0.600 | 56 | 3 | 2 | 28 | 1 |
| none | SA | 0.986 | 0.227 | 0.386 | 0.449 | 102 | 13 | 19 | 70 | 3 |
| heuristic | MA | 0.989 | 0.278 | 0.467 | 0.556 | 54 | 3 | 6 | 26 | 1 |
| heuristic | SA | 0.986 | 0.222 | 0.406 | 0.473 | 107 | 4 | 23 | 70 | 3 |
| domain_110_170 | MA | 0.989 | 0.289 | 0.478 | 0.567 | 55 | 1 | 5 | 28 | 1 |
| domain_110_170 | SA | 0.986 | 0.237 | 0.415 | 0.483 | 109 | 4 | 20 | 71 | 3 |

`none` absolute error (mean / median / p95): MA 19.23 / 0.80 / 81.36; SA 28.55 / 8.27 / 95.28.

Observation (non-promotional): on frozen TEST, neither `heuristic` nor `domain_110_170` dominates `none` across accuracy bands and relation buckets. CALIBRATION exploration shows mild band gains for both folds. No threshold is derived from TEST/HOLDOUT.

## Exit vocabulary

Exactly one:

- `AQ1_TEMPO_CANDIDATE_COMPARE_REPRODUCIBLE`
- `AQ1_TEMPO_CANDIDATE_COMPARE_BLOCKED_PUBLIC_AUDIO_UNAVAILABLE`
- `AQ1_TEMPO_CANDIDATE_COMPARE_INCOMPLETE`

This slice exits `AQ1_TEMPO_CANDIDATE_COMPARE_REPRODUCIBLE` for CALIBRATION and TEST with BeatGrid correctness HOLD.
