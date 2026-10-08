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
| `aq7.boundary.section_count_abs_error` | minimize | absolute predicted-vs-reference section-count error per record, then aggregate |
| `aq7.boundary.segment_iou_weighted` | maximize | reference-bar-duration-weighted IoU of deterministically order-matched boundary-derived sections |

Undefined denominators are `not_applicable` / `unknown` as appropriate, never coerced to zero.

### Segment-IoU policy

Reference and predicted sections are formed by adding the implicit track start/end around their internal boundaries. Section pairs are matched monotonically by maximum bar-range overlap. For each eligible reference section, compute interval IoU in bar coordinates; weight by reference section length in bars. Unmatched reference sections contribute `0` IoU. This remains secondary to boundary P/R/F1 and must not hide over/under-segmentation.

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
| `aq7.drop_event.coverage` | maximize | records with complete event annotation and a usable event prediction surface / event-eligible records |

For records with a complete explicit empty reference event set, any predicted `drop_onset` is a false positive. Records with incomplete event annotation are `unknown` / HOLD for event correctness and must not be treated as no-drop truth.

## Annotation status / disagreement policy

Use annotation evidence states distinct from semantic labels:

- `adjudicated` — reviewed canonical reference accepted;
- `single_source` — one acceptable source, no disagreement evidence;
- `ambiguous` — unresolved disagreement or inherently unstable reference;
- `unavailable` — no defensible ground truth for this plane.

Normative rules:

1. Boundary annotator spread up to one bar may be adjudicated to one canonical bar **only when the corpus records the source spread/provenance**. Without adjudication it remains `ambiguous`.
2. Boundary disagreement greater than one bar without adjudication is `ambiguous`; the boundary and dependent reference sections are excluded from strict correctness denominators.
3. Role disagreement between concrete labels is `ambiguous`, not silently converted to semantic `unknown`.
4. Semantic `unknown` is a valid reference label only when annotation itself asserts that no concrete v1 role is defensible.
5. Drop-event disagreement is handled independently from role disagreement.
6. Ambiguous/unavailable annotations contribute annotation-health/coverage evidence but never fabricated correctness values.

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