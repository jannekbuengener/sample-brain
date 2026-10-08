# AQ7 Structure, Arrangement Role & Drop Event KPI / Annotation Contract

**Status:** ACTIVE_SUPPORTING — KPI/annotation freeze for [#1023](https://github.com/jannekbuengener/sample-brain/issues/1023)
**Class:** ACTIVE_SUPPORTING
**Parents:** [#949](https://github.com/jannekbuengener/sample-brain/issues/949) (AQ7), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)
**Corpus follow-up:** [#1024](https://github.com/jannekbuengener/sample-brain/issues/1024) owns the reproducible public/synthetic ground-truth corpus.
**Related (by reference only):** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) portable eval envelope; [#957](https://github.com/jannekbuengener/sample-brain/issues/957) perturbation mechanics; [#958](https://github.com/jannekbuengener/sample-brain/issues/958) runtime methodology; [#959](https://github.com/jannekbuengener/sample-brain/issues/959) semantic determinism. AQ8 foundations are closed/merged — reuse, do not reopen.

Current read-only runtime context: `src/structure_v1.py` owns neutral bar-synchronous boundaries/sections; `src/arrangement_classifier.py` consumes those sections and emits arrangement roles plus `drop_onset` boundary events. `docs/ARRANGEMENT_SIGNAL_MATRIX_V1.md` and `docs/arrangement_confidence_override_v1.json` preserve the same ownership split.

## Architecture outcome

```text
AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT_FROZEN
```

This document freezes **ground-truth ownership, annotation semantics, matching tolerance, metric planes, denominators and partition policy** before any StructureV1 or ArrangementClassifier threshold/feature change. It does not authorize analyzer changes or a production switch.

## Ownership

| Concern | Owner |
|---|---|
| Neutral boundary / segment ground truth + AQ7 boundary metrics | this contract; corpus instances → #1024 |
| Arrangement role ground truth + AQ7 role metrics | this contract; corpus instances → #1024 |
| `drop_onset` event ground truth + AQ7 event metrics | this contract; corpus instances → #1024 |
| Neutral boundary positions at runtime | `StructureV1` |
| Role / event predictions at runtime | `ArrangementClassifier` |
| Portable observations / statuses | #956 |
| Perturbation mechanics | #957 |
| Runtime cold/steady methodology | #958 |
| Semantic repeatability | #959 |
| Algorithm / threshold changes | later AQ7 compare/promotion work, never this docs-only slice |

## Non-goals

- no StructureV1 / ArrangementClassifier code or threshold changes
- no UI / Arrangement product work
- no production promotion thresholds or numeric quality gates
- no private tracks, filenames, paths, annotations, DBs or audio in committed evidence
- no pseudo-ground-truth from StructureV1, ArrangementClassifier, stems, CLAP or other analyzer output
- no role logic creating or moving boundaries
- no `drop_onset`-as-section-role semantics
- no single opaque score combining boundary, role and event quality

## Three reporting planes — normative separation

1. `aq7.boundary` — neutral structure boundary / segmentation correctness.
2. `aq7.role` — section-role correctness on **frozen reference neutral sections**.
3. `aq7.drop_event` — `drop_onset` event correctness on **frozen reference neutral boundaries**.

Rules:

- Boundary success does not imply role success.
- Role success does not imply correct boundary placement.
- `drop_onset` is an event attached to a neutral boundary; it never creates a new boundary.
- AQ7 role/event baselines must not repair or move reference boundaries to make classification look better.
- When one plane lacks valid ground truth, that plane is `unknown` / HOLD while other planes may remain measurable.

## Portable domain tokens (#956)

| Domain token | Scope |
|---|---|
| `aq7.boundary` | neutral internal transition boundaries and boundary-derived segmentation |
| `aq7.role` | section roles on frozen reference sections |
| `aq7.drop_event` | `drop_onset` events anchored to frozen reference boundaries |

The #956 envelope remains domain-neutral. AQ7 metric meaning, matching and eligibility stay owned here.

## Ground-truth ownership

AQ7 ground truth is annotation/corpus truth, not analyzer output.

### Neutral boundary truth

- Reference boundaries are internal musical section transitions indexed by zero-based `bar_index`.
- Track start and track end define section extent but are not scored as discovered internal boundaries.
- A reference boundary may also carry `time_sec` when trustworthy annotation/timebase provenance exists.
- `bar_index` is the primary matching coordinate; seconds are secondary diagnostics only.
- Reference boundaries must not be generated from current StructureV1 output.

### Role truth

Frozen section-role vocabulary:

`intro`, `groove`, `build`, `drop`, `breakdown`, `outro`, `unknown`.

- Role labels attach to the **reference sections created by reference neutral boundaries**.
- `unknown` is a legitimate semantic label meaning the reference cannot defensibly assert one concrete v1 role.
- `unknown` must not be used as a shortcut for unresolved annotator disagreement; disagreement has its own annotation status.
- Role evaluation never changes section boundaries.

### Drop-event truth

- The only v1 event is `drop_onset`.
- Every annotated `drop_onset` references a reference neutral boundary identity / bar position.
- An event may coexist with any reference section-role label; role and event truth are independent.
- A corpus record is event-eligible only when annotation is complete enough to state the full expected `drop_onset` set, including an explicit empty set when the track has no eligible drop event.

## Minimum annotation record semantics for #1024

The corpus implementation may choose its exact JSON shape, but it must preserve at least:

- stable `record_id` and corpus/version identity;
- split role: `CALIBRATION` or `TEST` / `HOLDOUT`;
- reference internal boundaries with stable ids and zero-based `bar_index`;
- optional `time_sec` plus provenance when seconds are trustworthy;
- reference sections derived from those boundaries;
- one role value per eligible reference section;
- zero or more `drop_onset` events referencing reference boundary ids;
- annotation status/provenance per plane;
- BeatGrid/timebase provenance or an explicit missing/insufficient state;
- no private path, filename or audio identity in committed portable evidence.

## Boundary matching tolerance — frozen

```text
BOUNDARY_MATCH_TOLERANCE_BARS = 1
```

Primary boundary/event matching is therefore **±1 musical bar** around a reference boundary.

Rationale:

- StructureV1 is explicitly bar-synchronous, so a bar unit matches the runtime representation.
- One-bar tolerance represents near-boundary annotation/detection disagreement without silently accepting multi-bar structural errors.
- A fixed seconds window would change musical strictness with tempo and is therefore not the primary tolerance.
- The three-second window in `ARRANGEMENT_PILOT_V1.md` was explicitly descriptive pilot evidence and is **not** promoted into AQ7 ground truth.

Matching policy:

1. sort reference and predicted internal boundaries by bar index;
2. use one-to-one, order-preserving matching;
3. maximize the number of pairs with `abs(pred_bar - ref_bar) <= 1`;
4. among equally maximal matchings, minimize total absolute bar error;
5. deterministic ties prefer the earlier prediction, then earlier reference id/order;
6. one prediction can credit at most one reference boundary and vice versa.

Report exact-bar matches (`abs_error_bars == 0`) separately as a diagnostic. Do not silently tighten or loosen the ±1-bar primary tolerance per candidate.

Seconds reporting for matched pairs:

- signed and absolute seconds error may be reported only when both prediction and reference seconds have trustworthy provenance;
- report median/p95 absolute seconds error as secondary diagnostics;
- no independent seconds-based match tolerance is frozen here;
- missing seconds evidence is `unknown`, never numeric zero.

## Boundary / segmentation KPI (`aq7.boundary`)

| Metric id | Direction | Definition |
|---|---|---|
| `aq7.boundary.precision_1bar` | maximize | matched predicted boundaries / predicted internal boundaries |
| `aq7.boundary.recall_1bar` | maximize | matched reference boundaries / eligible reference internal boundaries |
| `aq7.boundary.f1_1bar` | maximize | harmonic mean of precision and recall |
| `aq7.boundary.exact_hit_rate` | maximize | matched pairs with zero bar error / matched pairs |
| `aq7.boundary.abs_error_bars_median` | minimize | median `abs(pred_bar-ref_bar)` over matched pairs |
| `aq7.boundary.abs_error_bars_p95` | minimize | p95 absolute bar error over matched pairs |
| `aq7.boundary.miss_rate` | minimize | unmatched eligible reference boundaries / eligible reference boundaries |
| `aq7.boundary.extra_rate` | minimize | unmatched predictions / predicted internal boundaries |
| `aq7.boundary.section_count_abs_error` | minimize | absolute predicted-vs-reference section-count error per record after ignore-mask filtering, then aggregate |
| `aq7.boundary.segment_iou_weighted` | maximize | reference-bar-duration-weighted IoU of deterministically one-to-one order-matched boundary-derived sections |
| `aq7.boundary.coverage` | maximize | boundary-eligible records with a usable boundary prediction surface / boundary-eligible records |

Undefined denominators are `not_applicable` / `unknown` as appropriate, never coerced to zero.

### Boundary eligibility / prediction surface — frozen

Annotation-side **boundary-eligible** requires complete internal-boundary annotation for the plane with status `adjudicated` or `single_source` for the scored locus set (ambiguous loci are handled by the ignore mask; they do not by themselves make an otherwise complete record boundary-ineligible).

Prediction-side **usable boundary prediction surface** requires that StructureV1 completed a boundary pass whose public status is one of:

- `ok` / `partial` — usable; predicted internal boundaries (possibly empty after filtering) enter correctness denominators;
- `no_result` with reason `NO_BOUNDARY_CANDIDATE` — usable **empty** prediction surface; predicted count is 0 and enters precision/extra as an empty set (`not_applicable` when the denominator is 0), while recall/miss still score against eligible references;
- `no_result` with reason `DOWNBEATS_UNAVAILABLE` or `FEATURES_UNAVAILABLE` — **not** usable; boundary correctness is HOLD / `unknown` for the record;
- `failed` or any `no_result` without one of the reason codes above — **not** usable; HOLD / `unknown`.

When reason codes are absent from the consumed prediction artifact, treat undifferentiated `no_result` as **not usable** (HOLD). Do not invent a `NO_BOUNDARY_CANDIDATE` distinction the artifact does not expose.

Frozen coverage formula:

```text
aq7.boundary.coverage =
  |{boundary-eligible records with usable boundary prediction surface}|
  / |{boundary-eligible records}|
```

Empty boundary-eligible set → `not_applicable`. Low coverage must not be hidden by dropping unusable records from P/R only without reporting this metric.

### Segment-IoU policy

Bar-range intervals are **half-open** `[start_bar, end_bar)`, matching StructureV1 adjacent boundary indices (`end_bar` of one section equals `start_bar` of the next; length = `end_bar - start_bar`). Inclusive endpoint interpretations are forbidden for overlap, IoU, and reference weights.

Reference and predicted sections are formed by adding the implicit track start/end around their **eligible** reference internal boundaries and **unmasked** predicted internal boundaries (same filtered sets used for boundary P/R). Section pairing is deterministic one-to-one and order-preserving:

1. sort reference and predicted sections by start bar, then end bar, then stable id/order;
2. maximize the number of pairs whose bar-range overlap is strictly positive;
3. among equally maximal pairings, maximize total overlap length in bars;
4. among remaining ties, minimize `|pred_start - ref_start| + |pred_end - ref_end|`;
5. final ties prefer the earlier prediction, then earlier reference id/order;
6. one predicted section matches at most one reference section and vice versa.

For each eligible reference section, compute interval IoU in bar coordinates; weight by reference section length in bars. Unmatched reference sections contribute `0` IoU. This remains secondary to boundary P/R/F1 and must not hide over/under-segmentation.

## Role KPI (`aq7.role`)

Role evaluation consumes **frozen reference sections** from the corpus. It does not use StructureV1-predicted boundaries for the primary role baseline. That keeps role-classifier quality separate from segmentation quality.

Primary concrete-role set:

`intro`, `groove`, `build`, `drop`, `breakdown`, `outro`.

`unknown` stays in the confusion matrix and coverage/abstention evidence but is excluded from the primary concrete-role macro-F1 denominator.

| Metric id | Direction | Definition |
|---|---|---|
| `aq7.role.macro_f1` | maximize | unweighted mean F1 over the six concrete roles |
| `aq7.role.coverage` | maximize | non-`unknown` predictions / eligible concrete-role reference sections |
| `aq7.role.bar_weighted_accuracy` | maximize | correctly predicted role bars / eligible reference-role bars; diagnostic, not a replacement for macro-F1 |
| `aq7.role.unknown_rate` | neutral | predicted `unknown` / all role-eligible sections |
| `aq7.role.unknown_reference_recall` | maximize | reference-`unknown` sections predicted `unknown` / eligible reference-`unknown` sections |

Also report:

- per-role precision / recall / F1;
- full predicted × reference confusion matrix including `unknown`;
- support count and support bars per reference role;
- confusion pairs with support, especially `groove↔drop`, `build↔intro/groove`, and `breakdown↔outro` when they occur;
- optional seconds-weighted accuracy only when section-time provenance is trustworthy.

Overall accuracy alone is insufficient because long groove/drop sections can hide poor minority-role performance.

### Role eligibility / prediction surface — frozen

Annotation-side **role-eligible** requires complete role labels on the frozen reference sections used for scoring, with plane status `adjudicated` or `single_source` for those eligible sections (sections excluded by ambiguous-boundary carry-over are omitted from role denominators, not converted to semantic `unknown`).

Prediction-side **usable role prediction surface** requires that ArrangementClassifier completed a section-role classification pass over those frozen reference sections and the arrangement/track status is not `failed` or `unavailable`.

| Prediction state | Definition | Enters role correctness / coverage denominators? |
|---|---|---|
| Concrete or semantic-`unknown` prediction | Emitted section role under a usable surface | Yes |
| Track/pass HOLD | Status `failed` / `unavailable`, or no completed role pass | No — record/sections are `unknown` / `excluded` for role correctness; do **not** invent per-section semantic `unknown` predictions |
| Missing section under usable surface | Completed pass but no role emitted for an eligible reference section | Count as predicted semantic `unknown` only when the public surface explicitly emits `unknown`; otherwise `controlled_failure` / HOLD for that section, never a fabricated concrete role |

`aq7.role.coverage` therefore measures classifier abstention (`unknown` predictions) on eligible concrete-role reference sections under a usable surface. Execution failures that make the surface unusable lower role coverage only when reported as an explicit role-plane coverage / eligibility diagnostic; they must not inflate confusion-matrix `unknown` counts.

## Drop-event KPI (`aq7.drop_event`)

`drop_onset` predictions are matched to annotated reference `drop_onset` events with the same frozen **±1 bar** one-to-one matching policy used for neutral boundaries. The event still must reference a neutral boundary; matching tolerance does not grant event logic authority to invent a boundary.

| Metric id | Direction | Definition |
|---|---|---|
| `aq7.drop_event.precision_1bar` | maximize | matched predicted drop events / predicted drop events |
| `aq7.drop_event.recall_1bar` | maximize | matched reference drop events / eligible reference drop events |
| `aq7.drop_event.f1_1bar` | maximize | harmonic mean of event precision and recall |
| `aq7.drop_event.abs_error_bars_median` | minimize | median absolute bar error over matched drop events |
| `aq7.drop_event.abs_error_bars_p95` | minimize | p95 absolute bar error over matched drop events |
| `aq7.drop_event.false_rate` | minimize | unmatched predicted drop events / predicted drop events |
| `aq7.drop_event.miss_rate` | minimize | unmatched reference drop events / eligible reference drop events |
| `aq7.drop_event.coverage` | maximize | event-eligible records with a usable event prediction surface / event-eligible records (see Drop-event eligibility) |

For records with a complete explicit empty reference event set, any predicted `drop_onset` is a false positive. Records with incomplete event annotation are `unknown` / HOLD for event correctness and must not be treated as no-drop truth.

### Drop-event eligibility / prediction surface — frozen

Annotation-side **event-eligible** requires all of:

1. drop-event annotation status is `adjudicated` or `single_source` at record/plane level (not whole-plane `ambiguous` / `unavailable`);
2. the full expected `drop_onset` set is stated, including an explicit empty set when the track has none;
3. annotated events may reference excluded / ambiguous boundaries; those individual events are removed from drop-event correctness denominators by the ignore-mask / carry-over rules below, but they do **not** make the whole record event-ineligible when at least the annotation set is complete;
4. a usable bar mapping exists for ±1-bar matching; otherwise the record is HOLD for scored event timing/presence and is **not** event-eligible for P/R/F1.

Partial-ambiguity rule: a record with mixed clean and ambiguous-anchored drop events remains event-eligible. Only the ambiguous-anchored reference events and mask-overlapping predictions are excluded; remaining clean events still enter P/R/F1.

Prediction-side **usable event prediction surface** requires all of:

1. the record is event-eligible;
2. ArrangementClassifier completed an event-classification pass over the **frozen reference neutral boundaries** used for AQ7 event scoring;
3. arrangement/structure status for that pass is not `failed` or `unavailable`.

Status `uncertain` (for example inferred bar grid) remains a usable surface for presence scoring when the pass completed; provenance must still be reported. It does not convert scored negatives into HOLD by itself.

When the surface is not usable, drop-event correctness metrics for the record are `unknown` / HOLD / `excluded` as appropriate. Those records do **not** enter P/R/F1/false/miss denominators and do **not** count in the coverage numerator.

#### Positive vs negative vs abstention (runtime-honest)

Current runtime (`classify_events` / `_boundary_drop_onset_candidate` in `src/arrangement_classifier.py`) emits only positive `drop_onset` events. A single non-emission / `None` covers ordinary below-threshold negatives, unknown following role, and missing required features. This contract **does not invent** distinctions the public prediction surface does not expose, and #1023 does not change that runtime API.

| Prediction state | Definition | Enters event P/R/false/miss denominators? |
|---|---|---|
| Positive prediction | Explicit emitted `drop_onset` on a non-masked boundary | Yes — member of the predicted event set |
| Negative prediction | Usable surface and no emitted `drop_onset` for the evaluated boundary set / record | Yes — absence is scored as no-event (miss if refs remain unmatched; empty predicted set is valid) |
| Abstention / HOLD | Surface not usable, or annotation incomplete / plane excluded | No — `unknown` / `excluded`; neither miss nor true-negative credit |

Normative consequences:

- under a usable surface, non-emission is a **negative prediction**, never a coverage abstention that removes misses from recall;
- coverage abstention/HOLD is reserved for unusable surface or ineligible annotation;
- evaluators must not invent separate abstention classes for unknown-role vs missing-features vs below-threshold without a future explicit runtime status channel (out of scope here);
- that coalesced non-emission is a documented **coverage / attribution limitation** for later #1027 diagnostics, not a license to fabricate correctness.

Frozen coverage formula:

```text
aq7.drop_event.coverage =
  |{event-eligible records with usable event prediction surface}|
  / |{event-eligible records}|
```

Empty event-eligible set → `not_applicable`, never numeric zero.

## Corpus-level aggregation — frozen

Primary multi-record aggregation for AQ7 count-ratio KPIs is **micro**: pool eligible counts across records in the evaluated partition, then compute the ratio once. Unweighted means of per-record ratios (**macro-of-ratios**) are diagnostic only and must not replace micro for candidate ranking on those metrics.

Shared rules for all three planes:

1. Only records/items eligible for the plane and metric enter that metric's corpus aggregate.
2. A record with an undefined denominator for a metric is excluded from that metric's corpus ratio and counted under `not_applicable` / `unknown` — never coerced to numeric zero success or failure.
3. Incomplete, plane-ineligible, masked-only, or HOLD records are excluded from correctness aggregates for that plane; they may still appear in coverage / annotation-health evidence.
4. No track-duration, confidence, or ad-hoc sample-weight reweighting of primary P/R/F1 beyond the pooling rules below.
5. Empty contributing set for a metric → corpus value `not_applicable`, never `0.0`.
6. CALIBRATION and TEST/HOLDOUT aggregates are computed separately and never mixed.
7. When either precision or recall is `not_applicable` at corpus level, the corresponding F1 is `not_applicable`.

### `aq7.boundary` aggregation

| Metric id | Corpus rule |
|---|---|
| `precision_1bar`, `recall_1bar`, `miss_rate`, `extra_rate`, `exact_hit_rate` | **micro** — sum numerators / sum denominators over eligible records with usable boundary surface after ignore-mask filtering |
| `f1_1bar` | harmonic mean of corpus micro precision and corpus micro recall |
| `abs_error_bars_median`, `abs_error_bars_p95` | **pooled sample** — concatenate all matched-pair absolute bar errors across eligible records, then median / p95 on that multiset. Empty matched-pair set → `not_applicable`. Do **not** use median-of-per-record-medians as primary. Percentile math: linear interpolation on a sorted copy, same family as `src.measurement.stats.percentile` (#958). |
| `section_count_abs_error` | **macro mean** — unweighted mean of per-record `abs(pred_section_count - ref_section_count)` over records with usable boundary surface. Counts use **filtered** inputs only: `ref_section_count = 1 + eligible_reference_internal_boundaries`, `pred_section_count = 1 + unmasked_predicted_internal_boundaries`. Ambiguous/excluded references and masked predictions do not enter either count. |
| `segment_iou_weighted` | **pooled weighted** — across all eligible reference sections in the partition, `sum(IoU_i * weight_i) / sum(weight_i)` with `weight_i` = reference section length in bars |
| `coverage` | **record-level rate** — usable-surface boundary-eligible records / boundary-eligible records |

### `aq7.role` aggregation

| Metric id | Corpus rule |
|---|---|
| per-role precision / recall / F1 and confusion matrix | **micro** — pool section-level confusion counts across eligible sections/records; derive each role's P/R/F1 from the pooled matrix |
| `macro_f1` | unweighted mean of the six concrete-role F1 values from that pooled matrix. A concrete role with zero reference support **and** zero predictions is `not_applicable` for that role's F1 and is **omitted** from the macro-mean denominator (not coerced to 0). If all six are omitted, `macro_f1` is `not_applicable`. |
| `coverage`, `unknown_rate`, `unknown_reference_recall` | **micro** section-count ratios over eligible sections |
| `bar_weighted_accuracy` | **pooled bars** — correct eligible bars / eligible reference-role bars across records |

### `aq7.drop_event` aggregation

| Metric id | Corpus rule |
|---|---|
| `precision_1bar`, `recall_1bar`, `false_rate`, `miss_rate` | **micro** — pool event counts over event-eligible records with usable prediction surface, after event ignore-mask filtering |
| `f1_1bar` | harmonic mean of corpus micro precision and corpus micro recall |
| `abs_error_bars_median`, `abs_error_bars_p95` | pooled matched-event absolute bar errors; same median/p95 rule as boundary |
| `coverage` | **record-level rate** — usable-surface event-eligible records / event-eligible records (formula above) |

## Annotation status / disagreement policy

Use annotation evidence states distinct from semantic labels:

- `adjudicated` — reviewed canonical reference accepted;
- `single_source` — one acceptable source, no disagreement evidence;
- `ambiguous` — unresolved disagreement or inherently unstable reference;
- `unavailable` — no defensible ground truth for this plane.

Normative rules:

1. Boundary annotator spread up to one bar may be adjudicated to one canonical bar **only when the corpus records the source spread/provenance**. Without adjudication it remains `ambiguous`.
2. Boundary disagreement greater than one bar without adjudication is `ambiguous`; the boundary and dependent reference sections are excluded from strict correctness denominators. Predictions inside the disputed region are handled by the **ignore mask** below so ambiguity is not double-counted as a false positive.
3. Role disagreement between concrete labels is `ambiguous`, not silently converted to semantic `unknown`.
4. Semantic `unknown` is a valid reference label only when annotation itself asserts that no concrete v1 role is defensible.
5. Drop-event disagreement is handled independently from role disagreement.
6. Ambiguous/unavailable annotations contribute annotation-health/coverage evidence but never fabricated correctness values.

### Ambiguous boundary ignore mask — frozen

Annotation ambiguity must not be punished as an ordinary false positive.

When an ambiguous reference boundary is excluded from strict boundary denominators, construct a deterministic **ignore mask** in bar coordinates:

1. If the corpus records an inclusive annotator bar spread `[spread_lo, spread_hi]` for the disputed boundary:
   `mask_lo = spread_lo - BOUNDARY_MATCH_TOLERANCE_BARS`, `mask_hi = spread_hi + BOUNDARY_MATCH_TOLERANCE_BARS`.
2. Else if only a single disputed candidate bar `b` is recorded:
   `mask_lo = b - BOUNDARY_MATCH_TOLERANCE_BARS`, `mask_hi = b + BOUNDARY_MATCH_TOLERANCE_BARS`.
3. Else (ambiguous with no recorded bar locus): the record's entire `aq7.boundary` correctness plane is `ambiguous` / `unavailable` — exclude the record from boundary P/R/extra/miss/IoU correctness aggregates rather than inventing a mask.

Masked prediction rules:

- A predicted internal boundary whose `bar_index` lies in any ignore mask for that record is **masked**.
- Masked predictions are excluded from one-to-one matching against eligible references.
- Masked predictions are excluded from `precision_1bar` and `extra_rate` predicted-count denominators.
- Masked predictions never count as true positives or false positives for `aq7.boundary`.
- Eligible (non-ambiguous) reference boundaries remain in recall denominators; matching uses only unmasked predictions.

Dependent-plane carry-over:

- Reference sections that depend on an ambiguous boundary remain excluded from role correctness denominators.
- Annotated `drop_onset` events anchored to an ambiguous / excluded boundary are excluded from drop-event correctness denominators.
- Predicted `drop_onset` events whose bar falls inside a boundary ignore mask for that record are likewise masked: excluded from event matching and from event precision / false_rate denominators.

## BeatGrid / timebase dependency

AQ7 must expose BeatGrid provenance rather than laundering grid errors into StructureV1/ArrangementClassifier scores.

- Reference `bar_index` comes from corpus annotation truth, not from current analyzer output.
- Analyzer-side boundary bars are valid for comparison only when a deterministic predicted-bar mapping exists.
- Inferred 4/4 grids are allowed as a **measured provenance bucket**, not as observed-downbeat truth.
- If the analyzer cannot establish a usable bar grid, boundary/event timing correctness is `unknown` / controlled HOLD; do not invent positions.
- Seconds diagnostics require trustworthy reference and prediction time coordinates; otherwise omit them.
- Later diagnostics (#1027) must separate BeatGrid/provenance-limited failures from StructureV1/role/drop logic failures.

The private four-track pilot in `ARRANGEMENT_PILOT_V1.md` remains descriptive evidence only. Its inferred-grid results and three-second “near” aid are not benchmark truth.

## Partition policy

| Role | Policy |
|---|---|
| DEVELOPMENT / CALIBRATION | annotation/corpus debugging, threshold/feature exploration and candidate comparison; may influence the next bounded candidate |
| TEST / HOLDOUT | frozen evaluation after candidate/config freeze; **never tuning feedback** |

Rules:

- #1024 freezes record identities, annotations and partition membership before baseline/candidate work.
- Once TEST/HOLDOUT is revealed for a candidate, no annotation, tolerance, label-vocabulary, feature-selection or threshold edits may be made from those results.
- Fixing a demonstrated annotation defect requires a versioned corpus revision and invalidates prior directly comparable holdout claims for the changed records.
- Private owner tracks may be reality-check evidence only; they do not set public thresholds and never enter committed artifacts with private identifiers/audio.

## #956 observation status policy

AQ7 uses the existing portable vocabulary exactly:

- `measured` — finite metric value exists;
- `unknown` — evidence missing/ambiguous/HOLD;
- `not_applicable` — metric has no valid denominator for that record/plane;
- `controlled_failure` — analyzer/adapter failed in a controlled way;
- `excluded` — corpus record/annotation explicitly ineligible and emits no observation.

Never encode unknown/ambiguous/ineligible evidence as numeric zero.

## Shared quality dimensions (#942)

| Dimension | `aq7.boundary` | `aq7.role` | `aq7.drop_event` |
|---|---|---|---|
| correctness | selected | selected | selected |
| coverage / abstention | selected | selected (`unknown` first-class) | selected |
| error buckets / confusion | selected (early/late, miss, extra, over/under) | selected (per-role confusion) | selected (false/missed/timing) |
| baseline-vs-candidate delta | reserved for later compare | reserved | reserved |
| robustness / metamorphic | expectations below; mechanics → #957 | same | same |
| determinism / reproducibility | consume #959 | consume #959 | consume #959 |
| runtime median/p95 | consume #958 | consume #958 | consume #958 |
| calibration | out of scope — no calibrated AQ7 probability contract | out of scope; classifier scores are track-relative heuristic scores | out of scope |
| difficult slices | selected | selected | selected |

## Difficult / explanatory slices

Where corpus support exists, report at least:

- observed downbeats vs inferred 4/4 bar grid;
- short vs long sections;
- sparse vs dense boundary tracks;
- early-track / middle / late-track transitions;
- each concrete role support slice;
- reference `unknown` role slice;
- tracks with zero / one / multiple annotated `drop_onset` events;
- annotation-status buckets (`adjudicated`, `single_source`, `ambiguous`).

Signal families from `ARRANGEMENT_SIGNAL_MATRIX_V1.md` (energy/loudness, low-end, onset/rhythm, timbre/spectral, recurrence/self-similarity/novelty, neighbor/multi-bar trends) are **diagnostic attribution only**. They are not ground truth.

## Perturbation expectations (#957) — semantic only

Mechanics/provenance remain owned by #957.

| Transform | Boundary expectation | Role expectation | Drop-event expectation |
|---|---|---|---|
| `gain` / `peak_normalize` | invariant where musical structure is unchanged | invariant | invariant |
| `to_mono` / `to_stereo` | invariant where conversion preserves content | invariant | invariant |
| `resample` | bar identities invariant; seconds comparable on shared transformed timebase | invariant | bar identity invariant |
| `pad_silence` / `trim` | absolute time may transform; retained musical bar transitions must map through transformed annotation policy | roles of retained sections invariant | event absolute time transforms with retained boundary |
| `pitch_shift` | invariant for structure | role invariant where pitch-only shift preserves arrangement function | invariant |
| `time_stretch` | bar identity/ordering invariant; seconds scale with transform | role invariant | bar identity invariant; seconds scale |

No tolerance or promotion gate is introduced by this transform table.

## Automation-facing contract

To support later #1040 orchestration without re-deriving AQ7 semantics, machine-readable runs should carry:

- one of the three stable domain tokens above;
- stable corpus/partition/candidate/config identities;
- the frozen metric ids from this contract;
- explicit eligibility and #956 status;
- BeatGrid/timebase provenance;
- annotation status/provenance;
- per-record error buckets needed by #1027;
- no free-form agent judgment as the only decision input.

`#1024` owns the concrete corpus id/version and record schema. Until it is delivered:

```text
AQ7_ANNOTATED_CORPUS = HOLD_PENDING_1024
```

This HOLD does not weaken the KPI freeze; it means measurable baseline execution waits for real ground truth rather than inventing it.

## Runtime / determinism dimensions (by reference)

| Dimension | Authority | AQ7 use |
|---|---|---|
| Runtime median/p95 | #958 | StructureV1 boundary path and ArrangementClassifier role/event path, reported separately where practical |
| Semantic determinism | #959 | identical input/config/provenance must reproduce boundary bars, section-role projection and event bars semantically |
| Portable evidence | #956 | path-safe AQ7 observations; no private audio/paths |

Current classifier score cutoffs (for example role score separation or event heuristic thresholds) are **baseline implementation context only**. They are not KPI tolerances or promotion gates frozen here.

## Handoff to later AQ7 slices

- #1024: freeze the public/synthetic corpus implementing these annotation semantics.
- #1025: measure StructureV1 boundary/segmentation only.
- #1026: measure roles + `drop_onset` on frozen reference boundaries/sections.
- #1027: explain failures; keep BeatGrid, boundary, role and event causes separate.
- #1028: compare bounded candidates on CALIBRATION only.
- #1030: one locked TEST/HOLDOUT evaluation after freeze.
- #1031: evidence-backed decision memo; no production switch inside the memo.

## Evidence reused — not reopened

- `src/structure_v1.py` — neutral bar-synchronous boundary owner.
- `src/arrangement_classifier.py` — role/event consumer; cannot move boundaries.
- `docs/ARRANGEMENT_SIGNAL_MATRIX_V1.md` — signal/ownership separation.
- `docs/arrangement_confidence_override_v1.json` — independent boundary vs role/event status and `drop_onset` semantics.
- `docs/ARRANGEMENT_PILOT_V1.md` — descriptive private pilot only; not benchmark truth.
- closed #950 / #956–#960 — reusable evaluation foundation.

## Exit vocabulary

Exactly one:

- `AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT_FROZEN`
- `AQ7_KPI_CONTRACT_INSUFFICIENT`

This slice exits:

```text
AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT_FROZEN
```

The measurable corpus remains `HOLD_PENDING_1024`; missing ground truth is not fabricated.