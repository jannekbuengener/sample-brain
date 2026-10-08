# AQ4 Sample Classification Baseline (synthetic corpus)

**Status:** ACTIVE_SUPPORTING — measured current sample_class / pred_type baseline for [#1032](https://github.com/jannekbuengener/sample-brain/issues/1032); residual acceptance alignment for [#1003](https://github.com/jannekbuengener/sample-brain/issues/1003)
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#946](https://github.com/jannekbuengener/sample-brain/issues/946) (AQ4), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on:** [#1001](https://github.com/jannekbuengener/sample-brain/issues/1001) KPI contract, [#1021](https://github.com/jannekbuengener/sample-brain/issues/1021) corpus  
**Normative KPI:** [`AQ4_CLASSIFICATION_KPI_CONTRACT.md`](AQ4_CLASSIFICATION_KPI_CONTRACT.md)  
**Corpus:** [`AQ4_CLASSIFICATION_CORPUS.md`](AQ4_CLASSIFICATION_CORPUS.md) / `sample-brain.aq4.classification.synthetic.v1`  
**Runner:** `python -m src.aq4_classification_baseline`

## Architecture outcome

```text
AQ4_CLASSIFICATION_BASELINE_MEASURED
```

This document records the **current** duration-derived `sample_class` and rule `pred_type` paths against the frozen AQ4 KPI contract on the synthetic classification corpus. Taxonomies stay separate. It does **not** change classify/analyze algorithms, set promotion thresholds, or switch production behavior. Optional kNN override remains HOLD without seed embeddings / private paths.

## #1003 residual contract (DOCS_GATE)

[#1003](https://github.com/jannekbuengener/sample-brain/issues/1003) reuses the merged [#1032](https://github.com/jannekbuengener/sample-brain/issues/1032) / PR [#1033](https://github.com/jannekbuengener/sample-brain/pull/1033) harness. This slice does **not** rebuild a second evaluation framework, ARVP clone, or generic AQ platform. Greenfield corpus/metric runners are rejected.

### Candidate identities

| Path | Identity | Notes |
|---|---|---|
| Active baseline (`sample_class` + rule `pred_type`) | `classification.baseline.v1` | Production mirrors: `oneshot_max=1.2` + default `rule_type` thresholds; same id as the compare baseline candidate |
| `aq4.sample_class` | `classification.baseline.v1` | Duration-only plane under the joint baseline id |
| `aq4.pred_type_rule` | `classification.baseline.v1` | Rule-only plane under the joint baseline id |
| `aq4.pred_type_knn` | HOLD — no measured candidate_id | Optional product path not reproducible on the frozen synthetic corpus |

Do not invent bake-off candidates in #1003. Do not assign a measured candidate_id to a HOLD kNN stub.

### Exit mapping

Exactly one exit token:

| Exit | When |
|---|---|
| `AQ4_CLASSIFICATION_BASELINE_MEASURED` | Both mandatory planes (`aq4.sample_class`, `aq4.pred_type_rule`) score on CALIBRATION and TEST; optional kNN may be HOLD |
| `AQ4_CLASSIFICATION_BASELINE_PARTIAL_HOLD` | Exactly one mandatory plane can be scored and the other cannot (reserved; unused on current production surfaces) |
| `AQ4_CLASSIFICATION_BASELINE_INCOMPLETE` | Otherwise |

Optional kNN HOLD alone does **not** force `PARTIAL_HOLD`. That preserves the #1032 freeze while satisfying #1003’s third exit token.

### kNN HOLD rationale (live)

The product optional kNN path (`write_autotype_to_db(use_knn=True)`) is **not** repo-safe / not reproducible on `sample-brain.aq4.classification.synthetic.v1` today:

- `src.index.load_embeddings` is missing (only `load_embeddings_for_model` exists); import soft-disables kNN.
- Tracked `data/label_seeds.csv` points at private absolute host paths, not the synthetic corpus.

Evidence must remain a truthful HOLD stub (status + reason + surface). No fabricated metrics, mocks, or null scores that look measured. No kNN reimplementation in #1003.

### Provenance (#958 / #959 by reference)

Runtime median/p95 and semantic determinism are consumed **by reference** per the KPI contract — cite [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / [`ANALYZER_RUNTIME_METHODOLOGY_V1.md`](ANALYZER_RUNTIME_METHODOLOGY_V1.md) and [#959](https://github.com/jannekbuengener/sample-brain/issues/959) / [`../ANALYZER_SEMANTIC_DETERMINISM_V1.md`](../ANALYZER_SEMANTIC_DETERMINISM_V1.md) in portable JSON `provenance`. Do not re-run a full AQ5-style measurement loop inside this slice. Reproducibility proof for #1003 is identical corpus seed + frozen surfaces + matching aggregates on rerun.

### Production behavior

Settings toggle: `N/A` — evaluation harness only. No changes to `src/analyze.py` / `src/classify.py` thresholds, rules, or defaults. No production switch.

### Conflict avoidance

Do not edit `docs/CANON_INDEX.md` for this residual (open PR [#1101](https://github.com/jannekbuengener/sample-brain/pull/1101) owns that surface for AQ7). Downstream #1005 / #1006 / #1007 remain out of scope.

## Surfaces measured

| Plane | Current surface |
|---|---|
| `aq4.sample_class` | `src.analyze.extract_features.clazz` (duration-derived via `_duration_class`) |
| `aq4.pred_type_rule` | `src.classify.rule_type` primary tag (kNN disabled) |
| `aq4.pred_type_knn` | `src.classify.write_autotype_to_db(use_knn=True)` — **HOLD** (no seed embeddings on synthetic corpus) |

## Partition mapping

| Corpus `split` | AQ4 KPI role |
|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION |
| `TEST` | TEST / HOLDOUT |

Do not tune on TEST/HOLDOUT. Ambiguous / unknown GT labels stay explicit uncertain and are excluded from clear-label correctness denominators.

## How to run

Corpus audio/GT and JSON evidence stay **outside** the repository:

```powershell
python -m src.aq4_classification_baseline `
  --work-dir <external-directory>/aq4-classification-corpus `
  --output <external-directory>/aq4-classification-baseline.json
```

The runner generates `sample-brain.aq4.classification.synthetic.v1` under `--work-dir`, scores current classifiers with separate `aq4.sample_class` and `aq4.pred_type_rule` planes, and rejects outputs inside the git tree. Exact floats live in the external JSON; tables below are rounded display values. No private audio and no absolute host paths are committed.

## Metric schema (AQ4-aligned)

### Eligibility

| Material | Correctness denominator |
|---|---|
| `label_status=clear` and binary `oneshot`/`loop` | eligible for `aq4.sample_class` |
| `label_status=clear` and non-`unknown` semantic label | eligible for `aq4.pred_type_rule` |
| `ambiguous` / `unknown` | uncertain accounting only — not forced into P/R/F1 |

### `aq4.sample_class` / `aq4.pred_type_rule`

Per split, on clear-eligible clips only:

| Field | Notes |
|---|---|
| `n_clear_eligible` / `n_uncertain` | explicit denominators for correctness vs uncertain |
| per-class precision / recall / F1 | with `tp`/`fp`/`fn`/`support` |
| `macro_f1` | unweighted mean of per-class F1 on labels present in the eligible set |
| `balanced_accuracy` | mean of per-class recall (`sample_class`) |
| `confusion` | predicted × label (off-label predictions appear as extra columns) |
| `coverage_rate` / `abstention_rate` | current surfaces nearly always emit a label (no abstain today) |

Planes are never collapsed into one joint label or blended “autotype quality” score.

## Measured summary (portable)

Corpus: `sample-brain.aq4.classification.synthetic.v1` / `corpus_version=1.0.0` / `generator_seed=1021001` (10 clips). External JSON `exit_status=AQ4_CLASSIFICATION_BASELINE_MEASURED`. Classify/analyze algorithms were not changed.

### Dataset health

| Plane | Support |
|---|---|
| `sample_class` | oneshot 4, loop 4, ambiguous 1, unknown 1 |
| `pred_type` | Kick/Snare/HiHat-Closed/Impact/Drone/Pad/Loop/OneShot/Drum Loop/unknown — 1 each |
| `split` | CALIBRATION 5, TEST 5 |

### CALIBRATION → DEVELOPMENT/CALIBRATION

5 clips (4 clear + 1 ambiguous uncertain).

#### `aq4.sample_class`

| Metric | Value |
|---|---:|
| clear eligible / uncertain | 4 / 1 |
| macro-F1 | 1.000 |
| balanced accuracy | 1.000 |
| oneshot P / R / F1 (support 2) | 1.000 / 1.000 / 1.000 |
| loop P / R / F1 (support 2) | 1.000 / 1.000 / 1.000 |

Ambiguous boundary clip (`duration_ms=1200`) predicts `oneshot` via current ≤1.2 s rule; retained as uncertain, not scored as error.

#### `aq4.pred_type_rule`

| Metric | Value |
|---|---:|
| clear eligible / uncertain | 4 / 1 |
| macro-F1 | 0.500 |
| Kick P/R/F1 (support 1) | 1.000 / 1.000 / 1.000 |
| Snare P/R/F1 (support 1) | 1.000 / 1.000 / 1.000 |
| Drum Loop P/R/F1 (support 1) | 0.000 / 0.000 / 0.000 → predicted `Loop` |
| Pad P/R/F1 (support 1) | 0.000 / 0.000 / 0.000 → predicted `Drone` |

High-impact note: synthetic Drum Loop / Pad material is not recovered by current rule features on this thin corpus (rule falls back to `Loop` / dark-long `Drone`).

### TEST → TEST/HOLDOUT

5 clips (4 clear + 1 unknown uncertain). No tuning on this split.

#### `aq4.sample_class`

| Metric | Value |
|---|---:|
| clear eligible / uncertain | 4 / 1 |
| macro-F1 | 1.000 |
| balanced accuracy | 1.000 |
| oneshot P / R / F1 (support 2) | 1.000 / 1.000 / 1.000 |
| loop P / R / F1 (support 2) | 1.000 / 1.000 / 1.000 |

#### `aq4.pred_type_rule`

| Metric | Value |
|---|---:|
| clear eligible / uncertain | 4 / 1 |
| macro-F1 | 0.750 |
| HiHat-Closed P/R/F1 (support 1) | 1.000 / 1.000 / 1.000 |
| Drone P/R/F1 (support 1) | 1.000 / 1.000 / 1.000 |
| Loop P/R/F1 (support 1) | 1.000 / 1.000 / 1.000 |
| Impact P/R/F1 (support 1) | 0.000 / 0.000 / 0.000 → predicted `Snare` |

Unknown clip predicts `oneshot` / `Snare`; retained as uncertain, not scored as clear-label success or failure.

### HOLD stubs

| Item | Status |
|---|---|
| `aq4.pred_type_knn` | HOLD — optional kNN override not measured without seed embeddings / private paths |
| Human-labeled public/sanitized corpus | HOLD — separate from synthetic id |
| Descriptor multi-label GT | HOLD — not primary GT in corpus v1 |
| Confidence / calibration curves | HOLD — per KPI contract |

## Non-goals (this slice)

- no classify / analyze algorithm changes
- no production switch / promotion thresholds
- no collapse of `sample_class` into `pred_type`
- no private audio or absolute host paths in committed artifacts
- no committed WAV binaries
- no consumer safety-gate implementation

## Exit vocabulary

Exactly one:

- `AQ4_CLASSIFICATION_BASELINE_MEASURED`
- `AQ4_CLASSIFICATION_BASELINE_PARTIAL_HOLD`
- `AQ4_CLASSIFICATION_BASELINE_INCOMPLETE`

This slice exits `AQ4_CLASSIFICATION_BASELINE_MEASURED` for CALIBRATION and TEST on `sample-brain.aq4.classification.synthetic.v1`, with separate taxonomy planes, uncertain labels excluded from clear denominators, candidate identity `classification.baseline.v1`, and kNN HOLD unchanged. See [#1003 residual contract](#1003-residual-contract-docs_gate) for the PARTIAL_HOLD mapping.
