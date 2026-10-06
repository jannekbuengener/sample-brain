# AQ3 Onset / Attack Timing Baseline (synthetic corpus)

**Status:** ACTIVE_SUPPORTING — measured current onset/attack baseline for [#995](https://github.com/jannekbuengener/sample-brain/issues/995)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#945](https://github.com/jannekbuengener/sample-brain/issues/945) (AQ3), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on:** [#991](https://github.com/jannekbuengener/sample-brain/issues/991) KPI contract, [#993](https://github.com/jannekbuengener/sample-brain/issues/993) corpus  
**Normative KPI:** [`AQ3_ONSET_GESTURE_KPI_CONTRACT.md`](AQ3_ONSET_GESTURE_KPI_CONTRACT.md)  
**Corpus:** [`AQ3_TIMING_CORPUS.md`](AQ3_TIMING_CORPUS.md) / `sample-brain.aq3.timing.synthetic.v1`  
**Runner:** `python -m src.aq3_onset_attack_baseline`

## Architecture outcome

```text
AQ3_ONSET_ATTACK_BASELINE_MEASURED
```

This document records the **current** onset/attack timing path against the frozen AQ3 KPI contract on the synthetic timing corpus. It does **not** change onset/gesture algorithms, set promotion thresholds, or switch production behavior. #680 product/R&D scope stays out of this slice.

## Surfaces measured

| Plane | Current surface |
|---|---|
| `aq3.onset` | `src.gesture_analysis.analyze_gesture_audio` (onset times from gesture events) |
| `aq3.attack` | `src.workbench_attack_suggest.suggest_attack_ms` |
| `aq3.gesture` | same onset series; IOI/order reported only where multi-onset GT exists (PARTIAL when coverage is thin) |

## Partition mapping

| Corpus `split` | AQ3 KPI role |
|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION |
| `TEST` | TEST / HOLDOUT |

Do not tune on TEST/HOLDOUT. HOLD stubs (`layered_transient_dense`, `noisy`) remain HOLD — no clips in corpus v1.

## How to run

Corpus audio/GT and JSON evidence stay **outside** the repository:

```powershell
python -m src.aq3_onset_attack_baseline `
  --work-dir <external-directory>/aq3-timing-corpus `
  --output <external-directory>/aq3-onset-attack-baseline.json
```

The runner generates `sample-brain.aq3.timing.synthetic.v1` under `--work-dir`, scores current detectors with corpus tolerance candidates (20 ms / 50 ms), and rejects outputs inside the git tree. Exact floats live in the external JSON; tables below are rounded display values. No private audio and no absolute host paths are committed.

## Metric schema (AQ3-aligned)

### `aq3.onset`

Per split, micro-averaged across clips, **for each explicit tolerance window**:

| Field | Notes |
|---|---|
| `precision` / `recall` / `f1` | greedy 1:1 nearest matching within the window |
| `missed_onset_rate` / `duplicate_onset_rate` | unmatched labels / unmatched predictions |
| `abs_error_ms` mean / median / p95 | matched pairs only |
| `event_count_abs_error` | per-clip `|pred_count − label_count|` summary |
| `no_result_rate` | clips with empty / too_short / unreadable and no predictions |

### `aq3.attack`

On clips with a non-null `attack_marker_ms` label:

| Field | Notes |
|---|---|
| `eligible` / `predicted` / `coverage_rate` / `abstention_rate` | counts and rates |
| `within_tolerance_rates.<20\|50>` | fraction of **eligible** inside the window (abstention counts as miss) |
| `early_rate` / `late_rate` | among predicted claims |
| `abs_error_ms` mean / median / p95 | among predicted claims |

### `aq3.gesture`

| Status | Meaning |
|---|---|
| `HOLD` | no multi-onset clip in the split |
| `PARTIAL` | thin multi-onset coverage (IOI/order still reported where matched) |
| `MEASURED` | multi-onset coverage sufficient for a fuller gesture plane |

Quantization remains out of scope as a silent success criterion.

## Measured summary (portable)

Corpus: `sample-brain.aq3.timing.synthetic.v1` / `corpus_version=1.0.0` / `generator_seed=993001` (4 clips). External JSON `exit_status=AQ3_ONSET_ATTACK_BASELINE_MEASURED`. Analyzer algorithms were not changed.

### CALIBRATION → DEVELOPMENT/CALIBRATION

2 clips: `soft_attack`, `silence_leading`.

| Metric | Value |
|---|---:|
| onset clips / usable / no_result_rate | 2 / 2 / 0.000 |
| onset @20 ms P / R / F1 | 0.250 / 0.500 / 0.333 |
| onset @50 ms P / R / F1 | 0.250 / 0.500 / 0.333 |
| onset abs error median / p95 @20 ms | 5.4 / 5.4 ms |
| onset matched @20 ms (matched/labels) | 1 / 2 |
| attack eligible / predicted | 2 / 2 |
| attack coverage / abstention | 1.000 / 0.000 |
| attack within ±20 ms / ±50 ms | 0.500 / 1.000 |
| attack abs error mean / median / p95 | 15.0 / 15.0 / 30.0 ms |
| attack early / late rate | 0.500 / 0.000 |
| gesture | HOLD (no multi-onset clip) |

Note: soft-attack material produces multiple gesture onsets against a single GT label, which lowers onset precision on CALIBRATION. Attack on soft-attack is early by ~30 ms (inside 50 ms, outside 20 ms); silence-leading attack matches within 20 ms.

### TEST → TEST/HOLDOUT

2 clips: `short_clip`, `simple_multi_onset`.

| Metric | Value |
|---|---:|
| onset clips / usable / no_result_rate | 2 / 2 / 0.000 |
| onset @20 ms P / R / F1 | 0.750 / 0.750 / 0.750 |
| onset @50 ms P / R / F1 | 1.000 / 1.000 / 1.000 |
| onset abs error median / p95 @20 ms | 4.5 / 7.3 ms |
| onset matched @20 ms (matched/labels) | 3 / 4 |
| attack eligible / predicted | 1 / 1 |
| attack coverage / abstention | 1.000 / 0.000 |
| attack within ±20 ms / ±50 ms | 1.000 / 1.000 |
| attack abs error mean / median / p95 | 0.0 / 0.0 / 0.0 ms |
| attack early / late rate | 0.000 / 0.000 |
| gesture | PARTIAL (1 multi-onset clip) |
| gesture IOI abs error median @20/50 ms | ~4.0 ms |
| gesture order_break_rate | 0.000 |

### HOLD stubs

| Bucket | Status |
|---|---|
| `layered_transient_dense` | HOLD — no synthetic GT clip in v1 |
| `noisy` | HOLD — no synthetic GT clip in v1 |

## Non-goals (this slice)

- no onset / attack / gesture algorithm changes
- no production switch / promotion thresholds
- no #680 product duplication
- no private audio or absolute host paths in committed artifacts
- no committed WAV binaries

## Exit vocabulary

Exactly one:

- `AQ3_ONSET_ATTACK_BASELINE_MEASURED`
- `AQ3_ONSET_ATTACK_BASELINE_INCOMPLETE`

This slice exits `AQ3_ONSET_ATTACK_BASELINE_MEASURED` for CALIBRATION and TEST on `sample-brain.aq3.timing.synthetic.v1`, with gesture PARTIAL on TEST and HOLD on CALIBRATION, and layered/noisy HOLD stubs unchanged.
