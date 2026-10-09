# AQ7 Structure / Role / Drop Diagnostics — Error Buckets + Signal Attribution

**Status:** ACTIVE_SUPPORTING — diagnostics / evidence for [#1027](https://github.com/jannekbuengener/sample-brain/issues/1027)
**Class:** ACTIVE_SUPPORTING
**Parents:** [#949](https://github.com/jannekbuengener/sample-brain/issues/949) (AQ7), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)
**Depends on (CLOSED):** [#1025](https://github.com/jannekbuengener/sample-brain/issues/1025) boundary baseline, [#1026](https://github.com/jannekbuengener/sample-brain/issues/1026) role/drop baseline, [#1024](https://github.com/jannekbuengener/sample-brain/issues/1024) corpus, [#1023](https://github.com/jannekbuengener/sample-brain/issues/1023) KPI
**Normative KPI:** [`AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md`](AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md)
**Corpus:** [`AQ7_STRUCTURE_ROLE_DROP_CORPUS.md`](AQ7_STRUCTURE_ROLE_DROP_CORPUS.md) / `sample-brain.aq7.structure-role-drop.synthetic.v1`
**Boundary baseline:** [`AQ7_STRUCTURE_BOUNDARY_BASELINE.md`](AQ7_STRUCTURE_BOUNDARY_BASELINE.md) / `structure_v1.baseline.v1`
**Role/drop baseline:** [`AQ7_STRUCTURE_ROLE_DROP_BASELINE.md`](AQ7_STRUCTURE_ROLE_DROP_BASELINE.md) / `arrangement_classifier.baseline.v1`
**Signal ownership context (diagnostic only):** [`../ARRANGEMENT_SIGNAL_MATRIX_V1.md`](../ARRANGEMENT_SIGNAL_MATRIX_V1.md)
**Related bootstrap:** [#1040](https://github.com/jannekbuengener/sample-brain/issues/1040) quality-loop consumer of stable bucket IDs (orchestrator out of scope here)
**Downstream (not started here):** [#1028](https://github.com/jannekbuengener/sample-brain/issues/1028) candidate compare

## Architecture outcome

```text
AQ7_DIAGNOSTICS_PARTIAL_HOLD
```

This document turns the measured [#1025](https://github.com/jannekbuengener/sample-brain/issues/1025) / [#1026](https://github.com/jannekbuengener/sample-brain/issues/1026) baselines into **explainable failure buckets**, **BeatGrid/provenance separation**, and **bounded CALIBRATION hypotheses** for later candidate comparison. Planes stay separate. It does **not** change StructureV1, ArrangementClassifier, SectionSignals, BeatGrid, thresholds/defaults, set promotion gates, or start [#1028](https://github.com/jannekbuengener/sample-brain/issues/1028).

`PARTIAL_HOLD` is intentional: dominant measured buckets are enumerated with support, but the frozen synthetic pack is thin (10 fixtures; many confusion pairs `n=1`), BeatGrid provenance HOLD remains material on TEST, and no durable global AQ7 quality score or promotion threshold is inventable from this corpus.

## 1. Scope / Evidence Chain

| In | Out |
|---|---|
| Bucket boundary / role / drop failures from frozen #1025+#1026 evidence | Analyzer / harness / threshold changes |
| Diagnostic signal availability + correlation notes | Causal claims / GT leakage into prediction |
| BeatGrid/provenance vs analyzer attribution hierarchy | Candidate implementation (#1028) |
| Bounded CALIBRATION hypotheses with support | TEST/HOLDOUT tuning feedback |
| Machine-facing bucket appendix for #1040 | Orchestrator / autonomous promotion |

### Evidence identities (exact)

| Field | Boundary (#1025) | Role/drop (#1026) |
|---|---|---|
| `document_type` | `sample-brain.aq7.structure-boundary-baseline.v1` | `sample-brain.aq7.structure-role-drop-baseline.v1` |
| `schema_version` | `1.0.0` | `1.0.0` |
| `candidate_id` | `structure_v1.baseline.v1` | `arrangement_classifier.baseline.v1` |
| `corpus_id` | `sample-brain.aq7.structure-role-drop.synthetic.v1` | same |
| `corpus_version` | `1.0.0` | `1.0.0` |
| `generator_seed` | `1024001` | `1024001` |
| Exit token | `AQ7_STRUCTURE_BOUNDARY_BASELINE_PARTIAL_HOLD` | `AQ7_ROLE_DROP_BASELINE_PARTIAL_HOLD` |
| Boundary context | n/a (owner) | `boundary_reference = structure_v1.baseline.v1` |

External JSON evidence was regenerated with the frozen harnesses only (outside the checkout). Exact floats live in those uncommitted artifacts; portable rounded aggregates below match the published #1025/#1026 baseline tables. No WAV/JSON committed.

Repro (external workdir only):

```powershell
python -m src.aq7_structure_boundary_baseline `
  --work-dir <external>/aq7-structure-role-drop-corpus `
  --output <external>/aq7-structure-boundary-baseline.json

python -m src.aq7_structure_role_drop_baseline `
  --work-dir <external>/aq7-structure-role-drop-corpus `
  --output <external>/aq7-structure-role-drop-baseline.json
```

### Attribution hierarchy (fail-closed)

A fixture/case is attributed to the **first** applicable layer; deeper layers must not double-count the same HOLD/ineligible surface:

1. Eligibility / annotation (ignore-mask, incomplete annotation)
2. BeatGrid / provenance HOLD
3. Analyzer / feature surface failure
4. Boundary geometry failure (`aq7.boundary`)
5. Signal availability (diagnostic only)
6. Role classifier outcome (`aq7.role`)
7. Drop classifier outcome (`aq7.drop_event`)

### Thin-corpus warning

| Slice | Count |
|---|---:|
| Fixtures total | 10 (CAL 6 / TEST 4) |
| Boundary-eligible | CAL 6 / TEST 3 |
| BeatGrid HOLD | TEST 1 (`aq7-synth-beatgrid-hold-test-001`) |
| Role concrete support | CAL 17 / TEST 12 (HOLD fixture excluded) |
| Drop reference support | CAL 1 / TEST 2 |

`dominant` requires support ≥ 2 within plane×split. Support 1 is labeled `DOMINANT_ON_THIN_CORPUS` / singleton — measured, not a durable rate.

## 2. Boundary Failure Buckets

Plane: `aq7.boundary` only. Denominators exclude BeatGrid HOLD and ignore-masked loci.

### Aggregate (rounded; matches #1025)

| Partition | P@1bar | R@1bar | F1 | support | FP | FN | over-seg rate | under-seg rate | section-count abs err | BeatGrid HOLD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CALIBRATION | 0.343 | 0.923 | 0.500 | 13 | 23 | 1 | 1.0 | 0.0 | 3.67 | 0 |
| TEST/HOLDOUT | 0.360 | 1.000 | 0.529 | 9 | 16 | 0 | 1.0 | 0.0 | 5.33 | 1 |

### Bucket inventory

| bucket_id | split | support | share / note | fixture_ids | ranking |
|---|---|---:|---|---|---|
| `boundary.over_segmentation` | CAL | 6/6 eligible | rate 1.0 | all CAL eligible | **dominant** |
| `boundary.over_segmentation` | TEST | 3/3 eligible | rate 1.0 | all TEST eligible | **dominant** |
| `boundary.extra_or_duplicate` | CAL | FP=23 | 23/35 unmasked preds | all CAL eligible | **dominant** (with over-seg) |
| `boundary.extra_or_duplicate` | TEST | FP=16 | 16/25 unmasked preds | all TEST eligible | **dominant** (with over-seg) |
| `boundary.section_count_error` | CAL | mean abs err 3.67 | all over-count | all CAL eligible | **dominant** companion |
| `boundary.section_count_error` | TEST | mean abs err 5.33 | all over-count | all TEST eligible | **dominant** companion |
| `boundary.exact` | CAL | 11/12 matched | exact_hit_rate ≈ 0.917 | matched pairs | measured companion |
| `boundary.exact` | TEST | 9/9 matched | exact_hit_rate 1.0 | matched pairs | measured companion |
| `boundary.early` | CAL | 1 | signed err −1 bar | `aq7-synth-repeated-structure-cal-001` | `DOMINANT_ON_THIN_CORPUS` |
| `boundary.early` | TEST | 0 | — | — | none |
| `boundary.late` | CAL | 0 | — | — | none |
| `boundary.late` | TEST | 0 | — | — | none |
| `boundary.missed` | CAL | FN=1 | 1/13 refs | `aq7-synth-over-segmentation-challenge-cal-001` (bar 12) | `DOMINANT_ON_THIN_CORPUS` |
| `boundary.missed` | TEST | FN=0 | — | — | none |
| `boundary.under_segmentation` | CAL/TEST | 0 | rate 0.0 | — | none on this pack |
| `boundary.near_tolerance` | CAL | 1 early pair inside ±1 | not a separate FP | `aq7-synth-repeated-structure-cal-001` | thin |
| `boundary.ambiguity_ignore_mask` | CAL | 1 fixture | masked locus; 0 eligible refs | `aq7-synth-annotation-disagreement-cal-001` | eligibility layer (not FP/FN) |
| `boundary.beatgrid_hold` | TEST | 1 | excluded from denom | `aq7-synth-beatgrid-hold-test-001` | HOLD (not correctness) |
| `boundary.analyzer_failure` | CAL/TEST | 0 | — | — | none |

Offline signed-error recount used predicted/reference bars with the same ±1-bar one-to-one policy as #1023 (analysis-only; harness unchanged). Almost all matched pairs are exact; early/late is not the dominant failure mode.

## 3. Role Confusion Buckets

Plane: `aq7.role` only. Scored automatic roles on frozen reference sections. `unknown` visible; concrete macro-F1 excludes unknown per #1023. HOLD fixture excluded from denominators.

### Aggregate (rounded; matches #1026)

| Partition | macro-F1 | coverage | bar-weighted acc | unknown rate | abstention | concrete support | BeatGrid HOLD |
|---|---:|---:|---:|---:|---:|---:|---:|
| CALIBRATION | 0.457 | 0.588 | 0.393 | 0.444 | 0 | 17 | 0 |
| TEST/HOLDOUT | 0.297 | 0.750 | 0.341 | 0.250 | 1 | 12 | 1 |

### Confusion pairs (scored items only)

#### CALIBRATION

| bucket_id | ref → pred | support | fixture context (ids) | ranking |
|---|---|---:|---|---|
| `role.outro_outro_correct` | outro → outro | 5 | late-track sections across CAL | measured correct (not failure) |
| `role.intro_unknown` | intro → unknown | 4 | early sections: simple-clean, repeated, near-boundary, role-ambiguity | **dominant** failure |
| `role.build_groove` | build → groove | 2 | near-boundary; over-seg challenge | **dominant** (support=2) |
| `role.groove_unknown` | groove → unknown | 2 | repeated-structure; simple-clean | **dominant** (support=2) |
| `role.build_unknown` | build → unknown | 1 | repeated-structure | singleton |
| `role.intro_groove` | intro → groove | 1 | over-seg challenge | singleton |
| `role.drop_drop_correct` | drop → drop | 1 | over-seg challenge | singleton correct |
| `role.groove_groove_correct` | groove → groove | 1 | repeated-structure | singleton correct |
| `role.unknown_unknown` | unknown → unknown | 1 | role-ambiguity | reference-unknown (not concrete error) |
| `role.abstention_uncovered` | — | abstention 0; coverage 0.588 | unknown predictions reduce concrete coverage | measured |
| `role.held_unavailable` | — | 0 | — | none on CAL |

#### TEST/HOLDOUT (evidence only; not tuning)

| bucket_id | ref → pred | support | fixture context (ids) | ranking |
|---|---|---:|---|---|
| `role.drop_groove` | drop → groove | 2 | drop-at-boundary; under-seg challenge | **dominant** on TEST (not CAL hypothesis fuel) |
| `role.outro_outro_correct` | outro → outro | 2 | drop-at-boundary; under-seg | measured correct |
| `role.build_groove` | build → groove | 1 | under-seg | singleton |
| `role.build_intro` | build → intro | 1 | drop-at-boundary | singleton |
| `role.intro_groove` | intro → groove | 1 | drop-not-boundary-owner | singleton |
| `role.intro_unknown` | intro → unknown | 1 | under-seg | singleton |
| `role.groove_unknown` | groove → unknown | 1 | under-seg | singleton |
| `role.outro_unknown` | outro → unknown | 1 | drop-not-boundary-owner | singleton |
| `role.held_unavailable` | — | 1 fixture | `aq7-synth-beatgrid-hold-test-001` | BeatGrid HOLD |

`breakdown` has corpus support 0 on both splits (N/A F1) — no invented breakdown confusion.

## 4. Drop Event Failure Buckets

Plane: `aq7.drop_event` only. Matching ±1 bar on frozen reference boundaries. HOLD excluded from correctness denominators.

### Aggregate (rounded; matches #1026)

| Partition | P@1bar | R@1bar | F1 | support | false | missed | med\|err\| | p95\|err\| | coverage | BeatGrid HOLD |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|
| CALIBRATION | 0.000 | 0.000 | 0.000 | 1 | 6 | 1 | N/A | N/A | 1.000 | 0 |
| TEST/HOLDOUT | 0.000 | 0.000 | 0.000 | 2 | 3 | 2 | N/A | N/A | 1.000 | 1 |

No drop events matched within ±1 bar → `drop.timing_offset = not_applicable` (not 0).

### Bucket inventory

| bucket_id | split | support | note | fixture_ids | ranking |
|---|---|---:|---|---|---|
| `drop.false` | CAL | 6 | preds on empty-ref or unmatched bars | simple-clean, repeated (2), near-boundary, role-ambiguity, over-seg | **dominant** |
| `drop.false` | TEST | 3 | unmatched preds | drop-at-boundary, drop-not-boundary-owner, under-seg | **dominant** |
| `drop.missed` | CAL | 1 | ref bar 28 unmatched | `aq7-synth-over-segmentation-challenge-cal-001` | `DOMINANT_ON_THIN_CORPUS` |
| `drop.missed` | TEST | 2 | refs unmatched | drop-at-boundary; drop-not-boundary-owner | **dominant** on TEST |
| `drop.timing_offset` | CAL/TEST | n/a | no matched pairs | — | `not_applicable` |
| `drop.correct_event` | CAL/TEST | 0 | — | — | none |
| `drop.correct_negative` | CAL | 1 | empty ref + empty pred | `aq7-synth-annotation-disagreement-cal-001` | thin correct |
| `drop.correct_negative` | TEST | 0 among usable non-HOLD with empty ref | under-seg has empty ref but FP pred | — | — |
| `drop.unavailable_hold` | — | 0 | — | — | none beyond BeatGrid |
| `drop.beatgrid_hold` | TEST | 1 | excluded | `aq7-synth-beatgrid-hold-test-001` | HOLD |

## 5. Signal Availability / Correlation

Signal families are **explanatory only** — not ground truth, not promotion evidence, not pseudo-labels.

### Availability (usable non-HOLD fixtures)

| Family | Status on usable fixtures | Notes |
|---|---|---|
| energy / loudness (`bar_energy_rms`, `bar_loudness_delta`) | measured | present on all eligible CAL+TEST |
| low-end share | measured | present |
| onset density | measured | present |
| rhythm stability | measured | present |
| timbre change (`timbre_delta`) | measured | present |
| spectral change (`spectral_delta`) | measured | present |
| recurrence / self-similarity / novelty | measured | present |
| neighbor / multi-bar trends | measured | present |
| relative track position | measured | present |
| CLAP | `not_applicable` | not consumed |
| stems | `not_applicable` | not consumed |

BeatGrid HOLD fixture (`aq7-synth-beatgrid-hold-test-001`): only `clap`/`stems` recorded as `not_applicable`; core families are **not** claimed measured under provenance HOLD (attribution stops at layer 2).

### Correlation notes (non-causal)

| Observation | Plane | Support | Guard |
|---|---|---:|---|
| Extra boundaries co-occur with dense novelty/onset-capable surfaces on synthetic accents | `aq7.boundary` | all eligible over-seg | correlation with over-seg bucket; **not** proof that a novelty threshold is wrong |
| `intro → unknown` often on early sections where relative position is measured | `aq7.role` | CAL n=4 | classifier under-claim; do not invent GT from signals |
| `build → groove` where build cues (loudness/onset/timbre deltas) may be weak on synth material | `aq7.role` | CAL n=2 | thin; exploratory only |
| False `drop_onset` on empty-ref tracks despite measured loudness/timbre/novelty families | `aq7.drop_event` | CAL FP=6 | emission without reference support; no causal weight claim |
| Missed `drop_onset` when a ref exists | `aq7.drop_event` | CAL n=1 / TEST n=2 | timing/eligibility mismatch visible; no invented offset metric |

Optional signals (CLAP/stems) are absent — report as absent, never as correctness.

## 6. BeatGrid / Provenance Attribution

| Fixture | Split | Layer | Effect |
|---|---|---|---|
| `aq7-synth-beatgrid-hold-test-001` | TEST | 2 BeatGrid/provenance | HOLD for boundary, role, and drop; **out of all correctness denominators** |
| `aq7-synth-annotation-disagreement-cal-001` | CAL | 1 Eligibility/annotation | ignore-mask on disputed boundary; 0 eligible boundary refs; role/drop not treated as BeatGrid failure |
| All other fixtures | CAL/TEST | 4–7 after eligible | authored_synthetic eval BeatGrid; failures attributed to boundary/role/drop logic — not invented as BeatGrid errors |

No analyzer_failure cases observed on this regeneration.

## 7. CALIBRATION vs TEST comparison

| Plane | CALIBRATION (exploration) | TEST/HOLDOUT (frozen evidence) | Firewall |
|---|---|---|---|
| Boundary | over-seg + extras dominate; 1 miss; 1 early | same over-seg pattern; 0 miss; 1 BeatGrid HOLD | do not tune on TEST |
| Role | intro→unknown, build→groove, groove→unknown lead | drop→groove leads; BeatGrid HOLD | TEST confusions are evidence only |
| Drop | FP-dominant; 1 miss; timing N/A | FP + 2 misses; timing N/A; HOLD | no TEST feedback into candidates |
| Signals | core families measured | same on usable; HOLD sparse | no optional-signal labeling |

CAL and TEST tables are never mixed into one quality score.

## 8. Dominant Failure Summary

| Plane × split | Dominant bucket(s) | Support basis |
|---|---|---|
| boundary × CAL | `boundary.over_segmentation` + `boundary.extra_or_duplicate` | 6/6 fixtures; FP=23 |
| boundary × TEST | `boundary.over_segmentation` + `boundary.extra_or_duplicate` | 3/3 eligible; FP=16; HOLD separate |
| role × CAL | `role.intro_unknown` (then `role.build_groove`, `role.groove_unknown`) | 4; 2; 2 |
| role × TEST | `role.drop_groove` | 2 (evidence only) |
| drop × CAL | `drop.false` | 6 |
| drop × TEST | `drop.false` + `drop.missed` | 3 + 2 |

Early/late boundary timing is **not** dominant. Under-segmentation is **not** observed on eligible fixtures (including the family named `under-segmentation-challenge`, which still over-segments under current StructureV1).

## 9. Bounded Candidate Hypotheses

Hypotheses are **CALIBRATION-derived**, bounded, and explicitly non-causal. They do **not** authorize thresholds, production switches, or #1028 implementation in this slice. TEST may only later **evaluate** candidates — never generate them.

| hyp_id | Target plane | CAL evidence | Support | Singletons? | Allowed #1028 use |
|---|---|---|---:|---|---|
| `H-AQ7-1027-01` | `aq7.boundary` | Reduce extra/over-segmentation density without collapsing recall | over-seg 6/6; FP=23 | no (fixture-level) | thin adapter exploration only; no invented gate |
| `H-AQ7-1027-02` | `aq7.role` | Reduce early-section `intro → unknown` under-claim | 4 | no | CAL exploration; preserve unknown honesty |
| `H-AQ7-1027-03` | `aq7.role` | Reduce `build → groove` concrete confusion | 2 | borderline | CAL only; abort if only singleton remains after any filter |
| `H-AQ7-1027-04` | `aq7.drop_event` | Reduce false `drop_onset` on empty-ref surfaces | FP=6 | no | CAL only; keep miss visibility separate |

Hypothesis count: **4**.

Not promoted to hypotheses (retained as diagnostics only):

- CAL `boundary.missed` / `boundary.early` (n=1)
- TEST-leading `role.drop_groove` (TEST must not drive candidates)
- Any breakdown-family claim (support 0)
- Any CLAP/stem-driven claim (`not_applicable`)
- Any global AQ7 composite score

## 10. Explicit Non-Conclusions

- No causality from signal family → failure bucket.
- No GT leakage: GT roles/drops/boundaries never enter prediction; diagnostics only read baseline outputs.
- No invented thresholds, tolerances, or promotion gates.
- No global AQ7 quality score blending boundary+role+drop.
- HOLD / ignore-mask / BeatGrid are not “failures against the analyzer.”
- `drop.timing_offset` is not 0 when unmatched — it is `not_applicable`.
- Thin synthetic support does not authorize consumer-safety or production claims.
- #1028 is not started; hypotheses are tokens only.
- Optional signals were not present and are not pseudo-labeled.

## 11. Exit Token

Exactly one:

```text
AQ7_DIAGNOSTICS_PARTIAL_HOLD
```

Rationale: buckets are quantified with support and plane separation, identities match #1025/#1026, but thin corpus + material BeatGrid HOLD prevent an honest `AQ7_ERROR_BUCKETS_EXPLAINED` upgrade. Evidence is not `INSUFFICIENT` — regeneration matched frozen baselines.

## 12. Machine-facing bucket appendix

Stable IDs for later #1040 consumption. Values are portable summaries; exact floats remain in external JSON.

```json
{
  "document_type": "sample-brain.aq7.structure-role-drop-diagnostics.v1",
  "schema_version": "1.0.0",
  "issue": 1027,
  "exit_status": "AQ7_DIAGNOSTICS_PARTIAL_HOLD",
  "corpus_id": "sample-brain.aq7.structure-role-drop.synthetic.v1",
  "corpus_version": "1.0.0",
  "generator_seed": 1024001,
  "boundary_candidate_id": "structure_v1.baseline.v1",
  "role_drop_candidate_id": "arrangement_classifier.baseline.v1",
  "boundary_exit": "AQ7_STRUCTURE_BOUNDARY_BASELINE_PARTIAL_HOLD",
  "role_drop_exit": "AQ7_ROLE_DROP_BASELINE_PARTIAL_HOLD",
  "planes": ["aq7.boundary", "aq7.role", "aq7.drop_event"],
  "hold": {
    "beatgrid_fixture_ids": ["aq7-synth-beatgrid-hold-test-001"],
    "beatgrid_split": "TEST",
    "correctness_denominator": "excluded"
  },
  "dominant_buckets": [
    {"plane": "aq7.boundary", "split": "CALIBRATION", "bucket_id": "boundary.over_segmentation", "support": 6},
    {"plane": "aq7.boundary", "split": "CALIBRATION", "bucket_id": "boundary.extra_or_duplicate", "support": 23},
    {"plane": "aq7.boundary", "split": "TEST", "bucket_id": "boundary.over_segmentation", "support": 3},
    {"plane": "aq7.boundary", "split": "TEST", "bucket_id": "boundary.extra_or_duplicate", "support": 16},
    {"plane": "aq7.role", "split": "CALIBRATION", "bucket_id": "role.intro_unknown", "support": 4},
    {"plane": "aq7.role", "split": "CALIBRATION", "bucket_id": "role.build_groove", "support": 2},
    {"plane": "aq7.role", "split": "CALIBRATION", "bucket_id": "role.groove_unknown", "support": 2},
    {"plane": "aq7.role", "split": "TEST", "bucket_id": "role.drop_groove", "support": 2, "tuning_fuel": false},
    {"plane": "aq7.drop_event", "split": "CALIBRATION", "bucket_id": "drop.false", "support": 6},
    {"plane": "aq7.drop_event", "split": "TEST", "bucket_id": "drop.false", "support": 3, "tuning_fuel": false},
    {"plane": "aq7.drop_event", "split": "TEST", "bucket_id": "drop.missed", "support": 2, "tuning_fuel": false}
  ],
  "drop_timing_offset": "not_applicable",
  "hypotheses": [
    {"hyp_id": "H-AQ7-1027-01", "plane": "aq7.boundary", "split_fuel": "CALIBRATION"},
    {"hyp_id": "H-AQ7-1027-02", "plane": "aq7.role", "split_fuel": "CALIBRATION"},
    {"hyp_id": "H-AQ7-1027-03", "plane": "aq7.role", "split_fuel": "CALIBRATION"},
    {"hyp_id": "H-AQ7-1027-04", "plane": "aq7.drop_event", "split_fuel": "CALIBRATION"}
  ],
  "hypothesis_count": 4,
  "signal_availability_summary": {
    "core_structure_families": "measured_on_usable_fixtures",
    "clap": "not_applicable",
    "stems": "not_applicable"
  },
  "non_conclusions": [
    "no_causality",
    "no_gt_leakage",
    "no_invented_thresholds",
    "no_global_aq7_score",
    "hold_excluded_from_correctness",
    "test_not_tuning_fuel"
  ]
}
```

## Non-goals (this slice)

- no `src/structure_v1.py` / `arrangement_classifier.py` / `section_signals.py` changes
- no #1025/#1026 harness edits
- no threshold/default/production switch
- no #1028 candidate implementation
- no committed WAV / raw JSON / private or absolute paths
- no optional-signal pseudo-labeling
