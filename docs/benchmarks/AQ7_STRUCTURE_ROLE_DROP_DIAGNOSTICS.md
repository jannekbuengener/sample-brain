# AQ7 Structure / Role / Drop Diagnostics — Error Buckets + Signal Attribution

**Status:** ACTIVE_SUPPORTING — diagnostics / evidence for [#1027](https://github.com/jannekbuengener/sample-brain/issues/1027)
**Class:** ACTIVE_SUPPORTING
**Parents:** [#949](https://github.com/jannekbuengener/sample-brain/issues/949) (AQ7), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)
**Depends on (CLOSED):** [#1023](https://github.com/jannekbuengener/sample-brain/issues/1023) KPI, [#1024](https://github.com/jannekbuengener/sample-brain/issues/1024) corpus, [#1025](https://github.com/jannekbuengener/sample-brain/issues/1025) boundary baseline, [#1026](https://github.com/jannekbuengener/sample-brain/issues/1026) role/drop baseline
**Normative KPI:** [`AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md`](AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md)
**Corpus:** [`AQ7_STRUCTURE_ROLE_DROP_CORPUS.md`](AQ7_STRUCTURE_ROLE_DROP_CORPUS.md) / `sample-brain.aq7.structure-role-drop.synthetic.v1`
**Boundary baseline:** [`AQ7_STRUCTURE_BOUNDARY_BASELINE.md`](AQ7_STRUCTURE_BOUNDARY_BASELINE.md) / `structure_v1.baseline.v1`
**Role/drop baseline:** [`AQ7_STRUCTURE_ROLE_DROP_BASELINE.md`](AQ7_STRUCTURE_ROLE_DROP_BASELINE.md) / `arrangement_classifier.baseline.v1`
**Signal ownership context (diagnostic only):** [`../ARRANGEMENT_SIGNAL_MATRIX_V1.md`](../ARRANGEMENT_SIGNAL_MATRIX_V1.md)
**Related bootstrap:** [#1040](https://github.com/jannekbuengener/sample-brain/issues/1040) quality-loop consumer of stable bucket IDs (orchestrator out of scope here)
**Downstream (not started here):** [#1028](https://github.com/jannekbuengener/sample-brain/issues/1028) candidate compare
**Style reference:** [`AQ4_CLASSIFICATION_DIAGNOSTICS.md`](AQ4_CLASSIFICATION_DIAGNOSTICS.md) (taxonomy separation; not a plane merge)

## Architecture outcome (Task 1)

```text
AQ7_1027_BUCKET_ANALYSIS_READY
```

This document turns the measured #1025 / #1026 baselines into **explainable failure buckets** with plane firewalls, HOLD honesty, and dominant ranking. Task 1 does **not** change StructureV1 / ArrangementClassifier / SectionSignals, retune thresholds, or switch production defaults.

## Architecture outcome (Task 2)

```text
AQ7_1027_ATTRIBUTION_READY
```

Task 2 adds **signal availability / correlation**, **bounded CALIBRATION hypotheses**, **explicit non-conclusions**, and a **machine-facing bucket/hypothesis appendix**. It does **not** implement candidates (#1028), invent thresholds, mutate analyzer/harness code, or treat TEST as a tuning set.

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

## 8. Signal Availability / Correlation

Signal families are **explanatory only** — not ground truth, not promotion evidence, not pseudo-labels.
Evidence states: `measured` | `missing` | `unknown` | `unavailable` | `held` | `not_applicable`.
Missing is never numeric `0`. Optional unused CLAP/stems stay `not_applicable` (not measured).

Live path only: `StructureV1.bar_features` → `SectionSignalsAssembler` (`src/section_signals.py`) → `ArrangementClassifier`. Provenance joined from Task-1 regenerated #1026 external JSON (uncommitted; workdir outside checkout).

### 8.1 Availability matrix (live SectionSignals path)

| Signal family | Live field(s) | Usable CAL | Usable TEST (non-HOLD) | BeatGrid HOLD fixture | Evidence state |
|---|---|---|---|---|---|
| energy / loudness | `bar_energy_rms`, `bar_loudness_delta` | present | present | not claimed measured | `measured` on usable; `held` under BeatGrid HOLD |
| low-end share | `low_end_share` | present | present | not claimed measured | `measured` / `held` |
| onset density | `onset_density` | present | present | not claimed measured | `measured` / `held` |
| rhythm stability | `rhythm_stability` | present | present | not claimed measured | `measured` / `held` |
| timbre change | `timbre_delta` | present | present | not claimed measured | `measured` / `held` |
| spectral change | `spectral_delta` | present | present | not claimed measured | `measured` / `held` |
| recurrence | `recurrence` | present | present | not claimed measured | `measured` / `held` |
| novelty / self-similarity | `novelty`, `self_similarity` | present | present | not claimed measured | `measured` / `held` |
| neighbor delta | `neighbor_delta` | present | present | not claimed measured | `measured` / `held` |
| multi-bar trend | `multi_bar_trend` | present | present | not claimed measured | `measured` / `held` |
| relative track position | `relative_track_position` | present | present | not claimed measured | `measured` / `held` |
| CLAP | (optional) | unused | unused | unused | `not_applicable` |
| stems | (optional) | unused | unused | unused | `not_applicable` |

`aq7-synth-beatgrid-hold-test-001` (TEST): external `signal_provenance` records only `clap`/`stems` = `not_applicable`. Core families are **not** asserted `measured` under provenance HOLD (attribution stops at layer 2 → evidence state `held`).

No core MVP family is `missing` or `unavailable` on usable `authored_synthetic` fixtures in this regeneration.

### 8.2 Correlation join (failure bucket → fixture/section → signal provenance)

Descriptive co-occurrence only. Allowed language: co-occurs, consistent with, present when, absent when. Forbidden: causes, proves, fixes.

Association claims require support ≥ 2 within the same split. Support 1 → `MEASURED_SINGLETON` (no generalization).

| Failure bucket | Split | Support | Fixture / section loci | Signal provenance co-occurrence | Association class |
|---|---|---:|---|---|---|
| `boundary.over_segmentation` + `boundary.extra_or_duplicate` | CAL | 6 fixtures / FP=23 | all CAL usable | novelty / onset / neighbor / multi-bar families `measured` present when extras present | association (support≥2) |
| `boundary.over_segmentation` + `boundary.extra_or_duplicate` | TEST | 3 fixtures / FP=16 | all TEST usable non-HOLD | same core families `measured` present when extras present | association (support≥2); evidence only |
| `role.confusion:intro->unknown` | CAL | 4 | early sections: simple-clean, repeated, near-boundary, role-ambiguity | `relative_track_position` `measured` present when intro→unknown; energy/onset/low-end also `measured` | association (support≥2) |
| `role.confusion:intro->unknown` | TEST | 1 | under-seg early section | same families `measured` | `MEASURED_SINGLETON` |
| `role.concrete_confusion:build->groove` | CAL | 2 | near-boundary; over-seg challenge | loudness/onset/timbre/spectral deltas `measured` present when build→groove | association (support≥2) |
| `role.concrete_confusion:build->groove` | TEST | 1 | under-seg | same | `MEASURED_SINGLETON` |
| `role.confusion:groove->unknown` | CAL | 2 | simple-clean; repeated | energy/onset/rhythm/recurrence `measured` present when groove→unknown | association (support≥2) |
| `role.confusion:groove->unknown` | TEST | 1 | under-seg | same | `MEASURED_SINGLETON` |
| `role.concrete_confusion:drop->groove` | TEST | 2 | drop-at-boundary; under-seg | energy/low-end/onset `measured` present when drop→groove | association on TEST only — **not** CAL hypothesis fuel |
| `drop.false` | CAL | 6 | simple-clean; repeated; near-boundary; role-ambiguity; over-seg | loudness/timbre/novelty/neighbor families `measured` present when false `drop_onset` emitted | association (support≥2) |
| `drop.false` | TEST | 3 | drop-at-boundary; drop-not-boundary-owner; under-seg | same families `measured` | association (support≥2); evidence only |
| `drop.missed` | CAL | 1 | over-seg challenge (ref bar 28) | core families `measured`; `drop.timing_offset` = `not_applicable` | `MEASURED_SINGLETON` |
| `drop.missed` | TEST | 2 | drop-at-boundary; drop-not-boundary-owner | core families `measured`; timing_offset `not_applicable` | TEST may confirm/refute later — **not** new CAL hypothesis |
| `boundary.missed` / `boundary.early` | CAL | 1 each | over-seg miss; repeated early −1 bar | core boundary-input families `measured` | `MEASURED_SINGLETON` each |

CLAP/stems remain `not_applicable` in every fixture row — never treated as correctness or as numeric absence.

---

## 9. Bounded Candidate Hypotheses

Hypotheses are **CALIBRATION-derived only**. TEST may confirm, refute, or HOLD — never create new CAL hypotheses.
Shortlist language for #1028: only CAL support ≥ 2. Support 1 → `OBSERVED_SINGLETON` (not a bake-off candidate).
No invented threshold numbers. Candidate change class is advisory only.

### 9.1 Shortlist-eligible (CAL support ≥ 2)

#### H-AQ7-1027-01

| Field | Value |
|---|---|
| HYPOTHESIS ID | `H-AQ7-1027-01` |
| Observed failure bucket | `boundary.extra_or_duplicate` / `boundary.over_segmentation` |
| Support CAL | 6/6 over-seg fixtures; FP extras = 23 |
| Support TEST | 3/3 eligible over-seg; FP extras = 16 (confirms co-occurrence; not fuel) |
| Evidence | Universal over-segmentation on usable fixtures; extras dominate unmatched unmasked preds; core novelty/onset/neighbor/multi-bar families `measured` present when extras present |
| Likely contributing signal/path | StructureV1 boundary density path consuming novelty / onset / neighbor / multi-bar trend surfaces |
| Confidence / evidence state | measured association (CAL support≥2); thin synthetic corpus |
| Candidate change class | `scoped_code` (advisory) — possibly with `config` exploration later |
| Expected metric affected | boundary P@1bar; over-seg rate; section-count abs error (keep R@1bar visible) |
| Risks | Collapsing recall / under-segmentation; harming exact-hit pairs that are already strong |
| What would falsify it | CAL over-seg rate drops while extras remain dominant, or extras shrink while over-seg rate stays 1.0 on the same pack |

#### H-AQ7-1027-02

| Field | Value |
|---|---|
| HYPOTHESIS ID | `H-AQ7-1027-02` |
| Observed failure bucket | `role.confusion:intro->unknown` |
| Support CAL | 4 |
| Support TEST | 1 (`MEASURED_SINGLETON` confirm/refute only) |
| Evidence | Four early CAL sections score intro→unknown while `relative_track_position` and energy/onset/low-end families are `measured` |
| Likely contributing signal/path | ArrangementClassifier early-section / relative-position path under SectionSignals |
| Confidence / evidence state | measured association (CAL n=4) |
| Candidate change class | `existing_candidate` (advisory) — classifier scoring surface |
| Expected metric affected | intro recall / concrete macro-F1; unknown rate (preserve honesty) |
| Risks | Over-forcing intro labels; GT leakage if signals treated as labels |
| What would falsify it | CAL intro→unknown support falls below 2 on the same fixtures without changing GT |

#### H-AQ7-1027-03

| Field | Value |
|---|---|
| HYPOTHESIS ID | `H-AQ7-1027-03` |
| Observed failure bucket | `role.concrete_confusion:build->groove` |
| Support CAL | 2 |
| Support TEST | 1 (`MEASURED_SINGLETON` only) |
| Evidence | Two CAL mid-track builds predicted as groove while loudness/onset/timbre/spectral deltas are `measured` |
| Likely contributing signal/path | Role scoring path weighting groove-stable cues over build-delta cues on synthetic material |
| Confidence / evidence state | measured association (CAL n=2; thin) |
| Candidate change class | `existing_candidate` (advisory) |
| Expected metric affected | build precision/recall within concrete macro-F1 |
| Risks | Swapping build↔groove errors; harming correct groove pairs |
| What would falsify it | CAL build→groove support falls below 2, or becomes singleton after any declared filter |

#### H-AQ7-1027-04

| Field | Value |
|---|---|
| HYPOTHESIS ID | `H-AQ7-1027-04` |
| Observed failure bucket | `role.confusion:groove->unknown` |
| Support CAL | 2 |
| Support TEST | 1 (`MEASURED_SINGLETON` only) |
| Evidence | Two CAL groove sections predicted unknown while energy/onset/rhythm/recurrence families are `measured` |
| Likely contributing signal/path | ArrangementClassifier abstention / unknown path on mid-track groove sections |
| Confidence / evidence state | measured association (CAL n=2; thin) |
| Candidate change class | `existing_candidate` (advisory) |
| Expected metric affected | groove recall; unknown rate; concrete coverage |
| Risks | Reducing legitimate unknown honesty; inflating false concrete labels |
| What would falsify it | CAL groove→unknown support falls below 2 on the same fixtures |

#### H-AQ7-1027-05

| Field | Value |
|---|---|
| HYPOTHESIS ID | `H-AQ7-1027-05` |
| Observed failure bucket | `drop.false` |
| Support CAL | FP = 6 |
| Support TEST | FP = 3 (confirms co-occurrence; not fuel) |
| Evidence | All CAL predicted drop events unmatched; loudness/timbre/novelty/neighbor families `measured` present when false `drop_onset` emitted; `drop.timing_offset` = `not_applicable` |
| Likely contributing signal/path | Drop-event emission path on ArrangementClassifier using loudness/timbre/novelty/neighbor surfaces |
| Confidence / evidence state | measured association (CAL FP=6) |
| Candidate change class | `scoped_code` (advisory) — emission eligibility / scoring surface |
| Expected metric affected | drop precision@1bar; false count (keep miss visibility separate) |
| Risks | Suppressing true drops; converting false-drop reduction into higher misses |
| What would falsify it | CAL false count falls while miss count rises enough that net F1 does not improve on the same pack |

### 9.2 OBSERVED_SINGLETON (CAL support = 1; not shortlist)

| HYPOTHESIS ID | Observed failure bucket | Support CAL | Support TEST | Shortlist? |
|---|---|---:|---|---|
| `H-AQ7-1027-S01` | `boundary.missed` | 1 | 0 | no — `OBSERVED_SINGLETON` |
| `H-AQ7-1027-S02` | `boundary.early` | 1 | 0 | no — `OBSERVED_SINGLETON` |
| `H-AQ7-1027-S03` | `role.confusion:build->unknown` | 1 | 0 | no — `OBSERVED_SINGLETON` |
| `H-AQ7-1027-S04` | `role.concrete_confusion:intro->groove` | 1 | 1 (TEST singleton) | no — `OBSERVED_SINGLETON` |
| `H-AQ7-1027-S05` | `drop.missed` | 1 | 2 (TEST may confirm later; not CAL fuel) | no — `OBSERVED_SINGLETON` on CAL |

Singleton fields (shared): evidence = Task-1 bucket row; likely path = same live SectionSignals→classifier surface; confidence = measured singleton; change class advisory `existing_candidate` or `scoped_code`; expected metric = the bucket's plane metric; risks = overfit to n=1; falsifier = support remains 1 or disappears on remeasure.

### 9.3 Explicitly not promoted to hypotheses

- TEST-leading `role.concrete_confusion:drop->groove` (TEST must not drive candidates)
- Any breakdown-family claim (corpus support 0)
- Any CLAP/stem-driven claim (`not_applicable`)
- Any global AQ7 composite score
- Any invented threshold / promotion gate

Hypothesis count: **10** (5 shortlist-eligible + 5 singletons). Shortlist-eligible for #1028: **5**.

---

## 10. Explicit Non-Conclusions

- Signal correlation ≠ Ground Truth.
- Signal correlation ≠ Causality.
- Thin synthetic corpus ≠ producer-world generalization.
- TEST is not a tuning set.
- BeatGrid HOLD is not ArrangementClassifier failure.
- 0 Drop TP does not by itself dictate which algorithm to change.
- #1027 authorizes no production change.
- No invented thresholds, tolerances, or promotion gates.
- No global AQ7 quality score blending boundary + role + drop.
- HOLD / ignore-mask / BeatGrid are not “failures against the analyzer.”
- `drop.timing_offset` is not 0 when unmatched — it is `not_applicable`.
- Optional signals (CLAP/stems) were not present and are not pseudo-labeled.
- #1028 is not started; hypotheses are advisory tokens only.

---

## 11. Machine-facing Bucket / Hypothesis Appendix

Stable IDs for later #1040 bootstrap. Markdown tables only (no committed JSON artifact). Values are portable summaries; exact floats remain in external JSON.

### 11.1 Bucket appendix

| bucket_id | plane | split | support | share | evidence_state | hypothesis_id |
|---|---|---|---:|---|---|---|
| `boundary.extra_or_duplicate` | `aq7.boundary` | CALIBRATION | 23 | 0.657 | measured | `H-AQ7-1027-01` |
| `boundary.over_segmentation` | `aq7.boundary` | CALIBRATION | 6 | 1.000 | measured | `H-AQ7-1027-01` |
| `boundary.section_count_error` | `aq7.boundary` | CALIBRATION | 6 | 1.000 | measured | `H-AQ7-1027-01` |
| `boundary.early` | `aq7.boundary` | CALIBRATION | 1 | 0.083 | measured | `H-AQ7-1027-S02` |
| `boundary.near_tolerance` | `aq7.boundary` | CALIBRATION | 1 | 0.083 | measured | — |
| `boundary.missed` | `aq7.boundary` | CALIBRATION | 1 | 0.077 | measured | `H-AQ7-1027-S01` |
| `boundary.ambiguity_ignore_mask` | `aq7.boundary` | CALIBRATION | 1 | n/a | measured | — |
| `boundary.extra_or_duplicate` | `aq7.boundary` | TEST | 16 | 0.640 | measured | — |
| `boundary.over_segmentation` | `aq7.boundary` | TEST | 3 | 1.000 | measured | — |
| `boundary.section_count_error` | `aq7.boundary` | TEST | 3 | 1.000 | measured | — |
| `boundary.beatgrid_hold` | `aq7.boundary` | TEST | 1 | n/a | held | — |
| `role.predicted_unknown` | `aq7.role` | CALIBRATION | 8 | 0.444 | measured | — |
| `role.confusion:intro->unknown` | `aq7.role` | CALIBRATION | 4 | 0.222 | measured | `H-AQ7-1027-02` |
| `role.concrete_confusion:build->groove` | `aq7.role` | CALIBRATION | 2 | 0.118 | measured | `H-AQ7-1027-03` |
| `role.confusion:groove->unknown` | `aq7.role` | CALIBRATION | 2 | 0.111 | measured | `H-AQ7-1027-04` |
| `role.confusion:build->unknown` | `aq7.role` | CALIBRATION | 1 | 0.056 | measured | `H-AQ7-1027-S03` |
| `role.concrete_confusion:intro->groove` | `aq7.role` | CALIBRATION | 1 | 0.059 | measured | `H-AQ7-1027-S04` |
| `role.reference_unknown` | `aq7.role` | CALIBRATION | 1 | 0.056 | measured | — |
| `role.held_unavailable` | `aq7.role` | CALIBRATION | 1 | n/a | held | — |
| `role.predicted_unknown` | `aq7.role` | TEST | 3 | 0.250 | measured | — |
| `role.concrete_confusion:drop->groove` | `aq7.role` | TEST | 2 | 0.167 | measured | — |
| `role.held` | `aq7.role` | TEST | 1 | n/a | held | — |
| `drop.false` | `aq7.drop_event` | CALIBRATION | 6 | 1.000 | measured | `H-AQ7-1027-05` |
| `drop.missed` | `aq7.drop_event` | CALIBRATION | 1 | 1.000 | measured | `H-AQ7-1027-S05` |
| `drop.timing_offset` | `aq7.drop_event` | CALIBRATION | n/a | n/a | not_applicable | — |
| `drop.false` | `aq7.drop_event` | TEST | 3 | 1.000 | measured | — |
| `drop.missed` | `aq7.drop_event` | TEST | 2 | 1.000 | measured | — |
| `drop.timing_offset` | `aq7.drop_event` | TEST | n/a | n/a | not_applicable | — |
| `drop.beatgrid_hold` | `aq7.drop_event` | TEST | 1 | n/a | held | — |

### 11.2 Hypothesis appendix

| hypothesis_id | observed_bucket | plane | support_cal | support_test | shortlist_eligible | evidence_state | change_class |
|---|---|---|---:|---:|---|---|---|
| `H-AQ7-1027-01` | `boundary.extra_or_duplicate` / `boundary.over_segmentation` | `aq7.boundary` | 6 / FP=23 | 3 / FP=16 | yes | measured | scoped_code |
| `H-AQ7-1027-02` | `role.confusion:intro->unknown` | `aq7.role` | 4 | 1 | yes | measured | existing_candidate |
| `H-AQ7-1027-03` | `role.concrete_confusion:build->groove` | `aq7.role` | 2 | 1 | yes | measured | existing_candidate |
| `H-AQ7-1027-04` | `role.confusion:groove->unknown` | `aq7.role` | 2 | 1 | yes | measured | existing_candidate |
| `H-AQ7-1027-05` | `drop.false` | `aq7.drop_event` | 6 | 3 | yes | measured | scoped_code |
| `H-AQ7-1027-S01` | `boundary.missed` | `aq7.boundary` | 1 | 0 | no (`OBSERVED_SINGLETON`) | measured | scoped_code |
| `H-AQ7-1027-S02` | `boundary.early` | `aq7.boundary` | 1 | 0 | no (`OBSERVED_SINGLETON`) | measured | scoped_code |
| `H-AQ7-1027-S03` | `role.confusion:build->unknown` | `aq7.role` | 1 | 0 | no (`OBSERVED_SINGLETON`) | measured | existing_candidate |
| `H-AQ7-1027-S04` | `role.concrete_confusion:intro->groove` | `aq7.role` | 1 | 1 | no (`OBSERVED_SINGLETON`) | measured | existing_candidate |
| `H-AQ7-1027-S05` | `drop.missed` | `aq7.drop_event` | 1 | 2 | no (`OBSERVED_SINGLETON`) | measured | scoped_code |

### 11.3 Signal availability appendix

| signal_family | evidence_state_usable | evidence_state_beatgrid_hold | consumed_by_live_path |
|---|---|---|---|
| energy/loudness | measured | held | yes |
| low_end_share | measured | held | yes |
| onset_density | measured | held | yes |
| rhythm_stability | measured | held | yes |
| timbre_delta | measured | held | yes |
| spectral_delta | measured | held | yes |
| recurrence | measured | held | yes |
| novelty/self_similarity | measured | held | yes |
| neighbor_delta | measured | held | yes |
| multi_bar_trend | measured | held | yes |
| relative_track_position | measured | held | yes |
| clap | not_applicable | not_applicable | no |
| stems | not_applicable | not_applicable | no |

---

## Non-goals (this slice)

- no `src/structure_v1.py` / `arrangement_classifier.py` / `section_signals.py` changes
- no #1025/#1026 harness edits
- no threshold/default/production switch
- no #1028 candidate implementation
- no committed WAV / raw JSON / private or absolute paths
- no optional-signal pseudo-labeling
- no `CANON_INDEX` edits in Task 2
