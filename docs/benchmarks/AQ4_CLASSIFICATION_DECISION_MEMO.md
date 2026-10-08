# AQ4 Classification Decision Memo (no production switch)

| Field | Value |
|---|---|
| Status | ACTIVE_SUPPORTING — evidence-backed classification decision; historical [#1036](https://github.com/jannekbuengener/sample-brain/issues/1036) preserved; residual [#1007](https://github.com/jannekbuengener/sample-brain/issues/1007) reconcile after [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) / [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006) |
| Class | ACTIVE_SUPPORTING |
| Parents | [#946](https://github.com/jannekbuengener/sample-brain/issues/946) (AQ4), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program) |
| Depends on (CLOSED) | [#1001](https://github.com/jannekbuengener/sample-brain/issues/1001) KPI, [#1021](https://github.com/jannekbuengener/sample-brain/issues/1021) synthetic corpus, [#1003](https://github.com/jannekbuengener/sample-brain/issues/1003) / [#1032](https://github.com/jannekbuengener/sample-brain/issues/1032) baseline, [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) diagnostics, [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006) residual candidate disposition, [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) historical compare, [#1036](https://github.com/jannekbuengener/sample-brain/issues/1036) historical decision |
| Related product / ownership (not AQ4 measurement authority) | [#936](https://github.com/jannekbuengener/sample-brain/issues/936) / `docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md`; [#171](https://github.com/jannekbuengener/sample-brain/issues/171) / [#173](https://github.com/jannekbuengener/sample-brain/issues/173); [#920](https://github.com/jannekbuengener/sample-brain/issues/920) / `docs/LOOP_ROW_PLAYBACK_CONTRACT.md` |

## Architecture outcome

### Historical [#1036](https://github.com/jannekbuengener/sample-brain/issues/1036) outcome (preserved)

```text
AQ4_CLASSIFICATION_DECISION_MEMO_RECORDED
```

Historical [#1036](https://github.com/jannekbuengener/sample-brain/issues/1036) recorded an evidence-backed keep-current recommendation from the then-available chain (contract → corpus → baseline → #1034 compare). That outcome remains historical truth. It is **not** reopened and is **not** declared wrong retrospectively.

### Residual [#1007](https://github.com/jannekbuengener/sample-brain/issues/1007) reconcile (after [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) / [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006))

```text
AQ4_CLASSIFICATION_DECISION_MEMO_RECORDED
```

This residual slice reconciles the full residual evidence chain after diagnostics and candidate disposition. It decides **`sample_class` and `pred_type` separately**, preserves consumer HOLDs and kNN HOLD, records **no production switch**, and states an explicit [#946](https://github.com/jannekbuengener/sample-brain/issues/946) parent disposition recommendation. It does **not** change classify/analyze algorithms, invent promotion gates, mandate ML, implement consumer safety gates, or collapse `sample_class` into `pred_type`.

## Evidence map

| Stage | Authority | Outcome token |
|---|---|---|
| KPI / Contract | [`AQ4_CLASSIFICATION_KPI_CONTRACT.md`](AQ4_CLASSIFICATION_KPI_CONTRACT.md) / [#1001](https://github.com/jannekbuengener/sample-brain/issues/1001) | `AQ4_CLASSIFICATION_KPI_CONTRACT_FROZEN` |
| Corpus | [`AQ4_CLASSIFICATION_CORPUS.md`](AQ4_CLASSIFICATION_CORPUS.md) / `sample-brain.aq4.classification.synthetic.v1` / [#1021](https://github.com/jannekbuengener/sample-brain/issues/1021) | `AQ4_CLASSIFICATION_CORPUS_FROZEN` |
| Baseline | [`AQ4_CLASSIFICATION_BASELINE.md`](AQ4_CLASSIFICATION_BASELINE.md) / [#1003](https://github.com/jannekbuengener/sample-brain/issues/1003) / [#1032](https://github.com/jannekbuengener/sample-brain/issues/1032) | `AQ4_CLASSIFICATION_BASELINE_MEASURED` |
| Diagnostics | [`AQ4_CLASSIFICATION_DIAGNOSTICS.md`](AQ4_CLASSIFICATION_DIAGNOSTICS.md) / [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) | `AQ4_CLASSIFICATION_DIAGNOSTICS_PARTIAL_HOLD` → `NO_JUSTIFIED_CANDIDATE_HYPOTHESIS` |
| Candidate compare / residual disposition | [`AQ4_CLASSIFICATION_CANDIDATE_COMPARE.md`](AQ4_CLASSIFICATION_CANDIDATE_COMPARE.md) / [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) + [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006) | historical `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE`; residual `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_NO_JUSTIFIED_CANDIDATE` |
| Decision | this document / [#1036](https://github.com/jannekbuengener/sample-brain/issues/1036) + [#1007](https://github.com/jannekbuengener/sample-brain/issues/1007) | historical + residual `AQ4_CLASSIFICATION_DECISION_MEMO_RECORDED` |

Flow:

```text
KPI
→ CORPUS
→ BASELINE
→ DIAGNOSTICS
→ CANDIDATE COMPARE / RESIDUAL DISPOSITION
→ DECISION
```

Decisions cite those surfaces only; anecdotes and private library checks are out of band. No new evidence source is invented in this slice.

## Historical chain roles (#1034 / #1036 / #1005 / #1006 / #1007)

| Slice | Role |
|---|---|
| [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) | Historical reproducible thin-adapter compare (`AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE`) |
| [#1036](https://github.com/jannekbuengener/sample-brain/issues/1036) | Historical decision from then-available contract/corpus/baseline/compare chain |
| [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) | Adds missing diagnostics plane (`PARTIAL_HOLD` + `NO_JUSTIFIED_CANDIDATE_HYPOTHESIS`) |
| [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006) | Adds residual `NO_JUSTIFIED_CANDIDATE` disposition (no new candidates) |
| [#1007](https://github.com/jannekbuengener/sample-brain/issues/1007) | Final residual reconciliation: per-plane tokens + #946 disposition recommendation |

New residual evidence **precises** the decision; it does **not** falsify closed historical slices.

## Partition / no-tuning-on-TEST

| Corpus `split` | AQ4 role | Decision use |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration narrative only |
| `TEST` | TEST / HOLDOUT | frozen evidence report; **no threshold discovery / no tuning** |

Inherited from the KPI contract and restated in corpus, baseline, diagnostics, and compare. This memo does not invent gates from TEST/HOLDOUT.

## Taxonomy separation (normative, inherited)

1. **`sample_class` (loop/oneshot) and `pred_type` / semantic tags remain separate taxonomies and separate reporting planes** (`aq4.sample_class` vs `aq4.pred_type` / `aq4.pred_type_rule`).
2. Correct `pred_type` does **not** imply correct `sample_class` (and vice versa).
3. Do **not** collapse the two into one label space for gates, baselines, portable `domain` tokens, or this recommendation.
4. Baseline paths stay reported separately: duration-only `sample_class`, rule-only `pred_type`, and optional kNN-override `pred_type` (kNN remains HOLD) — never a blended “autotype quality” score.
5. Descriptor companions (`Bright`, `Dark`, …) are not a third collapsed taxonomy with `sample_class`.
6. **Recommendation tokens are decided per plane** — not one global token for both.

## Synthetic corpus limits vs human-labeled public HOLD

`sample-brain.aq4.classification.synthetic.v1` is a **small deterministic synthetic** GT set (`label_source=synthetic_deterministic`, 10 clips, seed `1021001`). It is:

- deterministic;
- reproducible;
- small;
- thin per semantic class (often `n=1`).

It unblocks measurable baselines; it is **not** a substitute for a human-labeled public/sanitized corpus.

| Limit | Status |
|---|---|
| Active clear coverage | thin per-class support (often 1 clip per semantic label) |
| Ambiguous / unknown | retained as uncertain; excluded from clear-label denominators |
| `aq4.pred_type_knn` | HOLD — no seed embeddings / private paths on synthetic corpus |
| Human-labeled public/sanitized corpus | HOLD — separate from synthetic id |
| Confidence / calibration curves | HOLD — per KPI contract |
| Descriptor multi-label GT | HOLD — not primary GT in corpus v1 |
| Durable consumer FP-rate gates | HOLD / PARTIAL_HOLD per diagnostics |

Do **not** derive from this corpus:

- human-grade accuracy;
- production safety thresholds;
- belastbare per-class FP-Rates;
- real library coverage.

## Per-plane recommendations (#1007)

Token vocabulary (exactly one per plane):

```text
KEEP_CURRENT_BASELINE_PATH
DEFER_PROMOTION
PROMOTION_CANDIDATE_IDENTIFIED
NEED_MORE_EVIDENCE
```

Semantics:

| Token | Means | Does **not** mean |
|---|---|---|
| `KEEP_CURRENT_BASELINE_PATH` | Current production baseline remains the best-supported available path | Quality is sufficient or consumer-safe |
| `NEED_MORE_EVIDENCE` | Current evidence is insufficient for a stronger AQ4 semantic-type decision | Immediate production rewrite (path stays until a later authorized change) |
| `PROMOTION_CANDIDATE_IDENTIFIED` | Live evidence identifies a justified promotion candidate | Adapter existence alone (#1034) |
| `DEFER_PROMOTION` | Promotion deferred while a candidate remains under consideration | Used here (no promotion candidate) |

### `sample_class` recommendation

```text
SAMPLE_CLASS RECOMMENDATION:
KEEP_CURRENT_BASELINE_PATH
```

**Why:**

1. Clear CALIBRATION/TEST show **no measured** loop↔oneshot misses on the frozen synthetic corpus (`macro-F1` / bal-acc saturated at 1.0 on clear-eligible clips).
2. [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) duration adapters (`oneshot_max` 1.0 / 1.5) deliver **no proven advantage** over `classification.baseline.v1`.
3. [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) / [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006) provide no justified duration retune / new sample_class candidate.
4. Thin corpus and Rack `HOLD_INSUFFICIENT_SUPPORT` remain — this token is **not** “sample_class is proven safe.”

### `pred_type` recommendation

```text
PRED_TYPE RECOMMENDATION:
NEED_MORE_EVIDENCE
```

**Why:**

1. Measured clear misses remain: `Drum Loop → Loop`, `Pad → Drone`, `Impact → Snare` (support typically `n=1`).
2. [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) exits `AQ4_CLASSIFICATION_DIAGNOSTICS_PARTIAL_HOLD` with candidate guidance `NO_JUSTIFIED_CANDIDATE_HYPOTHESIS`.
3. [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006) exits `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_NO_JUSTIFIED_CANDIDATE` — no new bake-off identity justified.
4. Thin #1034 adapters do **not** recover those misses; adapter existence is not a promotion candidate.
5. Human-labeled public/sanitized corpus remains HOLD. Current evidence is insufficient for a stronger AQ4 semantic-type quality decision.

Production path note: until a later authorized product change, the current rule `pred_type` path remains the factual runtime default. `NEED_MORE_EVIDENCE` records the decision-plane insufficiency; it is **not** a silent production rewrite and **not** `PROMOTION_CANDIDATE_IDENTIFIED`.

### Tokens considered and not chosen

| Token | Plane | Why not |
|---|---|---|
| `PROMOTION_CANDIDATE_IDENTIFIED` | either | Forbidden by binding #1005/#1006 `NO_JUSTIFIED_CANDIDATE` upstream evidence |
| `DEFER_PROMOTION` | either | No promotion candidate under consideration |
| `KEEP_CURRENT_BASELINE_PATH` | `pred_type` | Would understate residual semantic-type evidence gaps after diagnostics/disposition |
| `NEED_MORE_EVIDENCE` | `sample_class` | Clear plane has a supported keep-current path among tested adapters; thin-corpus HOLDs are recorded separately |

```text
NEW PROMOTION CANDIDATE:
NONE

PRODUCTION CHANGE:
NONE
```

## Explicit non-action (this slice)

- **No production default change** (no switch of `_duration_class` / oneshot threshold, `rule_type` knobs, or related classify/analyze defaults).
- No classify / analyze algorithm changes.
- No ML mandate / new embedding models.
- No numeric promotion thresholds / gates invented from TEST/HOLDOUT.
- **No consumer safety-gate implementation** (Rack / auto-metadata / auto-loop / auto-attack remain owned elsewhere).
- No collapse of `sample_class` into `pred_type`.
- No private audio or absolute host paths in committed artifacts.
- No reopen of closed [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) / [#1036](https://github.com/jannekbuengener/sample-brain/issues/1036) / [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) / [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006).
- No mutation of parent [#946](https://github.com/jannekbuengener/sample-brain/issues/946) in this slice (recommendation only).
- No [#1040](https://github.com/jannekbuengener/sample-brain/issues/1040) / [#1097](https://github.com/jannekbuengener/sample-brain/issues/1097) automation work.

## kNN

```text
KNN:
HOLD
```

Optional kNN override was **not** reproducibly evaluated on the synthetic corpus (no seed embeddings / private library paths). Do not confuse “not selected” with “measured worse.” No ML mandate. No seed reconstruction.

## Consumer HOLDs (preserved — not aggregated away)

Classification evidence ≠ architecture authority ≠ consumer implementation. Ownership stays with existing issues/contracts. This memo does **not** implement gates.

| Consumer | Gate status | Notes |
|---|---|---|
| Rack playback eligibility | `HOLD_INSUFFICIENT_SUPPORT` | clear `sample_class` saturated on thin corpus ≠ consumer-safe |
| auto-loop | `PARTIAL_HOLD` | measured `pred_type` misses with `n=1`; behavior delta limited for some pairs |
| auto-attack / auto-metadata | `PARTIAL_HOLD` | Impact→Snare / unknown→Snare risk; FP rates HOLD |
| Filename/folder as silent playback authority | `NOT_APPLICABLE` (policy) | disallowed success path per KPI + #936 |

```text
CONSUMER SAFETY:
NOT PROVEN
```

A keep-current / no-justified-candidate decision is **not** a consumer-safety proof.

## AQ4 PARENT DISPOSITION RECOMMENDATION

Recommendation for parent [#946](https://github.com/jannekbuengener/sample-brain/issues/946) from this evidence (exactly one):

```text
AQ4 PARENT DISPOSITION:
CLOSE_AQ4_MEASUREMENT_CAMPAIGN
```

**Why:**

1. The AQ4 measurement chain is complete and reconciled: KPI → CORPUS → BASELINE → DIAGNOSTICS → CANDIDATE COMPARE / RESIDUAL DISPOSITION → DECISION.
2. Per-plane recommendations are explicit (`sample_class` keep-current; `pred_type` need-more-evidence).
3. Residual outcomes from [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005) / [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006) are consumed; no justified promotion candidate remains.
4. Consumer HOLDs and kNN HOLD are visible, not erased.
5. Closing the measurement campaign means the **evidence/decision criterion** for AQ4 is answered — not that classification quality or consumer safety is proven.

```text
AQ4 measurement campaign complete
≠
automated quality loop complete
```

[#1040](https://github.com/jannekbuengener/sample-brain/issues/1040) / [#1097](https://github.com/jannekbuengener/sample-brain/issues/1097) remain out of scope. This memo **does not close #946**; Owner decides after live verification of [#1007](https://github.com/jannekbuengener/sample-brain/issues/1007).

Alternative considered and not chosen: `DEFER_AQ4_PARENT_INSUFFICIENT_EVIDENCE` — the decision question itself is answerable with the residual chain; remaining HOLDs are recorded outcomes, not blockers to recording the campaign decision.

## Decision rollup

```text
SAMPLE_CLASS RECOMMENDATION:
KEEP_CURRENT_BASELINE_PATH

PRED_TYPE RECOMMENDATION:
NEED_MORE_EVIDENCE

PRODUCTION CHANGE:
NONE

NEW PROMOTION CANDIDATE:
NONE

KNN:
HOLD

CONSUMER SAFETY:
NOT PROVEN

AQ4 PARENT DISPOSITION:
CLOSE_AQ4_MEASUREMENT_CAMPAIGN
```

## Exit vocabulary

Exactly one for [#1007](https://github.com/jannekbuengener/sample-brain/issues/1007):

- `AQ4_CLASSIFICATION_DECISION_MEMO_RECORDED`
- `AQ4_CLASSIFICATION_DECISION_INSUFFICIENT_EVIDENCE`

This residual slice exits `AQ4_CLASSIFICATION_DECISION_MEMO_RECORDED`: the decision question is fully answerable with separate plane tokens, historical [#1036](https://github.com/jannekbuengener/sample-brain/issues/1036) truth preserved, #1005/#1006 outcomes consumed, consumer/kNN HOLDs visible, no production switch, and #946 disposition recommended (not mutated). A plane-level `NEED_MORE_EVIDENCE` token does **not** force the insufficient-evidence exit when the decision itself is clear and complete.
