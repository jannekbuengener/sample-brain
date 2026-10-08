# AQ4 Classification Candidate Comparison (synthetic corpus)

| Field | Value |
|---|---|
| Status | ACTIVE_SUPPORTING — reproducible candidate comparison for [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034); residual [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006) reconcile after [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) |
| Class | ACTIVE_SUPPORTING |
| Parents | [#946](https://github.com/jannekbuengener/sample-brain/issues/946) (AQ4), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program) |
| Depends on | [#1001](https://github.com/jannekbuengener/sample-brain/issues/1001) KPI, [#1021](https://github.com/jannekbuengener/sample-brain/issues/1021) corpus, [#1003](https://github.com/jannekbuengener/sample-brain/issues/1003) / [#1032](https://github.com/jannekbuengener/sample-brain/issues/1032) baseline, [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) diagnostics |
| Normative KPI | [`AQ4_CLASSIFICATION_KPI_CONTRACT.md`](AQ4_CLASSIFICATION_KPI_CONTRACT.md) |
| Corpus | [`AQ4_CLASSIFICATION_CORPUS.md`](AQ4_CLASSIFICATION_CORPUS.md) / `sample-brain.aq4.classification.synthetic.v1` |
| Baseline surface | [`AQ4_CLASSIFICATION_BASELINE.md`](AQ4_CLASSIFICATION_BASELINE.md) / `python -m src.aq4_classification_baseline` |
| Diagnostics (candidate-selection owner) | [`AQ4_CLASSIFICATION_DIAGNOSTICS.md`](AQ4_CLASSIFICATION_DIAGNOSTICS.md) |
| Compare runner | `python -m src.aq4_classification_candidate_compare` |

## Architecture outcome

### Historical [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) outcome (preserved)

```text
AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE
```

This document freezes a **small, fair sample_class / pred_type candidate set** and a **reproducible comparison harness** on the synthetic AQ4 classification corpus. Taxonomies stay separate. It does **not** promote a candidate, set numeric gates, switch production defaults, mandate ML, or tune on TEST/HOLDOUT.

### Residual [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006) disposition (after [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005))

```text
AQ4_CLASSIFICATION_CANDIDATE_COMPARE_NO_JUSTIFIED_CANDIDATE
```

Meaning: current diagnostics evidence does **not** justify another bounded AQ4 candidate beyond the frozen #1034 set. This is **not** a claim that the classifier is perfect, that consumer safety is proven, or that AQ4 automation is complete. Thin synthetic support and consumer HOLDs remain.

## Traceability (#1006)

| Stage | Authority | Token / identity |
|---|---|---|
| KPI | [#1001](https://github.com/jannekbuengener/sample-brain/issues/1001) / [`AQ4_CLASSIFICATION_KPI_CONTRACT.md`](AQ4_CLASSIFICATION_KPI_CONTRACT.md) | contract frozen |
| CORPUS | [#1021](https://github.com/jannekbuengener/sample-brain/issues/1021) / `sample-brain.aq4.classification.synthetic.v1` | frozen synthetic corpus (issue #1006 body may still cite older #1002 wording; live canon wins) |
| BASELINE | [#1003](https://github.com/jannekbuengener/sample-brain/issues/1003) / [#1032](https://github.com/jannekbuengener/sample-brain/issues/1032) / [`AQ4_CLASSIFICATION_BASELINE.md`](AQ4_CLASSIFICATION_BASELINE.md) | `AQ4_CLASSIFICATION_BASELINE_MEASURED` |
| DIAGNOSTICS | [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) / [`AQ4_CLASSIFICATION_DIAGNOSTICS.md`](AQ4_CLASSIFICATION_DIAGNOSTICS.md) | `AQ4_CLASSIFICATION_DIAGNOSTICS_PARTIAL_HOLD` → `NO_JUSTIFIED_CANDIDATE_HYPOTHESIS` |
| EXISTING COMPARE | [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) / this document (historical tables below) | `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE` |
| CURRENT #1006 DECISION | this residual section | `NO_JUSTIFIED_CANDIDATE` / `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_NO_JUSTIFIED_CANDIDATE` |

## Non-goals

- no production switch / no promotion thresholds
- no TEST/HOLDOUT threshold discovery or tuning
- no private audio or absolute host paths in committed artifacts
- no ML mandate / new embedding models
- no collapse of `sample_class` into `pred_type`
- no broad classify/analyze rewrite beyond declared thin config adapters
- no consumer safety-gate implementation
- no inventing new candidates solely to give #1006 a bake-off
- no reopening closed [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) / [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) / AQ8 foundation issues (#956–#959); reuse by reference
- no [#1007](https://github.com/jannekbuengener/sample-brain/issues/1007) decision-memo rewrite in this slice

## Candidate identity (frozen ≤4) — historical #1034 set

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
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration / comparison narrative only; candidate selection from diagnostics / CALIBRATION evidence |
| `TEST` | TEST / HOLDOUT | frozen evidence report once; **no threshold discovery**; **no candidate discovery** |

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

## Measured summary (portable) — historical #1034

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

### Non-promotional observation (#1034)

On this frozen synthetic corpus, thin duration and brightness adapters do **not** dominate `classification.baseline.v1` across both planes and partitions: clear `sample_class` remains saturated (macro-F1 1.0), and the known pred_type misses (Pad/Drum Loop on CALIBRATION, Impact on TEST) are unchanged. CALIBRATION-only narrative is not a production promotion proof. kNN remains HOLD.

## #1006 residual reconcile — #1005 diagnostics + existing #1034 compare

### Decision question

```text
Does #1005 provide any bounded evidence-derived candidate hypothesis
that is NOT already tested by #1034
and is sufficiently supported to justify implementation/comparison?
```

Answer: **NO**.

### #1005 input consumed

| Item | Value |
|---|---|
| #1005 exit | `AQ4_CLASSIFICATION_DIAGNOSTICS_PARTIAL_HOLD` |
| Hypothesis result | `NO_JUSTIFIED_CANDIDATE_HYPOTHESIS` |
| sample_class | clear CAL/TEST saturated; corpus too thin for durable consumer gates; no justified duration retune |
| pred_type measured misses | Drum Loop→Loop; Pad→Drone; Impact→Snare (typically `n=1` each) |
| kNN | `HOLD` (no seed embeddings / no reproducible public evidence) |

### Existing #1034 reuse (not reopened)

| Item | Value |
|---|---|
| Candidate ids | `classification.baseline.v1`, `sample_class.oneshot_max.1.0`, `sample_class.oneshot_max.1.5`, `pred_type.bright_min.4000` |
| Baseline result | clear `sample_class` saturated (macro-F1 1.0); pred_type misses as in portable tables |
| Candidate result | no thin adapter dominates baseline; duration adapters show no proven advantage; `bright_min.4000` does not recover the relevant pred_type misses |
| TEST firewall | TEST used only as frozen evidence; **not** as tuning or discovery surface |
| Production | unchanged |
| New candidates added for #1006 | **NONE** |
| New harness / product code for #1006 | **NONE** (no justified hypothesis → no new TEST discovery run) |

### Consumer HOLDs preserved (from #1005; not aggregated away)

| Consumer | Gate status |
|---|---|
| Rack playback eligibility | `HOLD_INSUFFICIENT_SUPPORT` |
| auto-loop | `PARTIAL_HOLD` |
| auto-attack / auto-metadata | `PARTIAL_HOLD` |
| kNN | `HOLD` |

A candidate-compare without improvement is **not** a consumer-safety proof. `NO_JUSTIFIED_CANDIDATE` does not clear these HOLDs.

### Semantics (normative for #1006)

`AQ4_CLASSIFICATION_CANDIDATE_COMPARE_NO_JUSTIFIED_CANDIDATE` means:

```text
Current evidence does not justify another bounded AQ4 candidate.
```

It does **not** mean: classifier perfect; consumer safety proven; AQ4 automation complete.

## HOLD stubs

| Item | Status |
|---|---|
| `aq4.pred_type_knn` | HOLD — optional kNN override not measured without seed embeddings / private paths |
| Human-labeled public/sanitized corpus | HOLD — separate from synthetic id |
| Confidence / calibration curves | HOLD — per KPI contract |
| Durable consumer FP-rate gates | HOLD / PARTIAL_HOLD per [`AQ4_CLASSIFICATION_DIAGNOSTICS.md`](AQ4_CLASSIFICATION_DIAGNOSTICS.md) |

## AQ8 reuse (by reference)

Consume closed [#956](https://github.com/jannekbuengener/sample-brain/issues/956) / [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / [#959](https://github.com/jannekbuengener/sample-brain/issues/959) methodology by reference. Do not reopen those issues in this slice.

## Exit vocabulary

Exactly one per slice context:

- `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE` — historical [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) bake-off (tables above)
- `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_NO_JUSTIFIED_CANDIDATE` — residual [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006) after [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) `NO_JUSTIFIED_CANDIDATE_HYPOTHESIS` + no justified improvement from the frozen #1034 set
- `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_INCOMPLETE`

Historical [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) remains `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE` for CALIBRATION and TEST on `sample-brain.aq4.classification.synthetic.v1`, with no production switch and no TEST tuning.

Residual [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006) exits `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_NO_JUSTIFIED_CANDIDATE`: #1005 provides no bounded new candidate hypothesis beyond the already-tested #1034 adapters, those adapters do not dominate baseline, consumer HOLDs stay visible, and no production defaults change.
