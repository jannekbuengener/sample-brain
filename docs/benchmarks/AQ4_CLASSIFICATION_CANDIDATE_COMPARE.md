# AQ4 Classification Candidate Comparison (synthetic corpus)

**Status:** ACTIVE_SUPPORTING — reproducible candidate comparison for [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#946](https://github.com/jannekbuengener/sample-brain/issues/946) (AQ4), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on:** [#1001](https://github.com/jannekbuengener/sample-brain/issues/1001) KPI, [#1021](https://github.com/jannekbuengener/sample-brain/issues/1021) corpus, [#1032](https://github.com/jannekbuengener/sample-brain/issues/1032) baseline  
**Normative KPI:** [`AQ4_CLASSIFICATION_KPI_CONTRACT.md`](AQ4_CLASSIFICATION_KPI_CONTRACT.md)  
**Corpus:** [`AQ4_CLASSIFICATION_CORPUS.md`](AQ4_CLASSIFICATION_CORPUS.md) / `sample-brain.aq4.classification.synthetic.v1`  
**Baseline surface:** [`AQ4_CLASSIFICATION_BASELINE.md`](AQ4_CLASSIFICATION_BASELINE.md) / `python -m src.aq4_classification_baseline`  
**Compare runner:** `python -m src.aq4_classification_candidate_compare`

## Architecture outcome

```text
AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE
```

This document freezes a **small, fair sample_class / pred_type candidate set** and a **reproducible comparison harness** on the synthetic AQ4 classification corpus. Taxonomies stay separate. It does **not** promote a candidate, set numeric gates, switch production defaults, mandate ML, or tune on TEST/HOLDOUT.

## Non-goals

- no production switch / no promotion thresholds
- no TEST/HOLDOUT threshold discovery or tuning
- no private audio or absolute host paths in committed artifacts
- no ML mandate / new embedding models
- no collapse of `sample_class` into `pred_type`
- no broad classify/analyze rewrite beyond declared thin config adapters
- no consumer safety-gate implementation
- no reopening closed AQ8 foundation issues (#956–#959); reuse by reference

## Candidate identity (frozen ≤4)

All candidates are thin config adapters over the **same** surfaces measured in #1032:

- `aq4.sample_class`: duration-derived class (`src.analyze.extract_features.clazz` / `_duration_class`)
- `aq4.pred_type_rule`: `src.classify.rule_type` primary tag (kNN remains HOLD)

Optional keyword overrides on `rule_type` and a documented oneshot-duration adapter exist only so bake-off configs can be declared without changing production defaults (defaults remain the current module constants).

| `candidate_id` | sample_class knob | pred_type knobs | Identity notes |
|---|---|---|---|
| `classification.baseline.v1` | `oneshot_max=1.2 s` | production rule thresholds | AQ4 baseline path; must match #1032 aggregates |
| `sample_class.oneshot_max.1.0` | `oneshot_max=1.0 s` | baseline rules | Shorter oneshot/loop boundary |
| `sample_class.oneshot_max.1.5` | `oneshot_max=1.5 s` | baseline rules | Longer oneshot/loop boundary |
| `pred_type.bright_min.4000` | baseline `1.2 s` | `bright_min=4000` (else baseline) | More sensitive brightness→Bright/HiHat/Impact path |

### Scoring rule (normative)

1. Each candidate predicts every corpus clip with its declared config only.
2. Metrics reuse `src.aq4_classification_baseline` aggregators (`aq4.sample_class` / `aq4.pred_type_rule`) with separate taxonomy planes.
3. The baseline candidate must reproduce the #1032 baseline harness aggregates on the same corpus.
4. Ambiguous / unknown GT labels stay uncertain and are excluded from clear-label denominators.
5. Do not invent thresholds from TEST/HOLDOUT.
6. Changing `sample_class` may change `pred_type` only via the existing `clazz` input to `rule_type` — planes remain scored separately.

## Partition policy

| Corpus `split` | AQ4 role | Allowed use in this slice |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration / comparison narrative only |
| `TEST` | TEST / HOLDOUT | frozen evidence report once; **no threshold discovery** |

## How to run

Corpus audio/GT and JSON evidence stay **outside** the repository:

```powershell
python -m src.aq4_classification_candidate_compare `
  --work-dir <external-directory>/aq4-classification-corpus `
  --output <external-directory>/aq4-classification-compare.json
```

The runner rejects outputs inside the git tree. Exact floats live in the external JSON; tables below are rounded display values.

## Artifact schema (compare)

| Field | Notes |
|---|---|
| `document_type` | `sample-brain.aq4.classification-candidate-compare.v1` |
| `schema_version` | `1.0.0` |
| `corpus_id` | `sample-brain.aq4.classification.synthetic.v1` |
| `baseline_document_type` | `sample-brain.aq4.classification-baseline.v1` |
| `no_tuning_on_test` | always `true` |
| `aq4.pred_type_knn` | HOLD (same as baseline) |
| `candidates[]` | frozen registry + per-candidate `splits.CALIBRATION\|TEST` metrics |
| `clips[]` | per-candidate clip rows with `clip_id` join keys only (no host paths) |

## Measured summary (portable)

Corpus: `sample-brain.aq4.classification.synthetic.v1` / `corpus_version=1.0.0` / `generator_seed=1021001` (10 clips). External JSON `exit_status=AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE`. Production defaults were not switched.

### CALIBRATION → DEVELOPMENT/CALIBRATION (exploration)

5 clips (4 clear + 1 ambiguous uncertain).

| Candidate | sample_class macro-F1 | sample_class bal-acc | pred_type macro-F1 | Notes |
|---|---:|---:|---:|---|
| `classification.baseline.v1` | 1.000 | 1.000 | 0.500 | matches #1032; Pad→Drone, Drum Loop→Loop |
| `sample_class.oneshot_max.1.0` | 1.000 | 1.000 | 0.500 | ambiguous 1.2 s clip still uncertain; clear clips unchanged |
| `sample_class.oneshot_max.1.5` | 1.000 | 1.000 | 0.500 | clear clips unchanged on this thin corpus |
| `pred_type.bright_min.4000` | 1.000 | 1.000 | 0.500 | brightness adapter does not recover Pad/Drum Loop here |

### TEST → TEST/HOLDOUT (frozen evidence; no tuning)

5 clips (4 clear + 1 unknown uncertain).

| Candidate | sample_class macro-F1 | sample_class bal-acc | pred_type macro-F1 | Notes |
|---|---:|---:|---:|---|
| `classification.baseline.v1` | 1.000 | 1.000 | 0.750 | matches #1032; Impact→Snare |
| `sample_class.oneshot_max.1.0` | 1.000 | 1.000 | 0.750 | clear clips unchanged |
| `sample_class.oneshot_max.1.5` | 1.000 | 1.000 | 0.750 | clear clips unchanged |
| `pred_type.bright_min.4000` | 1.000 | 1.000 | 0.750 | Impact still→Snare on this thin corpus |

### Non-promotional observation

On this frozen synthetic corpus, thin duration and brightness adapters do **not** dominate `classification.baseline.v1` across both planes and partitions: clear `sample_class` remains saturated (macro-F1 1.0), and the known pred_type misses (Pad/Drum Loop on CALIBRATION, Impact on TEST) are unchanged. CALIBRATION-only narrative is not a production promotion proof. kNN remains HOLD.

## HOLD stubs

| Item | Status |
|---|---|
| `aq4.pred_type_knn` | HOLD — optional kNN override not measured without seed embeddings / private paths |
| Human-labeled public/sanitized corpus | HOLD — separate from synthetic id |
| Confidence / calibration curves | HOLD — per KPI contract |

## AQ8 reuse (by reference)

Consume closed [#956](https://github.com/jannekbuengener/sample-brain/issues/956) / [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / [#959](https://github.com/jannekbuengener/sample-brain/issues/959) methodology by reference. Do not reopen those issues in this slice.

## Exit vocabulary

Exactly one:

- `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE`
- `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_INCOMPLETE`

This slice exits `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE` for CALIBRATION and TEST on `sample-brain.aq4.classification.synthetic.v1`, with no production switch and no TEST tuning.
