# AQ2 Key / Mode / Tonality Baseline (FSLD)

**Status:** ACTIVE_SUPPORTING — measured current-analyzer key/tonality baseline for [#985](https://github.com/jannekbuengener/sample-brain/issues/985)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#944](https://github.com/jannekbuengener/sample-brain/issues/944) (AQ2), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Normative KPI contract:** [`AQ2_KEY_TONALITY_KPI_CONTRACT.md`](AQ2_KEY_TONALITY_KPI_CONTRACT.md) ([#983](https://github.com/jannekbuengener/sample-brain/issues/983))  
**Runner surface:** [`FSLD_CURRENT_ANALYZER_EVAL.md`](FSLD_CURRENT_ANALYZER_EVAL.md) / `python -m src.fsld_current_analyzer_eval`

## Architecture outcome

```text
AQ2_KEY_TONALITY_BASELINE_MEASURED
```

This document records the **current** Sample Brain key/mode/tonality path against the frozen AQ2 KPI contract on the public FSLD human-manifest surface. It does **not** change key/mode algorithms, invent a continuous claim score, set promotion thresholds, or switch production behavior.

AUROC / AUPRC and confidence-as-probability calibration remain **HOLD** — see the KPI contract.

## Partition mapping

| FSLD human-manifest split | AQ2 role |
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
  --output <external-directory>/aq2-key-tonality-calibration.json

python -m src.fsld_current_analyzer_eval `
  --audio-root <FSL10K-audio-root> `
  --split TEST `
  --output <external-directory>/aq2-key-tonality-test.json
```

The runner calls `extract_features(..., bpm_normalization="none")`, verifies the frozen manifest SHA-256 sidecar, and rejects outputs inside the repository. If no record analyzes successfully, `run_status` is `PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY` and `metrics` is `null` — that is **not** a 0% quality baseline.

Unavailable local public audio → document `PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY` / exit `AQ2_KEY_TONALITY_BASELINE_BLOCKED_PUBLIC_AUDIO_UNAVAILABLE`.

## Key / tonality metric schema (AQ2-aligned)

On each `metrics.<ma|sa>` object the runner reports:

| Field | Notes |
|---|---|
| `key_root` | tonal + `root_evidence=known`; `exact` / `exact_rate` plus `coverage_rate` / `abstention_rate` |
| `key_mode` | tonal + `mode_evidence=known` (mode-on-mode-known; does **not** require root match) |
| `full_key` | tonal + root+mode known; joint exactness with coverage/abstention |
| `key_confusion` | diagnostic buckets on full-key-eligible material (`exact` / `relative` / `parallel` / `fifth` / `fourth` / `semitone_neighbor` / `other` / `missing_prediction`) |
| `tonality` | claimability: tonal coverage/abstention, `no_key` false-key-claim rate, selective full-key among claimed; `auroc_auprc` / `calibration` are `HOLD` |

Tempo metrics remain a separate plane and are unchanged in meaning by this slice.

## Confidence / ranking

```text
CONTINUOUS_CLAIM_SCORE = HOLD
AUROC_AUPRC = HOLD
CALIBRATION = HOLD
```

`key_conf` remains relative chroma-peak prominence evidence only (`KEY_CONF_EVIDENCE.md`). No continuous claim score is invented here.

## Measured summary (portable)

Public FSLD audio for both splits was available locally (CALIBRATION and TEST roots). AQ2 key/mode/tonality fields were **recomputed** with the extended runner metrics from prior EVALUATED current-analyzer prediction records (Path B, same pattern as AQ1 tempo baseline):

- **CALIBRATION** — prior `sample_brain.fsld_current_analyzer_eval` run (`run_status=EVALUATED`, 100/100 `status=ok`)
- **TEST** — prior `sample_brain.fsld_current_analyzer_eval` run (`run_status=EVALUATED`, 400/400 `status=ok`)

External JSON evidence stays untracked outside the repository (no absolute host paths, no private audio committed). Analyzer algorithms were not changed.

Rounded display values below; exact floats live in the external JSON.

### CALIBRATION → DEVELOPMENT/CALIBRATION

| Metric | MA | SA |
|---|---:|---:|
| key_root eligible / predicted | 20 / 20 | 23 / 23 |
| key_root exact_rate | 0.700 | 0.609 |
| key_root coverage / abstention | 1.000 / 0.000 | 1.000 / 0.000 |
| key_mode eligible / predicted | 16 / 8 | 18 / 5 |
| key_mode exact_rate | 0.438 | 0.167 |
| key_mode coverage / abstention | 0.500 / 0.500 | 0.278 / 0.722 |
| full_key eligible / predicted | 14 / 7 | 18 / 5 |
| full_key exact_rate | 0.143 | 0.167 |
| full_key coverage / abstention | 0.500 / 0.500 | 0.278 / 0.722 |
| tonal coverage / abstention | 1.000 / 0.000 (27) | 1.000 / 0.000 (23) |
| no_key false-key-claim rate | 1.000 (19/19) | 0.968 (30/31) |
| selective full-key exact among claimed | 0.286 (2/7) | 0.600 (3/5) |
| confusion exact / relative / parallel / fifth / fourth / semitone / other / missing | 2 / 0 / 0 / 3 / 0 / 0 / 2 / 7 | 3 / 0 / 0 / 1 / 0 / 0 / 1 / 13 |

### TEST → TEST/HOLDOUT

| Metric | MA | SA |
|---|---:|---:|
| key_root eligible / predicted | 85 / 85 | 89 / 89 |
| key_root exact_rate | 0.612 | 0.472 |
| key_root coverage / abstention | 1.000 / 0.000 | 1.000 / 0.000 |
| key_mode eligible / predicted | 57 / 14 | 71 / 12 |
| key_mode exact_rate | 0.123 | 0.127 |
| key_mode coverage / abstention | 0.246 / 0.754 | 0.169 / 0.831 |
| full_key eligible / predicted | 50 / 13 | 71 / 12 |
| full_key exact_rate | 0.100 | 0.085 |
| full_key coverage / abstention | 0.260 / 0.740 | 0.169 / 0.831 |
| tonal coverage / abstention | 1.000 / 0.000 (110) | 1.000 / 0.000 (90) |
| no_key false-key-claim rate | 1.000 (78/78) | 1.000 (122/122) |
| selective full-key exact among claimed | 0.385 (5/13) | 0.500 (6/12) |
| confusion exact / relative / parallel / fifth / fourth / semitone / other / missing | 5 / 2 / 0 / 1 / 0 / 0 / 5 / 37 | 6 / 0 / 1 / 2 / 1 / 0 / 2 / 59 |

## Non-goals (this slice)

- no `src/analyze.py` / key-algorithm changes
- no promotion thresholds / production switch
- no Harmonic Match scoring changes
- no invented continuous claim score / AUROC / calibration curves
- no private audio or absolute host paths in committed artifacts

## Exit vocabulary

Exactly one:

- `AQ2_KEY_TONALITY_BASELINE_MEASURED`
- `AQ2_KEY_TONALITY_BASELINE_BLOCKED_PUBLIC_AUDIO_UNAVAILABLE`
- `AQ2_KEY_TONALITY_BASELINE_INCOMPLETE`

This slice exits `AQ2_KEY_TONALITY_BASELINE_MEASURED` for CALIBRATION and TEST on the FSLD key/tonality eligibility sets, with AUROC/calibration HOLD.
