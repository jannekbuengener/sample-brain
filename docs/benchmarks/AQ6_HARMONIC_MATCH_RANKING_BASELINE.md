# AQ6 Harmonic Match Ranking Baseline + Upstream-Error Propagation

**Status:** ACTIVE_SUPPORTING — measured current Harmonic Match ranking path for [#1018](https://github.com/jannekbuengener/sample-brain/issues/1018)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#948](https://github.com/jannekbuengener/sample-brain/issues/948) (AQ6), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED — consume, do not reopen):** [#1016](https://github.com/jannekbuengener/sample-brain/issues/1016) ranking relevance contract; [#1017](https://github.com/jannekbuengener/sample-brain/issues/1017) theory baseline (separate plane)  
**Normative ranking contract:** [`AQ6_HARMONIC_MATCH_RANKING_RELEVANCE_CONTRACT.md`](AQ6_HARMONIC_MATCH_RANKING_RELEVANCE_CONTRACT.md)  
**Benchmark:** `sample-brain.aq6.harmonic-ranking.relevance.v1` / `tests/fixtures/aq6_harmonic_ranking/relevance_benchmark_v1.json`  
**Runner:** `python -m src.aq6_harmonic_ranking_baseline`  
**Related (separate plane — do not mix):** [`AQ6_HARMONIC_MATCH_THEORY_BASELINE.md`](AQ6_HARMONIC_MATCH_THEORY_BASELINE.md)

## Architecture outcome

```text
AQ6_RANKING_BASELINE_AND_UPSTREAM_DELTA_MEASURED
```

This document records the **current** `find_harmony_matches` / total-score ranking path against the frozen #1016 ranking-relevance benchmark, plus controlled upstream key/BPM evidence deltas. It does **not** change ranking weights (`0.75` / `0.25`), UI/QML, key/BPM detectors, embeddings/ML, or production semantics. Theory correctness (#1017) remains an independent plane and is not remeasured here as ranking quality.

## Surface measured

| Plane | Current surface |
|---|---|
| `aq6.ranking` | `src.workbench_harmony.find_harmony_matches` (+ `rate_harmony` total-score components) |

Weights under measurement (not tuned): harmony `0.75`, BPM `0.25`.

`aq6.theory` is cited for visibility only. `aq6.preference` remains inactive.

## How to run

JSON evidence stays **outside** the repository:

```powershell
python -m src.aq6_harmonic_ranking_baseline `
  --output <external-directory>/aq6-ranking-baseline.json
```

The runner loads the frozen ranking-relevance fixture, ranks each query through the live product finder, scores Precision@K / MRR@K / NDCG@K / Top-K FP against frozen grades, runs controlled upstream states, checks missing-evidence fail-closed behavior, proves #959 repeatability, and rejects outputs inside the git tree. Exact floats live in the external JSON; tables below are portable display values. No private audio and no absolute host paths are committed.

## Metric schema (`aq6.ranking`)

| Metric | Notes |
|---|---|
| Precision@K / MRR@K / NDCG@K | Frozen #1016 definitions; K in {1,3,5}; macro over non-empty queries |
| Top-K false-positive rate | Eligible hard negatives (`relevance_grade==0`) in Top-K |
| Coverage / abstention | Empty-result queries; ineligible-candidate fraction |
| Upstream deltas | `as_labeled` vs `missing_candidate_key` / `wrong_candidate_key` |
| BPM cohorts | Queries with known vs missing secondary BPM evidence |
| Missing-evidence guard | Ineligible rows stay `relation=uncertain` / `harmony_score=0` |
| Determinism (#959) | Two identical passes → identical ranked lists + macros |
| Theory visibility | Incompatible theory labels in Top-K reported separately; not folded into ranking KPIs |

## Measured summary (portable)

Benchmark: `sample-brain.aq6.harmonic-ranking.relevance.v1` / `benchmark_version=1.0.0`. External JSON `exit_status=AQ6_RANKING_BASELINE_AND_UPSTREAM_DELTA_MEASURED`. Product ranking weights and relation semantics were not changed.

### Coverage

| Material | Support |
|---|---:|
| Queries total / scored / empty | 5 / 4 / 1 |
| Empty abstention | `q_test_amaj_bpm_missing_reference` (`missing_reference_bpm`) |
| Partitions | CALIBRATION 2, TEST 2 (1 empty), HOLDOUT 1 |

### As-labeled ranking KPIs (`aq6.ranking`)

Macro over the 4 non-empty product rankings:

| Metric | Value |
|---|---:|
| Precision@1 | 1.000 |
| Precision@3 | 0.917 |
| Precision@5 | 0.600 |
| MRR@5 | 1.000 |
| NDCG@5 | 1.000 |
| Top-5 false-positive rate | 0.200 |

Interpretation: with correct labeled key/mode evidence, relation-priority ranking places a relevant item first on every scored query. Precision@5 / Top-5 FP reflect hard-negatives and padding still appearing inside K=5 after compatible family matches (not a theory failure).

### Upstream-error propagation (controlled)

Labels stay frozen (#1016). Only injected upstream key evidence changes; weights stay `0.75` / `0.25`. Attribution: **upstream_evidence**.

| State | P@1 | MRR@5 | NDCG@5 | Top-5 FP | P@1 delta vs as_labeled |
|---|---:|---:|---:|---:|---:|
| `as_labeled` | 1.000 | 1.000 | 1.000 | 0.200 | — |
| `missing_candidate_key` | 0.750 | 0.875 | 0.831 | 0.200 | -0.250 |
| `wrong_candidate_key` | 0.000 | 0.500 | 0.601 | 0.200 | -1.000 |

Wrong upstream key claims (hard-negative given the reference key; first relevant given a far key) collapse P@1 to 0. Missing candidate keys degrade ranking without inventing compatible relations.

### BPM secondary evidence

| Cohort | Queries | Scored | Empty | P@1 | NDCG@5 | Notes |
|---|---:|---:|---:|---:|---:|---|
| BPM known | 3 | 3 | 0 | 1.000 | 1.000 | Secondary BPM present on ref+cands |
| BPM missing | 2 | 1 | 1 | 1.000 | 1.000 | Missing **reference** BPM → product abstains with empty result; missing **candidate** BPM still ranks via harmony-primary path |

Missing BPM never invents tempo certainty (`bpm_score=0` when either side missing). Missing reference BPM is an abstention, not a forced ranking.

### Missing-evidence / forced-certainty guard

| Check | Result |
|---|---|
| Ineligible candidates checked | 4 |
| Forced compatible count | 0 |
| Guard | PASS — missing/uncertain key/mode stays `uncertain` with `harmony_score=0` |

### Isolation / determinism / theory plane

| Check | Result |
|---|---|
| Deterministic repeatability (#959) | PASS — 2 passes identical ranked lists + macros |
| Tie / sort policy | relation priority, then `-total_score`, then `\|pitch_shift\|`, then name/path — no opaque fusion |
| Theory plane mixed into ranking KPIs | False |
| Theory-incompatible labels observed in Top-K (sum across scored queries) | 4 (reported separately; does not rewrite #1017) |

## Non-goals (this slice)

- no 0.75 / 0.25 ranking-weight tuning
- no UI / QML changes
- no key / BPM detector changes
- no embeddings / ML
- no private audio / absolute host paths in committed artifacts
- no production semantic switch
- no theory-table rewrite / no theory remeasurement as ranking
- no human preference scoring

## Exit vocabulary

Exactly one:

- `AQ6_RANKING_BASELINE_AND_UPSTREAM_DELTA_MEASURED`
- `AQ6_RANKING_BASELINE_PARTIAL_HOLD`
- `AQ6_RANKING_BASELINE_INCOMPLETE`

This slice exits `AQ6_RANKING_BASELINE_AND_UPSTREAM_DELTA_MEASURED`.

## Follow-on write-heads (out of scope here)

- Later AQ6 weight / relation **candidate compare** slices against this baseline + frozen #1016 TEST/HOLDOUT (no unguarded production promotion)
- Preference remains later; no opaque global Harmonic Match score collapsing `aq6.theory` + `aq6.ranking`
