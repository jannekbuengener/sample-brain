# AQ3 Onset / Attack Candidate Comparison (synthetic corpus)

**Status:** ACTIVE_SUPPORTING — reproducible candidate comparison for [#997](https://github.com/jannekbuengener/sample-brain/issues/997)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#945](https://github.com/jannekbuengener/sample-brain/issues/945) (AQ3), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on:** [#991](https://github.com/jannekbuengener/sample-brain/issues/991) KPI, [#993](https://github.com/jannekbuengener/sample-brain/issues/993) corpus, [#995](https://github.com/jannekbuengener/sample-brain/issues/995) baseline  
**Normative KPI:** [`AQ3_ONSET_GESTURE_KPI_CONTRACT.md`](AQ3_ONSET_GESTURE_KPI_CONTRACT.md)  
**Corpus:** [`AQ3_TIMING_CORPUS.md`](AQ3_TIMING_CORPUS.md) / `sample-brain.aq3.timing.synthetic.v1`  
**Baseline surface:** [`AQ3_ONSET_ATTACK_BASELINE.md`](AQ3_ONSET_ATTACK_BASELINE.md) / `python -m src.aq3_onset_attack_baseline`  
**Compare runner:** `python -m src.aq3_onset_attack_candidate_compare`

## Architecture outcome

```text
AQ3_ONSET_ATTACK_CANDIDATE_COMPARE_REPRODUCIBLE
```

This document freezes a **small, fair onset/attack candidate set** and a **reproducible comparison harness** on the synthetic AQ3 timing corpus. It does **not** promote a candidate, set numeric gates, switch production defaults, or reopen #680 product/R&D scope.

## Non-goals

- no production switch / no promotion thresholds
- no TEST/HOLDOUT threshold discovery or tuning
- no private audio or absolute host paths in committed artifacts
- no #680 Pattern Core / retrieval / Rack / UI duplication
- no broad onset/attack algorithm rewrite beyond the declared thin config adapters
- no reopening closed AQ8 foundation issues (#956–#959); reuse by reference

## Candidate identity (frozen ≤4)

All candidates are thin config adapters over the **same** surfaces measured in #995:

- onset / gesture: `src.gesture_analysis.analyze_gesture_audio`
- attack: `src.workbench_attack_suggest.suggest_attack_ms`

Optional keyword overrides exist only so bake-off configs can be declared without changing production defaults (defaults remain the module constants).

| `candidate_id` | Onset knobs | Attack knobs | Identity notes |
|---|---|---|---|
| `gesture_attack.baseline.v1` | `delta=0.07`, `wait=13`, `gap=0.15 s` | `energy_ratio=0.2`, `peak_fraction=0.05`, `frame_ms=10` | AQ3 baseline path; must match #995 aggregates |
| `gesture.onset_delta.0.04` | `delta=0.04` (else baseline) | baseline | More sensitive `onset_detect` delta |
| `gesture.onset_gap.0.08` | `gap=0.08 s` (else baseline) | baseline | Tighter post-filter min onset gap |
| `attack.energy_ratio.0.10` | baseline | `energy_ratio=0.10` (else baseline) | More sensitive attack energy threshold |

### Scoring rule (normative)

1. Each candidate predicts every corpus clip with its declared config only.
2. Metrics reuse `src.aq3_onset_attack_baseline` aggregators (`aq3.onset` / `aq3.attack` / `aq3.gesture`) and corpus tolerance candidates (20 ms / 50 ms).
3. The baseline candidate must reproduce the #995 baseline harness aggregates on the same corpus.
4. Do not invent thresholds from TEST/HOLDOUT.

## Partition policy

| Corpus `split` | AQ3 role | Allowed use in this slice |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration / comparison narrative only |
| `TEST` | TEST / HOLDOUT | frozen evidence report once; **no threshold discovery** |

HOLD stubs (`layered_transient_dense`, `noisy`) remain HOLD — no clips in corpus v1.

## How to run

Corpus audio/GT and JSON evidence stay **outside** the repository:

```powershell
python -m src.aq3_onset_attack_candidate_compare `
  --work-dir <external-directory>/aq3-timing-corpus `
  --output <external-directory>/aq3-onset-attack-compare.json
```

The runner rejects outputs inside the git tree. Exact floats live in the external JSON; tables below are rounded display values.

## Artifact schema (compare)

| Field | Notes |
|---|---|
| `document_type` | `sample-brain.aq3.onset-attack-candidate-compare.v1` |
| `schema_version` | `1.0.0` |
| `corpus_id` | `sample-brain.aq3.timing.synthetic.v1` |
| `baseline_document_type` | `sample-brain.aq3.onset-attack-baseline.v1` |
| `no_tuning_on_test` | always `true` |
| `candidates[]` | frozen registry + per-candidate `splits.CALIBRATION\|TEST` metrics |
| `clips[]` | per-candidate clip rows with `clip_id` join keys only (no host paths) |

## Measured summary (portable)

Corpus: `sample-brain.aq3.timing.synthetic.v1` / `corpus_version=1.0.0` / `generator_seed=993001` (4 clips). External JSON `exit_status=AQ3_ONSET_ATTACK_CANDIDATE_COMPARE_REPRODUCIBLE`. Production defaults were not switched.

### CALIBRATION → DEVELOPMENT/CALIBRATION (exploration)

2 clips: `soft_attack`, `silence_leading`.

| Candidate | onset @20 F1 (P/R) | onset @50 F1 | attack within ±20/±50 | attack abs median (ms) | gesture |
|---|---:|---:|---:|---:|---|
| `gesture_attack.baseline.v1` | 0.333 (0.250/0.500) | 0.333 | 0.500 / 1.000 | 15.0 | HOLD |
| `gesture.onset_delta.0.04` | 0.286 (0.200/0.500) | 0.286 | 0.500 / 1.000 | 15.0 | HOLD |
| `gesture.onset_gap.0.08` | 0.333 (0.250/0.500) | 0.333 | 0.500 / 1.000 | 15.0 | HOLD |
| `attack.energy_ratio.0.10` | 0.333 (0.250/0.500) | 0.333 | 0.500 / 1.000 | 25.0 | HOLD |

### TEST → TEST/HOLDOUT (frozen evidence; no tuning)

2 clips: `short_clip`, `simple_multi_onset`.

| Candidate | onset @20 F1 (P/R) | onset @50 F1 | attack within ±20/±50 | attack abs median (ms) | gesture |
|---|---:|---:|---:|---:|---|
| `gesture_attack.baseline.v1` | 0.750 (0.750/0.750) | 1.000 | 1.000 / 1.000 | 0.0 | PARTIAL |
| `gesture.onset_delta.0.04` | 0.750 (0.750/0.750) | 1.000 | 1.000 / 1.000 | 0.0 | PARTIAL |
| `gesture.onset_gap.0.08` | 0.750 (0.750/0.750) | 1.000 | 1.000 / 1.000 | 0.0 | PARTIAL |
| `attack.energy_ratio.0.10` | 0.750 (0.750/0.750) | 1.000 | 1.000 / 1.000 | 0.0 | PARTIAL |

Gesture IOI abs error median on TEST multi-onset remains ~4.0 ms with `order_break_rate=0.000` for all candidates in this run.

### Non-promotional observation

On this frozen corpus, the thin adapters do **not** dominate `gesture_attack.baseline.v1` across both planes and partitions: more-sensitive onset delta lowers CALIBRATION onset F1 without improving TEST; tighter gap is identical to baseline here; lower attack energy ratio worsens CALIBRATION attack abs error without improving TEST. CALIBRATION-only deltas are not a production promotion proof.

## AQ8 reuse (by reference)

Consume closed [#956](https://github.com/jannekbuengener/sample-brain/issues/956) / [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / [#959](https://github.com/jannekbuengener/sample-brain/issues/959) methodology by reference. Do not reopen those issues in this slice.

## Exit vocabulary

Exactly one:

- `AQ3_ONSET_ATTACK_CANDIDATE_COMPARE_REPRODUCIBLE`
- `AQ3_ONSET_ATTACK_CANDIDATE_COMPARE_INCOMPLETE`

This slice exits `AQ3_ONSET_ATTACK_CANDIDATE_COMPARE_REPRODUCIBLE` for CALIBRATION and TEST on `sample-brain.aq3.timing.synthetic.v1`, with no production switch and no TEST tuning.
