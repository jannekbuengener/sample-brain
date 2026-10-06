# AQ4 Classification Decision Memo (no production switch)

**Status:** ACTIVE_SUPPORTING — evidence-backed classification decision for [#1036](https://github.com/jannekbuengener/sample-brain/issues/1036)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#946](https://github.com/jannekbuengener/sample-brain/issues/946) (AQ4), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED):** [#1001](https://github.com/jannekbuengener/sample-brain/issues/1001) KPI contract, [#1021](https://github.com/jannekbuengener/sample-brain/issues/1021) synthetic corpus, [#1032](https://github.com/jannekbuengener/sample-brain/issues/1032) classification baseline, [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) candidate compare (PR [#1035](https://github.com/jannekbuengener/sample-brain/pull/1035))  
**Related product / ownership (not AQ4 measurement authority):** [#936](https://github.com/jannekbuengener/sample-brain/issues/936) / `docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md` (Rack user-channel resolver); [#171](https://github.com/jannekbuengener/sample-brain/issues/171) / [#173](https://github.com/jannekbuengener/sample-brain/issues/173) (auto-metadata consumers); [#920](https://github.com/jannekbuengener/sample-brain/issues/920) / `docs/LOOP_ROW_PLAYBACK_CONTRACT.md` (loop-row playback that *consumes* `sample_class`).

## Architecture outcome

```text
AQ4_CLASSIFICATION_DECISION_MEMO_RECORDED
```

This memo records an **evidence-backed product recommendation** for AQ4 sample_class / pred_type path choices from frozen upstream docs. It does **not** change classify/analyze algorithms, set numeric promotion gates, switch production defaults, mandate ML, implement consumer safety gates, or collapse `sample_class` into `pred_type`.

## Evidence map

| Stage | Authority | Outcome token |
|---|---|---|
| Contract | [`AQ4_CLASSIFICATION_KPI_CONTRACT.md`](AQ4_CLASSIFICATION_KPI_CONTRACT.md) | `AQ4_CLASSIFICATION_KPI_CONTRACT_FROZEN` |
| Corpus | [`AQ4_CLASSIFICATION_CORPUS.md`](AQ4_CLASSIFICATION_CORPUS.md) / `sample-brain.aq4.classification.synthetic.v1` | `AQ4_CLASSIFICATION_CORPUS_FROZEN` |
| Baseline | [`AQ4_CLASSIFICATION_BASELINE.md`](AQ4_CLASSIFICATION_BASELINE.md) | `AQ4_CLASSIFICATION_BASELINE_MEASURED` |
| Candidate compare | [`AQ4_CLASSIFICATION_CANDIDATE_COMPARE.md`](AQ4_CLASSIFICATION_CANDIDATE_COMPARE.md) | `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE` |

Flow: **contract → corpus → baseline → compare → this decision**. Decisions cite those four surfaces only; anecdotes and private library checks are out of band.

## Partition / no-tuning-on-TEST

| Corpus `split` | AQ4 role | Decision use |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration narrative only |
| `TEST` | TEST / HOLDOUT | frozen evidence report; **no threshold discovery / no tuning** |

Inherited from the KPI contract and restated in corpus, baseline, and compare. This memo does not invent gates from TEST/HOLDOUT.

## Taxonomy separation (normative, inherited)

1. **`sample_class` (loop/oneshot) and `pred_type` / semantic tags remain separate taxonomies and separate reporting planes** (`aq4.sample_class` vs `aq4.pred_type` / `aq4.pred_type_rule`).
2. Correct `pred_type` does **not** imply correct `sample_class` (and vice versa).
3. Do **not** collapse the two into one label space for gates, baselines, portable `domain` tokens, or this recommendation.
4. Baseline paths stay reported separately: duration-only `sample_class`, rule-only `pred_type`, and optional kNN-override `pred_type` (kNN remains HOLD) — never a blended “autotype quality” score.
5. Descriptor companions (`Bright`, `Dark`, …) are not a third collapsed taxonomy with `sample_class`.

## Synthetic corpus limits vs human-labeled public HOLD

`sample-brain.aq4.classification.synthetic.v1` is a **small deterministic synthetic** GT set (`label_source=synthetic_deterministic`, 10 clips, seed `1021001`). It unblocks measurable baselines; it is **not** a substitute for a human-labeled public/sanitized corpus.

| Limit | Status |
|---|---|
| Active clear coverage | thin per-class support (often 1 clip per semantic label) |
| Ambiguous / unknown | retained as uncertain; excluded from clear-label denominators |
| `aq4.pred_type_knn` | HOLD — no seed embeddings / private paths on synthetic corpus |
| Human-labeled public/sanitized corpus | HOLD — separate from synthetic id |
| Confidence / calibration curves | HOLD — per KPI contract |
| Descriptor multi-label GT | HOLD — not primary GT in corpus v1 |

Synthetic keep-current evidence therefore applies to controlled clips under the frozen corpus identity. It does **not** claim human-grade classification quality on real libraries, nor authorize consumer FP gates from this thin material.

## Recommendation

```text
KEEP_CURRENT_BASELINE_PATH
```

**Justification (brief):**

1. **Frozen contract** separates `sample_class` / `pred_type`, partitions CALIBRATION vs TEST/HOLDOUT, keeps confidence HOLD, and lists consumer safety gates as future dependents only ([`AQ4_CLASSIFICATION_KPI_CONTRACT.md`](AQ4_CLASSIFICATION_KPI_CONTRACT.md)).
2. **Synthetic corpus + measured baseline** record the current surfaces (`_duration_class` / `clazz`, `rule_type`) on `sample-brain.aq4.classification.synthetic.v1` with separate planes and explicit uncertain accounting; clear `sample_class` is saturated (macro-F1 1.0) while rule `pred_type` shows known thin-corpus misses (Pad→Drone, Drum Loop→Loop on CALIBRATION; Impact→Snare on TEST) ([`AQ4_CLASSIFICATION_CORPUS.md`](AQ4_CLASSIFICATION_CORPUS.md), [`AQ4_CLASSIFICATION_BASELINE.md`](AQ4_CLASSIFICATION_BASELINE.md)).
3. **Candidate compare** on frozen TEST shows thin duration (`oneshot_max` 1.0 / 1.5) and brightness (`bright_min=4000`) adapters do **not** dominate `classification.baseline.v1` across both planes: clear `sample_class` stays 1.0, and the known pred_type misses are unchanged ([`AQ4_CLASSIFICATION_CANDIDATE_COMPARE.md`](AQ4_CLASSIFICATION_CANDIDATE_COMPARE.md) tables + non-promotional observation). CALIBRATION-only narrative is not a production promotion proof.

**Adapter / bake-off limits:** the #1034 compare used thin keyword overrides over the **same** baseline surfaces (oneshot duration boundary; `rule_type` brightness knob). It does **not** evaluate new classify/analyze backends, ML/embedding models, kNN seed sets, production default changes, or consumer gate wiring. Adapter knobs alone do not justify a production default change.

Alternative tokens considered and **not** chosen:

- `DEFER_PROMOTION` — redundant with keep-current once no candidate is promoted and production stays on the measured baseline path.
- `NEED_FURTHER_CANDIDATES` — may apply later if product quality work targets richer semantic rules, measured kNN with public seeds, human-labeled public corpus adoption, or new classify backends; it is not required to record this keep-current decision from the existing four-doc chain.

## Explicit non-action (this slice)

- **No production default change** (no switch of `_duration_class` / oneshot threshold, `rule_type` knobs, or related classify/analyze defaults).
- No classify / analyze algorithm changes.
- No ML mandate / new embedding models.
- No numeric promotion thresholds / gates invented from TEST/HOLDOUT.
- **No consumer safety-gate implementation** (Rack / auto-metadata / auto-loop / auto-attack remain future dependents; list only).
- No collapse of `sample_class` into `pred_type`.
- No private audio or absolute host paths in committed artifacts.

## Consumer gates — future dependents only

Inherited from the KPI contract dependency notice (not owned or implemented here):

| Consumer / risk | Why AQ4 evidence matters | Ownership remains |
|---|---|---|
| Rack playback eligibility / point-trigger vs loop-row | wrong `sample_class` can change audible playback path | #936 / #920 / Rack runtime issues |
| Auto-metadata classification consumers | wrong `pred_type` / tags pollute browsing and export metadata | #171 / #173 (and related) |
| Auto-loop / auto-attack adjacent flows | false-positive structural or semantic class can trigger unsafe automation | product/architecture issues that consume AQ4; not this memo |
| Filename/folder text as playback authority | explicitly **disallowed** as a silent success path | #936 authority + AQ4 guardrail |

List = dependency notice only. This memo does **not** set FP thresholds, wire gates, or authorize consumer default changes.

## Exit vocabulary

Exactly one:

- `AQ4_CLASSIFICATION_DECISION_MEMO_RECORDED`
- `AQ4_CLASSIFICATION_DECISION_INSUFFICIENT_EVIDENCE`

This slice exits `AQ4_CLASSIFICATION_DECISION_MEMO_RECORDED` with recommendation `KEEP_CURRENT_BASELINE_PATH`, taxonomy separation preserved, synthetic-corpus limits and HOLD stubs acknowledged, consumer gates future-only, and no production switch.
