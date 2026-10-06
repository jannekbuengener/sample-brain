# AQ1 Tempo Baseline (FSLD, `bpm_evidence=known`)

**Status:** ACTIVE_SUPPORTING — measured current-analyzer tempo baseline for [#975](https://github.com/jannekbuengener/sample-brain/issues/975)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#943](https://github.com/jannekbuengener/sample-brain/issues/943) (AQ1), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Normative KPI contract:** [`AQ1_TEMPO_BEATGRID_KPI_CONTRACT.md`](AQ1_TEMPO_BEATGRID_KPI_CONTRACT.md) ([#973](https://github.com/jannekbuengener/sample-brain/issues/973))  
**Runner surface:** [`FSLD_CURRENT_ANALYZER_EVAL.md`](FSLD_CURRENT_ANALYZER_EVAL.md) / `python -m src.fsld_current_analyzer_eval`

## Architecture outcome

```text
AQ1_TEMPO_BASELINE_MEASURED
```

This document records the **current** Sample Brain tempo path against the frozen AQ1 KPI contract on the public FSLD human-manifest surface (`bpm_evidence=known`). It does **not** change BPM/BeatGrid algorithms, set promotion thresholds, or switch production behavior.

BeatGrid correctness remains **HOLD** (no public timed annotation corpus) — see the KPI contract.

## Partition mapping

| FSLD human-manifest split | AQ1 role |
|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION |
| `TEST` | TEST / HOLDOUT |

Do not tune on TEST/HOLDOUT. Private libraries may be a reality check only and must not enter committed artifacts.

## How to run

Public FSL10K audio stays **outside** the repository as `<audio-root>/<public_sample_id>.wav`. Write JSON **outside** the repo:

```powershell
python -m src.fsld_current_analyzer_eval `
  --audio-root <FSL10K-audio-root> `
  --split CALIBRATION `
  --output <external-directory>/aq1-tempo-calibration.json

python -m src.fsld_current_analyzer_eval `
  --audio-root <FSL10K-audio-root> `
  --split TEST `
  --output <external-directory>/aq1-tempo-test.json
```

The runner calls `extract_features(..., bpm_normalization="none")`, verifies the frozen manifest SHA-256 sidecar, and rejects outputs inside the repository. If no record analyzes successfully, `run_status` is `PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY` and `metrics` is `null` — that is **not** a 0% quality baseline.

Unavailable local public audio → document `PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY` / exit `AQ1_TEMPO_BASELINE_BLOCKED_PUBLIC_AUDIO_UNAVAILABLE`.

## Tempo metric schema (AQ1-aligned)

On the eligible set (`bpm_evidence=known` + finite positive label BPM), each `metrics.<ma|sa>.tempo` object reports:

| Field | Notes |
|---|---|
| `eligible` / `predicted` | counts |
| `coverage_rate` / `abstention_rate` | `predicted/eligible`, `(eligible−predicted)/eligible` |
| `accuracy_within_0_5_bpm` / `accuracy_within_1_bpm` / `accuracy_within_2_bpm` | fraction of **eligible** with finite predicted BPM inside the band |
| `absolute_bpm_error` / `relative_bpm_error` | mean / median / p95 summaries |
| `relation_counts` / `relation_rates` | `classify_bpm_error` buckets (`correct` / `half` / `double` / `ambiguous` / `outlier`) |

Key metrics remain separate planes and are unchanged by this slice.

## BeatGrid

```text
BEATGRID_PUBLIC_ANNOTATION_CORPUS = HOLD
```

No BeatGrid correctness numbers are claimed here. Runtime existence of `src/beat_grid.py` does not satisfy AQ1 BeatGrid KPI.

## Measured summary (portable)

Public FSLD audio for both splits was available locally. Live re-analysis on the executing host could not produce BPM predictions (optional `numba`/librosa beat path blocked by host application-control policy), so AQ1 accuracy bands and coverage fields were **recomputed** with the extended `_tempo_metrics` from prior EVALUATED current-analyzer prediction records:

- **CALIBRATION** — prior `sample_brain.fsld_current_analyzer_eval` run (`run_status=EVALUATED`)
- **TEST** — prior bakeoff engine `sample_brain_current` records (same current-analyzer prediction surface)

External JSON evidence stays untracked outside the repository (no absolute host paths, no private audio committed). Analyzer algorithms were not changed.

Rounded display values below; exact floats live in the external JSON.

### CALIBRATION → DEVELOPMENT/CALIBRATION

| Metric | MA | SA |
|---|---:|---:|
| eligible / predicted | 26 / 26 | 52 / 51 |
| coverage_rate | 1.000 | 0.981 |
| abstention_rate | 0.000 | 0.019 |
| accuracy ±0.5 BPM | 0.346 | 0.308 |
| accuracy ±1 BPM | 0.423 | 0.423 |
| accuracy ±2 BPM | 0.462 | 0.462 |
| abs error mean / median / p95 | 32.65 / 6.67 / 117.66 | 23.54 / 10.90 / 83.39 |
| rel error mean / median / p95 | 0.302 / 0.049 / 1.011 | 0.207 / 0.109 / 0.760 |
| relation correct / half / double / ambiguous / outlier | 13 / 2 / 5 / 6 / 0 | 25 / 3 / 3 / 20 / 1 |

### TEST → TEST/HOLDOUT

| Metric | MA | SA |
|---|---:|---:|
| eligible / predicted | 90 / 89 | 207 / 204 |
| coverage_rate | 0.989 | 0.986 |
| abstention_rate | 0.011 | 0.014 |
| accuracy ±0.5 BPM | 0.322 | 0.227 |
| accuracy ±1 BPM | 0.500 | 0.386 |
| accuracy ±2 BPM | 0.600 | 0.449 |
| abs error mean / median / p95 | 19.23 / 0.80 / 81.36 | 28.55 / 8.27 / 95.28 |
| rel error mean / median / p95 | 0.157 / 0.007 / 0.563 | 0.258 / 0.064 / 1.007 |
| relation correct / half / double / ambiguous / outlier | 56 / 3 / 2 / 28 / 1 | 102 / 13 / 19 / 70 / 3 |

## Non-goals (this slice)

- no `src/analyze.py` / `src/beat_grid.py` algorithm changes
- no promotion thresholds / production switch
- no candidate bake-off
- no invented BeatGrid annotations
- no private audio or absolute host paths in committed artifacts

## Exit vocabulary

Exactly one:

- `AQ1_TEMPO_BASELINE_MEASURED`
- `AQ1_TEMPO_BASELINE_BLOCKED_PUBLIC_AUDIO_UNAVAILABLE`
- `AQ1_TEMPO_BASELINE_INCOMPLETE`

This slice exits `AQ1_TEMPO_BASELINE_MEASURED` for CALIBRATION and TEST on the FSLD `bpm_evidence=known` eligible sets, with BeatGrid correctness HOLD.
