# AQ6 Harmonic Match Theory Correctness Baseline

**Status:** ACTIVE_SUPPORTING — measured current Harmonic Match theory correctness for [#1017](https://github.com/jannekbuengener/sample-brain/issues/1017)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#948](https://github.com/jannekbuengener/sample-brain/issues/948) (AQ6), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED — consume, do not reopen):** [#1015](https://github.com/jannekbuengener/sample-brain/issues/1015) theory truth table + KPI contract  
**Normative KPI:** [`AQ6_HARMONIC_MATCH_THEORY_KPI_CONTRACT.md`](AQ6_HARMONIC_MATCH_THEORY_KPI_CONTRACT.md)  
**Truth table:** `sample-brain.aq6.harmonic-theory.truth-table.v1` / `tests/fixtures/aq6_harmonic_theory/truth_table_v1.json`  
**Runner:** `python -m src.aq6_harmonic_theory_baseline`  
**Related (separate plane — do not mix):** [#1016](https://github.com/jannekbuengener/sample-brain/issues/1016) / [`AQ6_HARMONIC_MATCH_RANKING_RELEVANCE_CONTRACT.md`](AQ6_HARMONIC_MATCH_RANKING_RELEVANCE_CONTRACT.md)

## Architecture outcome

```text
AQ6_THEORY_BASELINE_MEASURED
```

This document records the **current** `rate_harmony` / relation-classification path against the frozen exhaustive AQ6 theory truth table. It does **not** change ranking weights, UI/QML, key/BPM detectors, embeddings/ML, or production semantics. Ranking relevance evidence must not excuse theory failures.

## Surface measured

| Plane | Current surface |
|---|---|
| `aq6.theory` | `src.workbench_harmony.rate_harmony` (+ `determine_relation` / pitch-shift suggestion) |

`aq6.ranking` and `aq6.preference` are **out of scope** for this baseline.

## How to run

JSON evidence stays **outside** the repository:

```powershell
python -m src.aq6_harmonic_theory_baseline `
  --output <external-directory>/aq6-theory-baseline.json
```

The runner loads the frozen truth-table fixture, scores every cell through the live product path, checks transposition invariance and #959 repeatability, proves BPM perturbation does not alter theory fields, and rejects outputs inside the git tree. Exact floats live in the external JSON; tables below are portable display values. No private audio and no absolute host paths are committed.

## Metric schema (AQ6 theory-aligned)

| Metric | Notes |
|---|---|
| Relation classification accuracy | Predicted `relation` == frozen expected on all scored cells |
| Incompatible false-positive rate | Frozen `compatibility=incompatible` predicted as `compatible` |
| Compatible false-negative rate | Frozen `compatibility=compatible` predicted as not `compatible` |
| Pitch-shift suggestion correctness | Transpose-only denominator; non-transpose null-shift tracked separately |
| Transposition invariance violations | Modeful +k root rotation must preserve relation/compatibility/shift |
| Evidence fail-closed rate | Missing/unparseable/missing-mode cells stay `uncertain`/`uncertain` with null shift |
| Relation error buckets | Mismatches grouped by expected `direct` / `related` / `transpose` / `uncertain` |
| BPM isolation | Ranking-adjacent BPM may change `total_score`; theory fields must not move |
| Determinism (#959) | Two identical passes → identical theory predictions and scores |

## Measured summary (portable)

Truth table: `sample-brain.aq6.harmonic-theory.truth-table.v1` / `truth_table_version=1.0.0`. External JSON `exit_status=AQ6_THEORY_BASELINE_MEASURED`. Product harmony algorithms were not changed.

### Coverage

| Material | Support |
|---|---:|
| Cells scored / expected | 584 / 584 |
| Modeful ordered pairs | 576 |
| Fail-closed evidence cells | 8 |
| Roots covered | 12 (`C`…`B` sharp-normalized) |
| Modes covered | `maj`, `min` |

### Theory KPIs (`aq6.theory`)

| Metric | Value |
|---|---:|
| Relation classification accuracy | 1.000 (584/584) |
| Incompatible false-positive rate | 0.000 (0/216) |
| Compatible false-negative rate | 0.000 (0/360) |
| Pitch-shift suggestion correctness (transpose-only) | 1.000 (240/240) |
| Non-transpose null-shift failures | 0 / 344 |
| Evidence fail-closed rate | 1.000 (8/8) |
| Transposition invariance violations | 0 |

### Relation error buckets (by expected relation)

| Expected relation | Support | Errors |
|---|---:|---:|
| `direct` | 24 | 0 |
| `related` | 96 | 0 |
| `transpose` | 240 | 0 |
| `uncertain` | 224 | 0 |

(`uncertain` support includes known-incompatible modeful pairs plus the 8 evidence cells; product relation remains `uncertain` while theory compatibility distinguishes incompatible vs evidence-uncertain.)

### Isolation / determinism

| Check | Result |
|---|---|
| BPM isolation (theory fields) | PASS — 0 relation/compatibility/pitch-shift changes across 584 cells when BPM 128/128 → 90/140; `total_score` may change (ranking-adjacent) |
| Deterministic repeatability (#959) | PASS — 2 passes identical predictions + scores |
| Ranking plane mixed into theory | False |

## Non-goals (this slice)

- no 0.75 / 0.25 ranking-weight tuning
- no UI / QML changes
- no key / BPM detector changes
- no embeddings / ML
- no private audio / absolute host paths in committed artifacts
- no production semantic switch
- no theory-table rewrite (measurement harness only)
- no ranking/preference evidence used to excuse theory failures

## Exit vocabulary

Exactly one:

- `AQ6_THEORY_BASELINE_MEASURED`
- `AQ6_THEORY_BASELINE_INCOMPLETE`

This slice exits `AQ6_THEORY_BASELINE_MEASURED`.

## Follow-on write-heads (out of scope here)

- AQ6 ranking relevance **baseline measurement** against the frozen #1016 contract (separate plane)
- Later relation-rule / weight candidates only after evidence-backed compare slices
- Preference remains later; no opaque global Harmonic Match score
