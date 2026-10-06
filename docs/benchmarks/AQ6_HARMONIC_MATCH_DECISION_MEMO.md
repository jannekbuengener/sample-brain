# AQ6 Harmonic Match Decision Memo (no production switch)

**Status:** ACTIVE_SUPPORTING — evidence-backed Harmonic Match decision for [#1022](https://github.com/jannekbuengener/sample-brain/issues/1022)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#948](https://github.com/jannekbuengener/sample-brain/issues/948) (AQ6), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED):** [#1015](https://github.com/jannekbuengener/sample-brain/issues/1015) theory contract, [#1016](https://github.com/jannekbuengener/sample-brain/issues/1016) ranking benchmark, [#1017](https://github.com/jannekbuengener/sample-brain/issues/1017) theory baseline, [#1018](https://github.com/jannekbuengener/sample-brain/issues/1018) ranking/upstream baseline, [#1019](https://github.com/jannekbuengener/sample-brain/issues/1019) candidate compare (PR [#1048](https://github.com/jannekbuengener/sample-brain/pull/1048) / `b1cf8a46`), [#1020](https://github.com/jannekbuengener/sample-brain/issues/1020) preference gate (PR [#1049](https://github.com/jannekbuengener/sample-brain/pull/1049) / `692bef42`)  
**Upstream consume-only (do not reopen):** closed AQ1 [#943](https://github.com/jannekbuengener/sample-brain/issues/943), AQ2 [#944](https://github.com/jannekbuengener/sample-brain/issues/944)

## Architecture outcome

```text
AQ6_HARMONIC_MATCH_DECISION_MEMO_RECORDED
```

```text
recommendation=KEEP_CURRENT_BASELINE_PATH
preference_plane=NOT_REQUIRED
production_switch=false
```

This memo records an **evidence-backed product recommendation** for AQ6 Harmonic Match path choices from frozen upstream docs. It does **not** change relation rules, ranking weights (`0.75` / `0.25`), UI/QML, key/BPM detectors, embeddings/ML, or production defaults. Theory, ranking, upstream, and preference remain **separate evidence planes**.

## Evidence map

| Stage | Authority | Outcome token |
|---|---|---|
| Theory contract | [`AQ6_HARMONIC_MATCH_THEORY_KPI_CONTRACT.md`](AQ6_HARMONIC_MATCH_THEORY_KPI_CONTRACT.md) | `AQ6_THEORY_TRUTH_TABLE_CONTRACT_FROZEN` |
| Ranking contract | [`AQ6_HARMONIC_MATCH_RANKING_RELEVANCE_CONTRACT.md`](AQ6_HARMONIC_MATCH_RANKING_RELEVANCE_CONTRACT.md) | `AQ6_RANKING_RELEVANCE_BENCHMARK_FROZEN` |
| Theory baseline | [`AQ6_HARMONIC_MATCH_THEORY_BASELINE.md`](AQ6_HARMONIC_MATCH_THEORY_BASELINE.md) | `AQ6_THEORY_BASELINE_MEASURED` |
| Ranking + upstream baseline | [`AQ6_HARMONIC_MATCH_RANKING_BASELINE.md`](AQ6_HARMONIC_MATCH_RANKING_BASELINE.md) | `AQ6_RANKING_BASELINE_AND_UPSTREAM_DELTA_MEASURED` |
| Candidate compare | [`AQ6_HARMONIC_MATCH_RANKING_CANDIDATE_COMPARE.md`](AQ6_HARMONIC_MATCH_RANKING_CANDIDATE_COMPARE.md) | `AQ6_HARMONIC_CANDIDATE_COMPARE_REPRODUCIBLE` |
| Preference gate | [`AQ6_HARMONIC_MATCH_HUMAN_PREFERENCE_GATE.md`](AQ6_HARMONIC_MATCH_HUMAN_PREFERENCE_GATE.md) | `AQ6_HUMAN_PREFERENCE_NOT_REQUIRED` |

Flow: **theory contract → ranking contract → theory baseline → ranking/upstream baseline → compare → preference gate → this decision**. Decisions cite those six surfaces only; anecdotes and private library checks are out of band.

## Partition / no-tuning-on-TEST

| Fixture `partition` | AQ6 role | Decision use |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration narrative only |
| `TEST` | TEST | frozen evidence report; **no threshold discovery / no tuning** |
| `HOLDOUT` | HOLDOUT | frozen evidence report; **no threshold discovery / no tuning** |

Inherited from the ranking contract and restated in baseline + compare. This memo does not invent gates from TEST/HOLDOUT.

## Plane separation (normative, inherited)

1. **`aq6.theory`** — deterministic relation / compatibility / pitch-shift correctness against the frozen truth table. Ranking scores must never excuse theory failures.
2. **`aq6.ranking`** — graded relevance (Precision@K / MRR@K / NDCG@K / Top-K FP) on the frozen synthetic relevance fixture. Theory-incompatible items in Top-K are reported separately, not folded into ranking macros.
3. **Upstream key/mode/BPM** — quality-loss attribution when injected evidence is missing or wrong (#1018). Owned as propagation accounting; AQ6 does not own key/BPM detectors (AQ1/AQ2 consume-only).
4. **`aq6.preference`** — optional subjective plane. Recorded **`NOT_REQUIRED`** for this bootstrap pass (#1020); no listening study; preference must never rewrite theory truth or retune ranking on holdout.

Do **not** collapse these into one opaque “Harmonic Match quality” score for gates, baselines, portable `domain` tokens, or this recommendation.

## Theory plane summary (`aq6.theory`)

| Evidence | Result |
|---|---|
| Truth table coverage | 584/584 cells; 12 roots × maj/min + fail-closed evidence cells |
| Relation classification accuracy | 1.000 |
| Incompatible false-positive rate | 0.000 |
| Compatible false-negative rate | 0.000 |
| Pitch-shift / transposition invariance | PASS (0 violations) |
| Evidence fail-closed | PASS (8/8) |
| BPM isolation of theory fields | PASS |

Current product `rate_harmony` / `determine_relation` matches the frozen #1015 contract on the exhaustive table. No theory regression is available to trade for ranking gains.

## Ranking + upstream plane summary (`aq6.ranking`)

| Evidence | Result |
|---|---|
| As-labeled P@1 / MRR@5 / NDCG@5 | 1.000 / 1.000 / 1.000 (4 scored queries) |
| As-labeled Top-5 FP | 0.200 |
| `missing_candidate_key` P@1 delta | −0.250 |
| `wrong_candidate_key` P@1 delta | −1.000 |
| Missing-evidence forced-compatible guard | PASS |
| Fixture scale | thin synthetic (`sample-brain.aq6.harmonic-ranking.relevance.v1`; 5 queries) |

With correct labeled key/mode evidence, relation-priority ranking places a relevant item first. Upstream wrong keys collapse ranking quality without inventing compatible relations. Top-5 FP / Precision@5 soft spots on this thin set are ranking/policy signals, **not** theory failures.

## Candidate compare summary (#1019)

| Candidate | Theory gate | TEST/HOLDOUT ranking vs baseline |
|---|---|---|
| `harmonic.baseline.v1` (`0.75`/`0.25`) | PASS | anchor |
| `harmonic.weights.harmony_0.90_bpm_0.10` | PASS | ties baseline macros |
| `harmonic.weights.harmony_1.00_bpm_0.00` | PASS | ties baseline macros |
| `harmonic.rank_filter.drop_uncertain` | PASS | Top-5 FP 0.200 → 0.000; still **not** promoted in #1019 |

Weight-only adapters do not move macros on this fixture (relation-priority sort dominates). `drop_uncertain` is an objective FP reduction without a theory regression, but remains an adapter observation on a thin synthetic set — **not** an authorized production default change in this evidence pack.

## Preference plane (`aq6.preference`)

```text
AQ6_HUMAN_PREFERENCE_NOT_REQUIRED
```

#1020 recorded `NOT_REQUIRED`: no material unresolved preference question after #1019; weight candidates objectively tie; the only differentiated candidate is already an objective ranking/policy signal; manufacturing a listening study on synthetic rows would invent preference labels. Preference stays inactive for this AQ6 bootstrap decision.

## Recommendation

```text
KEEP_CURRENT_BASELINE_PATH
```

**Justification (brief):**

1. **Frozen theory contract + measured baseline** show the current relation path is exhaustive-table correct (accuracy 1.000; zero incompatible FPs; fail-closed intact) ([`AQ6_HARMONIC_MATCH_THEORY_KPI_CONTRACT.md`](AQ6_HARMONIC_MATCH_THEORY_KPI_CONTRACT.md), [`AQ6_HARMONIC_MATCH_THEORY_BASELINE.md`](AQ6_HARMONIC_MATCH_THEORY_BASELINE.md)). Ranking gains cannot override that plane.
2. **Ranking contract + baseline** record usable as-labeled macros and explicit upstream-error propagation; missing/wrong key evidence is the dominant quality risk, not the current `0.75`/`0.25` weights themselves ([`AQ6_HARMONIC_MATCH_RANKING_RELEVANCE_CONTRACT.md`](AQ6_HARMONIC_MATCH_RANKING_RELEVANCE_CONTRACT.md), [`AQ6_HARMONIC_MATCH_RANKING_BASELINE.md`](AQ6_HARMONIC_MATCH_RANKING_BASELINE.md)).
3. **Candidate compare** shows weight adapters do **not** dominate `harmonic.baseline.v1`, and `drop_uncertain` is a non-promoted adapter observation on a thin synthetic fixture — not a production switch proof ([`AQ6_HARMONIC_MATCH_RANKING_CANDIDATE_COMPARE.md`](AQ6_HARMONIC_MATCH_RANKING_CANDIDATE_COMPARE.md)).
4. **Preference** is explicitly `NOT_REQUIRED` and must not be manufactured to justify a path change ([`AQ6_HARMONIC_MATCH_HUMAN_PREFERENCE_GATE.md`](AQ6_HARMONIC_MATCH_HUMAN_PREFERENCE_GATE.md)).

**Adapter / bake-off limits:** #1019 used thin weight / post-rank filter adapters over the same `find_harmony_matches` surface. It does **not** evaluate new relation-rule backends, ML rankers, live key/BPM detector changes, UI paths, or production default switches. Adapter knobs alone do not justify a production default change.

Alternative tokens considered and **not** chosen:

- `DEFER_PROMOTION` — redundant with keep-current once no candidate is promoted and production stays on the measured baseline path (`0.75` / `0.25`, current relation semantics).
- `NEED_FURTHER_CANDIDATES` — may apply later if product quality work targets richer ranking fixtures, uncertain-filter policy as a separately scoped test-first behavior issue, or upstream key/BPM claimability improvements outside AQ6; it is not required to record this keep-current decision from the existing six-doc chain.

Issue #1022 also lists `PROMOTION_CANDIDATE_IDENTIFIED` / `NEED_MORE_EVIDENCE`; neither fits: no candidate is identified for production promotion, and the evidence pack is sufficient to record keep-current without inventing further candidates or preference data.

## Unresolved uncertainty / HOLDs (visible)

| Uncertainty | Status | Notes |
|---|---|---|
| Upstream key/mode claimability | consume AQ2 | Wrong/missing keys collapse ranking (#1018); not owned by AQ6 |
| BPM secondary evidence | consume AQ1 | Missing reference BPM abstains; secondary only; not theory truth |
| Ranking fixture scale | thin synthetic | Keep-current applies to frozen `relevance.v1`; not a claim of library-wide ranking quality |
| `drop_uncertain` as product policy | deferred | Objective FP drop observed; requires separate test-first feature/behavior issue + Settings toggle if exposed |
| Human preference | `NOT_REQUIRED` | Re-open only with Owner/Lead GO on real listening material |
| Continuous opaque fusion of theory+ranking | disallowed | Remain separate planes forever for gates |

## Explicit non-action (this slice)

- **No production default change** (no switch of harmony/BPM weights, relation scores, or uncertain-filter policy).
- No ranking-weight / relation-rule algorithm changes.
- No UI / QML / key / BPM detector / ML changes.
- No numeric promotion thresholds / gates invented from TEST/HOLDOUT.
- No preference study manufactured.
- No private audio or absolute host paths in committed artifacts.
- Any future production relation/weight/filter behavior change is a **separate** test-first feature/behavior issue; if exposed as new functional behavior, it must satisfy the Bootloader Settings toggle contract.

## Machine-consumable decision tokens (#1040-facing)

```text
exit_status=AQ6_HARMONIC_MATCH_DECISION_MEMO_RECORDED
recommendation=KEEP_CURRENT_BASELINE_PATH
production_switch=false
preference_plane=NOT_REQUIRED
baseline_candidate_id=harmonic.baseline.v1
weights_harmony=0.75
weights_bpm=0.25
theory_fixture=sample-brain.aq6.harmonic-theory.truth-table.v1
ranking_fixture=sample-brain.aq6.harmonic-ranking.relevance.v1
compare_document_type=sample-brain.aq6.harmonic-ranking-candidate-compare.v1
no_tuning_on_test=true
```

Human-readable prose above is a view over this evidence pack; long-term #1040 should consume tokens/artifacts rather than re-deriving music-theory semantics from memo text alone.

## Exit vocabulary

Exactly one:

- `AQ6_HARMONIC_MATCH_DECISION_MEMO_RECORDED`
- `AQ6_HARMONIC_MATCH_DECISION_INSUFFICIENT_EVIDENCE`

This slice exits `AQ6_HARMONIC_MATCH_DECISION_MEMO_RECORDED` with recommendation `KEEP_CURRENT_BASELINE_PATH`, theory vs ranking vs upstream vs preference planes kept separate, preference `NOT_REQUIRED`, thin-fixture / upstream HOLDs visible, and no production switch.
