# AQ6 Harmonic Match Ranking Candidate Comparison

**Status:** ACTIVE_SUPPORTING — reproducible candidate comparison for [#1019](https://github.com/jannekbuengener/sample-brain/issues/1019)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#948](https://github.com/jannekbuengener/sample-brain/issues/948) (AQ6), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED — consume, do not reopen):** [#1015](https://github.com/jannekbuengener/sample-brain/issues/1015) theory contract, [#1016](https://github.com/jannekbuengener/sample-brain/issues/1016) ranking benchmark, [#1017](https://github.com/jannekbuengener/sample-brain/issues/1017) theory baseline, [#1018](https://github.com/jannekbuengener/sample-brain/issues/1018) ranking/upstream baseline  
**Normative ranking contract:** [`AQ6_HARMONIC_MATCH_RANKING_RELEVANCE_CONTRACT.md`](AQ6_HARMONIC_MATCH_RANKING_RELEVANCE_CONTRACT.md)  
**Ranking baseline:** [`AQ6_HARMONIC_MATCH_RANKING_BASELINE.md`](AQ6_HARMONIC_MATCH_RANKING_BASELINE.md)  
**Theory plane (hard gate — do not mix):** [`AQ6_HARMONIC_MATCH_THEORY_BASELINE.md`](AQ6_HARMONIC_MATCH_THEORY_BASELINE.md)  
**Benchmark:** `sample-brain.aq6.harmonic-ranking.relevance.v1` / `tests/fixtures/aq6_harmonic_ranking/relevance_benchmark_v1.json`  
**Compare runner:** `python -m src.aq6_harmonic_ranking_candidate_compare`

## Architecture outcome

```text
AQ6_HARMONIC_CANDIDATE_COMPARE_REPRODUCIBLE
```

This document freezes a **small, fair Harmonic Match ranking candidate set** (≤4) and a **reproducible comparison harness** against frozen #1016 labels with #1018 as the baseline anchor. Theory correctness stays a **hard per-candidate gate** (#1015/#1017): ranking gain may not hide a theory regression. It does **not** promote a candidate, change production `0.75`/`0.25` defaults, retune on TEST/HOLDOUT, or claim theory fixes.

## Non-goals

- no production switch / no unguarded weight promotion
- no TEST/HOLDOUT threshold discovery or tuning
- no UI / QML changes
- no key / BPM detector changes
- no embeddings / ML
- no private audio or absolute host paths in committed artifacts
- no theory-table rewrite / no ranking metrics used as theory ground truth
- no human preference used as theory ground truth
- no opaque global score collapsing `aq6.theory` + `aq6.ranking`

## Candidate identity (frozen ≤4)

All candidates are thin adapters over the same surface measured in #1018 (`find_harmony_matches` / total-score components). Relation classification continues to use production `determine_relation`; adapters may only change declared weights, relation→harmony score map, or a post-rank uncertain filter.

| `candidate_id` | Weights (H/BPM) | Other knobs | Derived from |
|---|---|---|---|
| `harmonic.baseline.v1` | `0.75` / `0.25` | production relation scores; no filter | #1018 as_labeled anchor |
| `harmonic.weights.harmony_0.90_bpm_0.10` | `0.90` / `0.10` | production relation scores | #1018 BPM-secondary / Top-K soft spot |
| `harmonic.weights.harmony_1.00_bpm_0.00` | `1.00` / `0.00` | BPM still visible; weight 0 | #1018 BPM secondary isolation |
| `harmonic.rank_filter.drop_uncertain` | `0.75` / `0.25` | drop `relation=uncertain` before metrics | #1018 Top-5 FP + theory-incompatible-in-Top-K |

### Scoring rule (normative)

1. Each candidate ranks every frozen #1016 query with its declared adapter only.
2. Ranking metrics reuse #1018 helpers (Precision@K / MRR@K / NDCG@K / Top-K FP / coverage).
3. Partitions are reported separately: CALIBRATION = exploration narrative; TEST + HOLDOUT = frozen evidence (no tuning).
4. `harmonic.baseline.v1` must reproduce the #1018 as_labeled anchor KPIs on the same fixture.
5. Every candidate must pass the #1015 theory gate (relation/compatibility/pitch-shift); failures are hard-visible and cannot be averaged into ranking KPIs.
6. Upstream states remain measurable; missing evidence stays fail-closed.
7. Do not invent promotion thresholds from TEST/HOLDOUT.

## Partition policy

| Fixture `partition` | AQ6 role | Allowed use in this slice |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration / comparison narrative only |
| `TEST` | TEST | frozen evidence report once; **no threshold discovery** |
| `HOLDOUT` | HOLDOUT | frozen evidence report once; **no threshold discovery** |

## How to run

JSON evidence stays **outside** the repository:

```powershell
python -m src.aq6_harmonic_ranking_candidate_compare `
  --output <external-directory>/aq6-ranking-candidate-compare.json
```

The runner loads frozen ranking + theory fixtures, scores every candidate, applies the theory hard gate, proves #959 repeatability, and rejects outputs inside the git tree. Exact floats live in the external JSON; tables below are portable display values. No private audio and no absolute host paths are committed.

## Artifact schema (compare)

| Field | Notes |
|---|---|
| `document_type` | `sample-brain.aq6.harmonic-ranking-candidate-compare.v1` |
| `schema_version` | `1.0.0` |
| `domain` | `aq6.ranking` |
| `baseline_document_type` | `sample-brain.aq6.harmonic-ranking-baseline.v1` |
| `no_tuning_on_test` | always `true` |
| `production_switch` | always `false` |
| `candidates[]` | frozen registry + `ranking` + `theory_gate` + `determinism` |
| `theory_plane` | hard gate metadata; never mixed into ranking macros |

## Measured summary (portable)

Benchmark: `sample-brain.aq6.harmonic-ranking.relevance.v1` / `benchmark_version=1.0.0`. External JSON `exit_status=AQ6_HARMONIC_CANDIDATE_COMPARE_REPRODUCIBLE`. Production ranking defaults were not switched.

### Theory hard gate (`aq6.theory`)

| Candidate | Theory gate | Relation accuracy |
|---|---|---:|
| all four frozen candidates | PASS | 1.000 |

No candidate claims a theory fix; ranking adapters leave relation classification identical to the #1017 product path.

### CALIBRATION (exploration narrative)

2 queries scored. Exploration only — not a promotion gate.

| Candidate | P@1 | MRR@5 | NDCG@5 | Top-5 FP | Notes |
|---|---:|---:|---:|---:|---|
| `harmonic.baseline.v1` | 1.000 | 1.000 | 1.000 | 0.200 | #1018 anchor |
| `harmonic.weights.harmony_0.90_bpm_0.10` | 1.000 | 1.000 | 1.000 | 0.200 | ties baseline (relation-priority dominates) |
| `harmonic.weights.harmony_1.00_bpm_0.00` | 1.000 | 1.000 | 1.000 | 0.200 | ties baseline on this fixture |
| `harmonic.rank_filter.drop_uncertain` | 1.000 | 1.000 | 1.000 | 0.000 | removes uncertain before Top-K FP |

### TEST + HOLDOUT (frozen evidence)

TEST: 2 queries (1 scored + 1 empty on missing reference BPM). HOLDOUT: 1 scored. Report once; do not tune.

| Candidate | TEST P@1 | TEST Top-5 FP | HOLDOUT P@1 | HOLDOUT Top-5 FP | Theory gate |
|---|---:|---:|---:|---:|---|
| `harmonic.baseline.v1` | 1.000 | 0.200 | 1.000 | 0.200 | PASS |
| `harmonic.weights.harmony_0.90_bpm_0.10` | 1.000 | 0.200 | 1.000 | 0.200 | PASS |
| `harmonic.weights.harmony_1.00_bpm_0.00` | 1.000 | 0.200 | 1.000 | 0.200 | PASS |
| `harmonic.rank_filter.drop_uncertain` | 1.000 | 0.000 | 1.000 | 0.000 | PASS |

Baseline as_labeled overall remains P@1=1.000 / MRR@5=1.000 / NDCG@5=1.000 / Top-5 FP=0.200 with 4 scored + 1 empty, matching #1018. Weight-only adapters do not move macros on this thin synthetic set because relation-priority sort dominates within-band BPM reordering. `drop_uncertain` lowers Top-5 FP to 0.000 without a theory regression — still **not** a production promotion in this slice.

## Non-promotion note

This slice does **not** select a production winner. Any KEEP / DEFER / promote decision belongs to a later decision memo (#1022) and must remain evidence-backed with theory regressions hard-visible.

## Exit vocabulary

Exactly one:

- `AQ6_HARMONIC_CANDIDATE_COMPARE_REPRODUCIBLE`
- `AQ6_HARMONIC_NO_JUSTIFIED_CANDIDATE`
- `AQ6_HARMONIC_CANDIDATE_COMPARE_INCOMPLETE`

This slice exits `AQ6_HARMONIC_CANDIDATE_COMPARE_REPRODUCIBLE`.

## Follow-on write-heads (out of scope here)

- [#1020](https://github.com/jannekbuengener/sample-brain/issues/1020) — optional blinded human preference (`NOT_REQUIRED` is valid)
- [#1022](https://github.com/jannekbuengener/sample-brain/issues/1022) — evidence-backed decision memo (KEEP/DEFER only; still no unguarded production switch)
