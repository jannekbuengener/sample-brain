# AQ6 Harmonic Match Human Preference Gate

**Status:** ACTIVE_SUPPORTING — optional preference-plane gate for [#1020](https://github.com/jannekbuengener/sample-brain/issues/1020)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#948](https://github.com/jannekbuengener/sample-brain/issues/948) (AQ6), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED — consume, do not reopen):** [#1019](https://github.com/jannekbuengener/sample-brain/issues/1019) candidate comparison (`AQ6_HARMONIC_CANDIDATE_COMPARE_REPRODUCIBLE`, merge `b1cf8a46`)  
**Compare evidence:** [`AQ6_HARMONIC_MATCH_RANKING_CANDIDATE_COMPARE.md`](AQ6_HARMONIC_MATCH_RANKING_CANDIDATE_COMPARE.md)  
**Theory plane (do not mix):** [`AQ6_HARMONIC_MATCH_THEORY_BASELINE.md`](AQ6_HARMONIC_MATCH_THEORY_BASELINE.md)  
**Ranking plane (do not mix):** [`AQ6_HARMONIC_MATCH_RANKING_BASELINE.md`](AQ6_HARMONIC_MATCH_RANKING_BASELINE.md)

## Architecture outcome

```text
AQ6_HUMAN_PREFERENCE_NOT_REQUIRED
```

This document records the **first gate** for AQ6 layer C (musical preference): whether #1019 leaves a **material unresolved preference question** that deterministic theory and ranking labels cannot resolve. Preference remains a **separate evidence plane** from `aq6.theory` and `aq6.ranking`. This slice does **not** run a listening study, invent subjective labels, change production weights, or promote any candidate.

## Gate verdict

| Field | Value |
|---|---|
| Gate | `REQUIRED` vs `NOT_REQUIRED` |
| Recorded | `NOT_REQUIRED` |
| EXIT | `AQ6_HUMAN_PREFERENCE_NOT_REQUIRED` |
| Listening study | **not run** (would be manufacturing evidence) |
| Preference corpus | none (no private audio; no synthetic preference labels) |
| Production weights | unchanged (`0.75` / `0.25`) |

## Why preference is not required for AQ6 decision readiness

#1019 already separates theory and ranking and reports objective, reproducible macros on the frozen #1016 fixture. After that compare:

1. **Theory plane is closed for preference.** All four frozen candidates PASS the #1015/#1017 theory hard gate (relation accuracy `1.000`). Subjective preference must never rewrite theory truth.
2. **Weight-only candidates do not create an A/B preference question.** `harmonic.weights.harmony_0.90_bpm_0.10` and `harmonic.weights.harmony_1.00_bpm_0.00` **tie** `harmonic.baseline.v1` on Precision@K / MRR@K / NDCG@K / Top-5 FP across CALIBRATION, TEST, and HOLDOUT. There is no residual “which ranking sounds better?” discriminator among weight knobs on this evidence set—only objective equivalence.
3. **The only differentiated candidate is objective, not aesthetic.** `harmonic.rank_filter.drop_uncertain` lowers Top-5 FP from `0.200` → `0.000` without a theory regression. That delta is already a ranking/policy signal for the #1022 decision memo (KEEP / DEFER / identify promotion candidate). A blinded pairwise study would not add a separate preference plane needed to interpret that metric.
4. **The frozen ranking fixture is synthetic relevance, not listening material.** Pairwise musical preference on synthetic key/BPM-labeled rows would either invent subjective labels or require an uncommitted private audio corpus. Issue #1020 forbids inventing preference data and forbids committing private audio; manufacturing a study here would violate both.
5. **Decision readiness for #1022 does not depend on layer C.** #1022 can recommend KEEP / DEFER / PROMOTION_CANDIDATE / NEED_MORE_EVIDENCE from theory, ranking, and upstream planes alone, with preference explicitly recorded as **inactive / not required** for this AQ6 bootstrap pass.

## What would make preference `REQUIRED` later (out of scope)

Re-open this plane only with an explicit Owner/Lead GO if a later candidate set produces **tied objective ranking macros** among musically distinct Top-K orderings on **real listening material**, where theory correctness is already PASS and graded relevance labels cannot decide. Until then, do not invent a preference corpus.

If revived, protocol must freeze **before** listening:

| Protocol element | Minimum freeze |
|---|---|
| Pairwise A/B | two named candidate configs; same query/candidate pool |
| Blinding | rater cannot see candidate_id / weight / filter identity |
| Sample-role slices | report by role/type separately; no universal preference claim |
| Order / randomization | fixed seed + counterbalanced presentation |
| Minimum support | declare n pairs and n raters before results |
| Reporting | pairwise win rate + agreement/disagreement; **never** convert preference into theory-correctness |
| Holdout hygiene | do not tune candidate weights on final preference holdout |

No such protocol was executed in this slice.

## Plane separation (normative)

| Plane | Authority in this slice |
|---|---|
| `aq6.theory` | cited closed; not remeasured; preference cannot override |
| `aq6.ranking` | cited from #1019; preference cannot retune weights/filters |
| `aq6.preference` | **gate only** → `NOT_REQUIRED`; no win-rate evidence recorded |
| Upstream key/BPM | remains an #1018 / #1022 concern; not preference |

## Non-goals

- no manufactured listening study / no invented preference labels
- no private audio committed / no host paths in evidence
- no production switch / no weight or filter promotion
- no UI / QML / key / BPM detector / ML changes
- no claim of universal musical preference
- no collapsing preference into theory or ranking scores

## Acceptance checklist

- [x] explicit `REQUIRED` vs `NOT_REQUIRED` gate is recorded → `NOT_REQUIRED`
- [x] no study invented when gate is `NOT_REQUIRED`
- [x] preference remains separate from theory/ranking correctness
- [x] disagreement/low support N/A (no raters) — absence is visible
- [x] no candidate tuned on preference holdout (no preference holdout exists)

## Exit vocabulary

Exactly one:

- `AQ6_HUMAN_PREFERENCE_NOT_REQUIRED`
- `AQ6_HUMAN_PREFERENCE_EVIDENCE_RECORDED`
- `AQ6_HUMAN_PREFERENCE_INSUFFICIENT_EVIDENCE`

This slice exits `AQ6_HUMAN_PREFERENCE_NOT_REQUIRED`.

## Follow-on write-head (out of scope here)

- [#1022](https://github.com/jannekbuengener/sample-brain/issues/1022) — evidence-backed AQ6 decision memo (theory + ranking + upstream; preference plane = not required)
