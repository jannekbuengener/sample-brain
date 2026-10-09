# AQ7 Structure / Role / Drop Diagnostics — Error Buckets (Task 1 WIP)

**Status:** WIP / ACTIVE_SUPPORTING — Task-1 evidence extraction for [#1027](https://github.com/jannekbuengener/sample-brain/issues/1027)
**Class:** ACTIVE_SUPPORTING (Task-1 partial; candidate hypotheses deferred)
**Parents:** [#949](https://github.com/jannekbuengener/sample-brain/issues/949) (AQ7), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)
**Depends on (CLOSED):** [#1023](https://github.com/jannekbuengener/sample-brain/issues/1023) KPI, [#1024](https://github.com/jannekbuengener/sample-brain/issues/1024) corpus, [#1025](https://github.com/jannekbuengener/sample-brain/issues/1025) boundary baseline, [#1026](https://github.com/jannekbuengener/sample-brain/issues/1026) role/drop baseline
**Normative KPI:** [`AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md`](AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md)
**Corpus:** [`AQ7_STRUCTURE_ROLE_DROP_CORPUS.md`](AQ7_STRUCTURE_ROLE_DROP_CORPUS.md) / `sample-brain.aq7.structure-role-drop.synthetic.v1`
**Boundary baseline:** [`AQ7_STRUCTURE_BOUNDARY_BASELINE.md`](AQ7_STRUCTURE_BOUNDARY_BASELINE.md) / `structure_v1.baseline.v1`
**Role/drop baseline:** [`AQ7_STRUCTURE_ROLE_DROP_BASELINE.md`](AQ7_STRUCTURE_ROLE_DROP_BASELINE.md) / `arrangement_classifier.baseline.v1`
**Style reference:** [`AQ4_CLASSIFICATION_DIAGNOSTICS.md`](AQ4_CLASSIFICATION_DIAGNOSTICS.md) (taxonomy separation; not a plane merge)

## Architecture outcome (Task 1)

```text
AQ7_1027_BUCKET_ANALYSIS_READY
```

This document turns the measured #1025 / #1026 baselines into **explainable failure buckets** with plane firewalls, HOLD honesty, and dominant ranking. It does **not** change StructureV1 / ArrangementClassifier / SectionSignals, retune thresholds, invent candidate hypotheses for #1028, update `CANON_INDEX`, or switch production defaults.

Task-1 scope is evidence extraction only. Final candidate hypotheses remain deferred.

---

## 1. Scope / Evidence Chain

| Item | Value |
|---|---|
| Corpus id | `sample-brain.aq7.structure-role-drop.synthetic.v1` |
| `corpus_version` | `1.0.0` |
| Boundary candidate | `structure_v1.baseline.v1` |
| Role/drop candidate | `arrangement_classifier.baseline.v1` |
| Boundary exit (frozen harness) | `AQ7_STRUCTURE_BOUNDARY_BASELINE_PARTIAL_HOLD` |
| Role/drop exit (frozen harness) | `AQ7_ROLE_DROP_BASELINE_PARTIAL_HOLD` |
| Evidence regen | external workdir only; WAV/JSON **not** committed |
| Boundary runner | `python -m src.aq7_structure_boundary_baseline --work-dir <ext>/aq7-structure-role-drop-corpus --output <ext>/aq7-structure-boundary-baseline.json` |
| Role/drop runner | `python -m src.aq7_structure_role_drop_baseline --work-dir <ext>/aq7-structure-role-drop-corpus --output <ext>/aq7-structure-role-drop-baseline.json` |

### Evidence identity check (Task 1)

Fresh external regeneration on `origin/main` including #1026 matched the portable rounded aggregates and exit tokens in the baseline docs (candidate/corpus ids, CAL/TEST P/R/F1, support, FP/FN, role macro-F1/coverage, drop support/false/missed, BeatGrid HOLD counts). Exact floats live only in the external JSON.

| Check | Result |
|---|---|
| Corpus / candidate / exit tokens | PASS |
| Rounded #1025 aggregates | PASS |
| Rounded #1026 role + drop aggregates | PASS |
| Raw WAV/JSON committed | NO |

On drift this slice must stop with `BLOCKED_EVIDENCE_IDENTITY_DRIFT` (not observed).

### Plane firewall

| Plane | Token | Baseline source | Bucket source |
|---|---|---|---|
| Boundary | `aq7.boundary` | #1025 | #1025 fixture bars + #1023 matcher (offline signed-error recount) |
| Role | `aq7.role` | #1026 | #1026 `role_items` / confusion only |
| Drop | `aq7.drop_event` | #1026 | #1026 drop events only |

Do **not** blend planes into one quality score. GT roles/drops never enter the prediction path (evaluator-only).

### Attribution hierarchy (fail-closed)

A case attributed at an earlier layer must **not** also count as a deeper plane failure:

1. Eligibility / annotation
2. BeatGrid / provenance
3. Analyzer / feature surface failure
4. Boundary geometry failure
5. Signal availability
6. Role classifier outcome
7. Drop classifier outcome

### Split firewall + HOLD rules

| Rule | Application |
|---|---|
| CALIBRATION vs TEST | Strictly separate tables; no pooled correctness rates |
| HOLD | Excluded from correctness denominators |
| Ambiguous / ignore-mask | Visible as `boundary.ambiguity_ignore_mask`; **not** FP/FN |
| Shares | Only over eligible denominators for that bucket |
| Thin support | `dominant` requires support ≥ 2; support 1 → `DOMINANT_ON_THIN_CORPUS` |

Dominant ranking within each plane × split: (1) support desc, (2) share of eligible denom desc, (3) lexicographic `bucket_id`.

---

## 2. Boundary Failure Buckets

Matching: #1023 ±1-bar one-to-one (`match_boundaries_1bar`). Early/late derived from recomputed `signed_error_bars` (`pred_bar - ref_bar`); ignore-masked predictions excluded from FP extras (same as #1025 scoring). `predicted_bars` in the artifact may include masked loci; unmasked preds are the correctness surface.

### Denominators (eligible / usable only; HOLD excluded)

| Split | Usable fixtures | Eligible refs | Unmasked preds | Matched pairs |
|---|---:|---:|---:|---:|
| CALIBRATION | 6 | 13 | 35 | 12 |
| TEST | 3 | 9 | 25 | 9 |

TEST BeatGrid HOLD fixture is **not** in these denominators.

### CALIBRATION (`aq7.boundary`)

| bucket_id | support | share (eligible denom) | affected `fixture_id`s | notes |
|---|---:|---|---|---|
| `boundary.extra_or_duplicate` | 23 | 23/35 = 0.657 | `aq7-synth-simple-clean-cal-001`, `aq7-synth-repeated-structure-cal-001`, `aq7-synth-near-boundary-tolerance-cal-001`, `aq7-synth-role-ambiguity-unknown-cal-001`, `aq7-synth-annotation-disagreement-cal-001`, `aq7-synth-over-segmentation-challenge-cal-001` | unmatched unmasked preds |
| `boundary.exact` | 11 | 11/12 = 0.917 | all usable except empty-ref disagreement | success context; signed_error = 0 |
| `boundary.over_segmentation` | 6 | 6/6 = 1.000 | all 6 usable CAL fixtures | record-level |
| `boundary.section_count_error` | 6 | 6/6 = 1.000 | same 6 | abs section-count error > 0 |
| `boundary.early` | 1 | 1/12 = 0.083 | `aq7-synth-repeated-structure-cal-001` | signed_error = −1 (ref 32 → pred 31) |
| `boundary.late` | 0 | 0/12 = 0.000 | — | — |
| `boundary.near_tolerance` | 1 | 1/12 = 0.083 | `aq7-synth-repeated-structure-cal-001` | matched with 0 < \|err\| ≤ 1 |
| `boundary.missed` | 1 | 1/13 = 0.077 | `aq7-synth-over-segmentation-challenge-cal-001` | eligible ref unmatched |
| `boundary.under_segmentation` | 0 | 0/6 = 0.000 | — | even `under_segmentation_challenge` still over-segs |
| `boundary.ambiguity_ignore_mask` | 1 | n/a (not FP/FN) | `aq7-synth-annotation-disagreement-cal-001` | mask around bar 16; masked pred not counted as FP |
| `boundary.beatgrid_hold` | 0 | n/a | — | — |
| `boundary.analyzer_failure` | 0 | n/a | — | — |

### TEST (`aq7.boundary`)

| bucket_id | support | share (eligible denom) | affected `fixture_id`s | notes |
|---|---:|---|---|---|
| `boundary.extra_or_duplicate` | 16 | 16/25 = 0.640 | `aq7-synth-drop-at-boundary-test-001`, `aq7-synth-drop-not-boundary-owner-test-001`, `aq7-synth-under-segmentation-challenge-test-001` | unmatched unmasked preds |
| `boundary.exact` | 9 | 9/9 = 1.000 | same 3 usable TEST fixtures | all matched pairs exact |
| `boundary.over_segmentation` | 3 | 3/3 = 1.000 | same 3 | record-level |
| `boundary.section_count_error` | 3 | 3/3 = 1.000 | same 3 | — |
| `boundary.early` | 0 | 0/9 = 0.000 | — | — |
| `boundary.late` | 0 | 0/9 = 0.000 | — | — |
| `boundary.near_tolerance` | 0 | 0/9 = 0.000 | — | — |
| `boundary.missed` | 0 | 0/9 = 0.000 | — | — |
| `boundary.under_segmentation` | 0 | 0/3 = 0.000 | — | challenge fixture still over-segs |
| `boundary.ambiguity_ignore_mask` | 0 | n/a | — | — |
| `boundary.beatgrid_hold` | 1 | n/a (HOLD) | `aq7-synth-beatgrid-hold-test-001` | provenance `missing`; not in correctness denoms |
| `boundary.analyzer_failure` | 0 | n/a | — | — |

---

## 3. Role Confusion Buckets

Source: #1026 only. Confusion is `reference_role -> predicted_role` on scored eligible sections. GT roles are never back-projected into the prediction path.

### Denominators

| Split | Scored role items | Concrete-role support | Held (BeatGrid) | Annotation-unavailable |
|---|---:|---:|---:|---:|
| CALIBRATION | 18 | 17 | 0 | 1 (`aq7-synth-annotation-disagreement-cal-001`) |
| TEST | 12 | 12 | 1 (`aq7-synth-beatgrid-hold-test-001`) | 0 |

Note: baseline aggregate field `abstention_count` counts **held unusable fixtures** (TEST = 1 BeatGrid HOLD), not section-level uncovered predictions. True `pred_role is None` uncovered count is **0** on both splits. BeatGrid HOLD stays at attribution layer 2 — not a role-classifier miss.

### CALIBRATION (`aq7.role`)

#### Confusion pairs (all scored)

| ref → pred | support | share of scored (18) | fixture_ids |
|---|---:|---:|---|
| intro → unknown | 4 | 0.222 | `aq7-synth-simple-clean-cal-001`, `aq7-synth-repeated-structure-cal-001`, `aq7-synth-near-boundary-tolerance-cal-001`, `aq7-synth-role-ambiguity-unknown-cal-001` |
| outro → outro | 5 | 0.278 | (correct; multiple CAL fixtures) |
| groove → unknown | 2 | 0.111 | `aq7-synth-simple-clean-cal-001`, `aq7-synth-repeated-structure-cal-001` |
| build → groove | 2 | 0.111 | `aq7-synth-near-boundary-tolerance-cal-001`, `aq7-synth-over-segmentation-challenge-cal-001` |
| build → unknown | 1 | 0.056 | `aq7-synth-repeated-structure-cal-001` |
| intro → groove | 1 | 0.056 | `aq7-synth-over-segmentation-challenge-cal-001` |
| groove → groove | 1 | 0.056 | (correct) |
| drop → drop | 1 | 0.056 | (correct) |
| unknown → unknown | 1 | 0.056 | `aq7-synth-role-ambiguity-unknown-cal-001` |

#### Concrete-role confusions (ref≠pred, both concrete)

| pair | support | share of concrete (17) | diagnostic context |
|---|---:|---:|---|
| build → groove | 2 | 0.118 | mid-track; length 16 bars; prev=intro; next=outro or drop |
| intro → groove | 1 | 0.059 | early; length 12; prev=none; next=build |

#### Predicted unknown / reference unknown / held

| bucket | support | share | fixture_ids |
|---|---:|---|---|
| predicted unknown | 8 | 8/18 = 0.444 | `aq7-synth-simple-clean-cal-001`, `aq7-synth-repeated-structure-cal-001`, `aq7-synth-near-boundary-tolerance-cal-001`, `aq7-synth-role-ambiguity-unknown-cal-001` |
| reference unknown | 1 | 1/18 = 0.056 | `aq7-synth-role-ambiguity-unknown-cal-001` (pred also unknown) |
| abstention / uncovered (`pred_role is None`) | 0 | — | — |
| held / unavailable | 1 | n/a | `aq7-synth-annotation-disagreement-cal-001` (ambiguous-boundary exclusion; eligibility layer) |

### TEST (`aq7.role`)

#### Confusion pairs (all scored; BeatGrid HOLD excluded)

| ref → pred | support | share of scored (12) | fixture_ids |
|---|---:|---:|---|
| drop → groove | 2 | 0.167 | `aq7-synth-drop-at-boundary-test-001`, `aq7-synth-under-segmentation-challenge-test-001` |
| outro → outro | 2 | 0.167 | (correct) |
| build → groove | 1 | 0.083 | `aq7-synth-under-segmentation-challenge-test-001` |
| build → intro | 1 | 0.083 | `aq7-synth-drop-at-boundary-test-001` |
| intro → groove | 1 | 0.083 | `aq7-synth-drop-not-boundary-owner-test-001` |
| intro → intro | 1 | 0.083 | (correct) |
| intro → unknown | 1 | 0.083 | `aq7-synth-under-segmentation-challenge-test-001` |
| groove → groove | 1 | 0.083 | (correct) |
| groove → unknown | 1 | 0.083 | `aq7-synth-under-segmentation-challenge-test-001` |
| outro → unknown | 1 | 0.083 | `aq7-synth-drop-not-boundary-owner-test-001` |

#### Concrete-role confusions

| pair | support | share of concrete (12) | diagnostic context |
|---|---:|---:|---|
| drop → groove | 2 | 0.167 | mid/late; length 16; prev=build; next=outro |
| build → groove | 1 | 0.083 | mid; length 16; prev=groove; next=drop |
| build → intro | 1 | 0.083 | mid; length 16; prev=intro; next=drop |
| intro → groove | 1 | 0.083 | early; length 12; prev=none; next=groove |

#### Predicted unknown / held

| bucket | support | share | fixture_ids |
|---|---:|---|---|
| predicted unknown | 3 | 3/12 = 0.250 | `aq7-synth-drop-not-boundary-owner-test-001`, `aq7-synth-under-segmentation-challenge-test-001` |
| reference unknown | 0 | — | — |
| abstention / uncovered | 0 | — | — |
| held (BeatGrid) | 1 | n/a | `aq7-synth-beatgrid-hold-test-001` |

---

## 4. Drop Event Failure Buckets

Source: #1026 only. Matching uses ±1-bar policy on reference drop events. **No matched events** on either split → `drop.timing_offset = not_applicable` (not 0).

### CALIBRATION (`aq7.drop_event`)

| bucket_id | support | share | affected `fixture_id`s |
|---|---:|---|---|
| `drop.false` | 6 | 6/6 predicted positives = 1.000 | `aq7-synth-simple-clean-cal-001`, `aq7-synth-repeated-structure-cal-001`, `aq7-synth-near-boundary-tolerance-cal-001`, `aq7-synth-role-ambiguity-unknown-cal-001`, `aq7-synth-over-segmentation-challenge-cal-001` |
| `drop.missed` | 1 | 1/1 ref support = 1.000 | `aq7-synth-over-segmentation-challenge-cal-001` (ref bar 28; pred bar 36 unmatched) |
| `drop.timing_offset` | n/a | **not_applicable** | no matched pairs |
| `drop.correct_event` | 0 | 0/1 | — |
| `drop.correct_negative` | 1 | n/a (empty expected set, no false preds) | `aq7-synth-annotation-disagreement-cal-001` |
| `drop.unavailable_hold` | 0 | n/a | — |
| `drop.beatgrid_hold` | 0 | n/a | — |

### TEST (`aq7.drop_event`)

| bucket_id | support | share | affected `fixture_id`s |
|---|---:|---|---|
| `drop.false` | 3 | 3/3 predicted positives = 1.000 | `aq7-synth-drop-at-boundary-test-001`, `aq7-synth-drop-not-boundary-owner-test-001`, `aq7-synth-under-segmentation-challenge-test-001` |
| `drop.missed` | 2 | 2/2 ref support = 1.000 | `aq7-synth-drop-at-boundary-test-001` (ref 32), `aq7-synth-drop-not-boundary-owner-test-001` (ref 28) |
| `drop.timing_offset` | n/a | **not_applicable** | no matched pairs |
| `drop.correct_event` | 0 | 0/2 | — |
| `drop.correct_negative` | 0 | — | — |
| `drop.unavailable_hold` | 0 | n/a | — |
| `drop.beatgrid_hold` | 1 | n/a (HOLD) | `aq7-synth-beatgrid-hold-test-001` |

---

## 5. BeatGrid / Provenance Attribution

| Fixture | Split | Provenance | Attribution layer | Effect |
|---|---|---|---|---|
| `aq7-synth-beatgrid-hold-test-001` | TEST | `missing` | 2 — BeatGrid / provenance | Boundary, role, and drop correctness = HOLD/unknown; excluded from all plane correctness denominators |
| All other fixtures | CAL + TEST | `authored_synthetic` | evaluation-only synthetic grid | Measurable surfaces; not analyzer BeatGrid truth |

No analyzer/feature-surface HOLD (`ANALYZER_FAILURE` / `ANALYZER_FEATURE_LIMITATION`) observed on this pack.

Annotation eligibility HOLD (layer 1): `aq7-synth-annotation-disagreement-cal-001` — ambiguous boundary ignore-mask; role sections excluded; boundary ignore-mask locus not scored as FP/FN; drop empty-set correct negative remains drop-plane evidence only.

Fail-closed: the BeatGrid HOLD fixture is **not** counted as role confusion, drop false/missed, or boundary FP/FN.

---

## 6. CALIBRATION vs TEST comparison

| Plane | CALIBRATION headline | TEST headline | Firewall note |
|---|---|---|---|
| Boundary | Extra/duplicate preds dominate (23/35); universal over-segmentation (6/6); 1 early/near-tol pair; 1 miss | Extra/duplicate (16/25); universal over-seg (3/3); all matched pairs exact; +1 BeatGrid HOLD | HOLD fixture only on TEST; rates not pooled |
| Role | Predicted `unknown` dominates (8/18); concrete build→groove (2); outro mostly correct | Predicted `unknown` (3/12); concrete drop→groove (2); build confusions thin | BeatGrid HOLD ≠ role abstention |
| Drop | All 6 predicted events false; 1 miss; timing N/A; 1 correct negative | All 3 predicted events false; 2 misses; timing N/A; +1 BeatGrid HOLD | No matched events either split |

Do **not** tune on TEST. Thin per-bucket support (often 1) blocks durable rate claims beyond this synthetic pack.

---

## 7. Dominant Failure Summary

Ranking rule: support ↓, eligible share ↓, `bucket_id` ↑. Tag `dominant` iff support ≥ 2; else `DOMINANT_ON_THIN_CORPUS`. Success-only buckets (`boundary.exact`, correct role pairs, `drop.correct_*`) are measured context, not failure winners.

### Boundary × CALIBRATION

| rank | bucket_id | support | share | tag |
|---:|---|---:|---:|---|
| 1 | `boundary.extra_or_duplicate` | 23 | 0.657 | dominant |
| 2 | `boundary.over_segmentation` | 6 | 1.000 | dominant |
| 3 | `boundary.section_count_error` | 6 | 1.000 | dominant |
| 4 | `boundary.early` | 1 | 0.083 | DOMINANT_ON_THIN_CORPUS |
| 5 | `boundary.near_tolerance` | 1 | 0.083 | DOMINANT_ON_THIN_CORPUS |
| 6 | `boundary.missed` | 1 | 0.077 | DOMINANT_ON_THIN_CORPUS |
| 7 | `boundary.ambiguity_ignore_mask` | 1 | n/a | DOMINANT_ON_THIN_CORPUS |

### Boundary × TEST

| rank | bucket_id | support | share | tag |
|---:|---|---:|---:|---|
| 1 | `boundary.extra_or_duplicate` | 16 | 0.640 | dominant |
| 2 | `boundary.over_segmentation` | 3 | 1.000 | dominant |
| 3 | `boundary.section_count_error` | 3 | 1.000 | dominant |
| 4 | `boundary.beatgrid_hold` | 1 | n/a | DOMINANT_ON_THIN_CORPUS |

### Role × CALIBRATION

| rank | bucket_id | support | share | tag |
|---:|---|---:|---:|---|
| 1 | `role.predicted_unknown` | 8 | 0.444 | dominant |
| 2 | `role.confusion:intro->unknown` | 4 | 0.222 | dominant |
| 3 | `role.concrete_confusion:build->groove` | 2 | 0.118 | dominant |
| 4 | `role.confusion:groove->unknown` | 2 | 0.111 | dominant |
| 5 | `role.confusion:build->unknown` | 1 | 0.056 | DOMINANT_ON_THIN_CORPUS |
| 6 | `role.concrete_confusion:intro->groove` | 1 | 0.059 | DOMINANT_ON_THIN_CORPUS |
| 7 | `role.reference_unknown` | 1 | 0.056 | DOMINANT_ON_THIN_CORPUS |
| 8 | `role.held_unavailable` (annotation) | 1 | n/a | DOMINANT_ON_THIN_CORPUS |

### Role × TEST

| rank | bucket_id | support | share | tag |
|---:|---|---:|---:|---|
| 1 | `role.predicted_unknown` | 3 | 0.250 | dominant |
| 2 | `role.concrete_confusion:drop->groove` | 2 | 0.167 | dominant |
| 3 | `role.concrete_confusion:build->groove` | 1 | 0.083 | DOMINANT_ON_THIN_CORPUS |
| 4 | `role.concrete_confusion:build->intro` | 1 | 0.083 | DOMINANT_ON_THIN_CORPUS |
| 5 | `role.concrete_confusion:intro->groove` | 1 | 0.083 | DOMINANT_ON_THIN_CORPUS |
| 6 | `role.confusion:groove->unknown` | 1 | 0.083 | DOMINANT_ON_THIN_CORPUS |
| 7 | `role.confusion:intro->unknown` | 1 | 0.083 | DOMINANT_ON_THIN_CORPUS |
| 8 | `role.confusion:outro->unknown` | 1 | 0.083 | DOMINANT_ON_THIN_CORPUS |
| 9 | `role.held` (BeatGrid) | 1 | n/a | DOMINANT_ON_THIN_CORPUS |

### Drop × CALIBRATION

| rank | bucket_id | support | share | tag |
|---:|---|---:|---:|---|
| 1 | `drop.false` | 6 | 1.000 | dominant |
| 2 | `drop.missed` | 1 | 1.000 | DOMINANT_ON_THIN_CORPUS |

`drop.timing_offset`: **not_applicable**.

### Drop × TEST

| rank | bucket_id | support | share | tag |
|---:|---|---:|---:|---|
| 1 | `drop.false` | 3 | 1.000 | dominant |
| 2 | `drop.missed` | 2 | 1.000 | dominant |
| 3 | `drop.beatgrid_hold` | 1 | n/a | DOMINANT_ON_THIN_CORPUS |

`drop.timing_offset`: **not_applicable**.

---

## Deferred (not Task 1)

- Final candidate hypotheses for #1028
- `CANON_INDEX` update
- Analyzer / harness / threshold changes
- Issue-level exit beyond Task-1 `AQ7_1027_BUCKET_ANALYSIS_READY`
