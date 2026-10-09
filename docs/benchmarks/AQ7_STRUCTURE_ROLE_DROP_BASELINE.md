# AQ7 Arrangement Role + Drop Event Baseline (synthetic corpus)

**Status:** ACTIVE_SUPPORTING - measured current ArrangementClassifier role/drop baseline for [#1026](https://github.com/jannekbuengener/sample-brain/issues/1026)
**Class:** ACTIVE_SUPPORTING
**Parents:** [#949](https://github.com/jannekbuengener/sample-brain/issues/949) (AQ7), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)
**Depends on:** [#1023](https://github.com/jannekbuengener/sample-brain/issues/1023) KPI contract, [#1024](https://github.com/jannekbuengener/sample-brain/issues/1024) frozen corpus, [#1025](https://github.com/jannekbuengener/sample-brain/issues/1025) frozen boundary context
**Normative KPI:** [`AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md`](AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md)
**Corpus:** [`AQ7_STRUCTURE_ROLE_DROP_CORPUS.md`](AQ7_STRUCTURE_ROLE_DROP_CORPUS.md) / `sample-brain.aq7.structure-role-drop.synthetic.v1`
**Boundary context:** [`AQ7_STRUCTURE_BOUNDARY_BASELINE.md`](AQ7_STRUCTURE_BOUNDARY_BASELINE.md) / `structure_v1.baseline.v1`
**Runner:** `python -m src.aq7_structure_role_drop_baseline`

## Architecture outcome

```text
AQ7_ROLE_DROP_BASELINE_PARTIAL_HOLD
```

This document records the current `ArrangementClassifier` role/drop baseline against frozen #1024 reference sections/boundaries, using #1025 as the frozen boundary context. It measures only `aq7.role` and `aq7.drop_event`. It does **not** tune ArrangementClassifier, change StructureV1, change SectionSignals, alter BeatGrid, set promotion gates, or switch production behavior.

The measured outcome for this slice is:

```text
AQ7_ROLE_DROP_BASELINE_PARTIAL_HOLD
```

`PARTIAL_HOLD` is honest: the frozen `beatgrid_hold` TEST fixture has missing BeatGrid provenance, so role and drop-event correctness for that fixture remains HOLD/unknown rather than receiving invented bars, fake negatives, or fake zeroes.

## Scope

| In | Out |
|---|---|
| Current `src.arrangement_classifier.ArrangementClassifier` default behavior | ArrangementClassifier tuning, thresholds, or defaults |
| Frozen #1024 role/drop GT on frozen reference sections/boundaries | StructureV1, BeatGrid, SectionSignals, or corpus algorithm changes |
| Role plane `aq7.role` on reference sections only | Role labels creating, deleting, or moving boundaries |
| Drop-event plane `aq7.drop_event` on reference boundaries only | `drop_onset` as a section role |
| Boundary context by reference to #1025 | Candidate comparison (#1028) or promotion |
| Portable external JSON artifact | Committed audio, raw generated corpus, private paths, reports |

Settings toggle: `N/A` - evaluation harness only. No production switch.

## Identities

| Field | Value |
|---|---|
| `document_type` | `sample-brain.aq7.structure-role-drop-baseline.v1` |
| `schema_version` | `1.0.0` |
| `candidate_id` / baseline id | `arrangement_classifier.baseline.v1` |
| `corpus_id` | `sample-brain.aq7.structure-role-drop.synthetic.v1` |
| `corpus_version` | `1.0.0` (frozen #1024) |
| Boundary context | `structure_v1.baseline.v1` (#1025) |
| Role plane token | `aq7.role` |
| Drop-event plane token | `aq7.drop_event` |
| Arrangement surface | `src.arrangement_classifier.ArrangementClassifier.classify_track(..., manual_overrides=None)` |
| Section signal surface | `src.section_signals.SectionSignalsAssembler` |
| Structure input surface | `src.structure_v1.StructureV1Result.bar_features` |
| Protected analyzer files | `src/arrangement_classifier.py`, `src/section_signals.py`, `src/structure_v1.py`, BeatGrid algorithm |

## Input model

The Task 3 harness must mirror the frozen adapter path:

```text
#1024 corpus
  -> authored eval BeatGrid
  -> StructureV1 bar_features
  -> patched StructureV1Result with GT geometry
  -> SectionSignalsAssembler
  -> ArrangementClassifier.classify_track(..., manual_overrides=None)
  -> aq7.role + aq7.drop_event scoring
  -> portable external artifact
```

Ground-truth geometry is evaluation-only. GT roles and GT drops are evaluator-only and must never enter the prediction path. `manual_overrides` is fixed to `None`; if the public classifier surface carries automatic and effective/manual values, the baseline scores only `automatic_result.role`.

## Plane firewalls

### Role plane (`aq7.role`)

- Role evaluation consumes frozen reference sections from #1024.
- Scoring uses automatic classifier output only.
- Primary concrete-role macro-F1 uses the #1023 concrete role set: `intro`, `groove`, `build`, `drop`, `breakdown`, `outro`.
- `unknown` remains visible in confusion, coverage, abstention, and reference-unknown recall evidence, but is excluded from the concrete macro-F1 denominator per #1023.
- Failed/unavailable role passes reduce coverage; they must not fabricate semantic `unknown` confusion rows.

### Drop plane (`aq7.drop_event`)

- `drop_onset` is an event anchored to a frozen reference neutral boundary.
- Matching uses the #1023 primary tolerance: `BOUNDARY_MATCH_TOLERANCE_BARS = 1`.
- Matching is one-to-one, order-preserving, maximizes pairs within tolerance, then minimizes absolute bar error.
- Drop prediction never creates or moves a boundary.
- Under a usable event surface, non-emission is a negative prediction; under an unusable surface it is HOLD/unknown and does not enter correctness denominators.

### Boundary firewall

This baseline consumes the #1025 boundary context and may patch StructureV1 geometry for evaluation so ArrangementClassifier sees frozen reference sections/boundaries. It must fail closed if:

- role/drop logic mutates boundary geometry;
- a predicted drop references an unknown boundary;
- GT roles or GT drop events appear in classifier inputs;
- protected analyzer changes seem necessary to make the harness work.

If any of those occurs, the delivery must stop with a contract/analyzer blocker rather than changing protected analyzer files.

## Signal provenance

Signal provenance is evidence, not ground truth. The artifact must state which signal families were available and which were absent. Do not claim CLAP, stems, or other optional signals unless the prediction surface actually consumed them. Missing optional signals are reported as absent/HOLD evidence, not as correctness values.

## BeatGrid HOLD honesty

Fixtures with `beatgrid_provenance.status == authored_synthetic` may use an evaluation-only authored synthetic BeatGrid to create the classifier inputs needed by the harness. Fixtures with `missing` or `insufficient` BeatGrid provenance are HOLD for both role and drop planes:

- no invented grid;
- no fake zeroes;
- no fabricated timing correctness;
- no false precision/recall denominators for the unusable surface.

## Split firewall

| Corpus `split` | AQ7 KPI role |
|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION |
| `TEST` | TEST / HOLDOUT |

Do not tune on TEST/HOLDOUT. This slice is baseline measurement only. Later candidate search belongs to #1028 and must not use TEST feedback.

## CLI mirror of #1025

Corpus audio/GT and JSON evidence stay outside the repository:

```powershell
python -m src.aq7_structure_role_drop_baseline `
  --work-dir <external-directory>/aq7-structure-role-drop-corpus `
  --output <external-directory>/aq7-structure-role-drop-baseline.json
```

The CLI must reject work/output paths inside the checkout and write a portable artifact only. Exact floats live in the external JSON; rounded display values are documented after Task 4.

## Measured baseline summary (rounded display)

Two independent external workdirs produced identical semantic projections (`arrangement_classifier.baseline.v1` on corpus `1.0.0`). Exact values live in the external JSON artifacts; rounded values are shown here.

### Role plane (`aq7.role`)

| Partition | macro-F1 | coverage | bar-weighted accuracy | unknown rate | abstention count | concrete support | BeatGrid HOLD |
|---|---:|---:|---:|---:|---:|---:|---:|
| CALIBRATION | 0.366 | 0.611 | 0.361 | 0.421 | 0 | 18 | 0 |
| TEST/HOLDOUT | 0.297 | 0.750 | 0.341 | 0.250 | 1 | 12 | 1 |

Per-role F1 summary:

| Partition | intro | groove | build | drop | breakdown | outro |
|---|---:|---:|---:|---:|---:|---:|
| CALIBRATION | 0.000 | 0.286 | 0.000 | 1.000 | 0.000 | 0.909 |
| TEST/HOLDOUT | 0.400 | 0.286 | 0.000 | 0.000 | N/A | 0.800 |

Role confusion remains visible in the external artifact. High `unknown` predictions are measured classifier output, not converted from ambiguous annotations.

### Drop-event plane (`aq7.drop_event`)

| Partition | P@1bar | R@1bar | F1 | support | false | missed | med\|err\| bars | p95\|err\| bars | coverage | BeatGrid HOLD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CALIBRATION | 0.000 | 0.000 | 0.000 | 1 | 7 | 1 | N/A | N/A | 1.000 | 0 |
| TEST/HOLDOUT | 0.000 | 0.000 | 0.000 | 2 | 3 | 2 | N/A | N/A | 0.750 | 1 |

No drop events matched within the frozen +/-1-bar policy. Timing-error aggregates are therefore not applicable, not zero.

## Runtime and determinism

Runtime methodology is consumed by reference from [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / [`ANALYZER_RUNTIME_METHODOLOGY_V1.md`](ANALYZER_RUNTIME_METHODOLOGY_V1.md).

- Track-length buckets are HOLD for this tiny synthetic pack unless a later methodology-compliant run proves otherwise.
- A single harness run may record diagnostic single-pass wall time only.
- Diagnostic single-pass runtime is not #958 cold/steady median/p95 evidence.
- Task 4 diagnostic-only Run B single-pass median was 3.776s and p95 was 4.900s over timed fixtures; this remains non-#958 diagnostic evidence.

Semantic determinism is consumed by reference from [#959](https://github.com/jannekbuengener/sample-brain/issues/959) / [`../ANALYZER_SEMANTIC_DETERMINISM_V1.md`](../ANALYZER_SEMANTIC_DETERMINISM_V1.md).

- A single run must report determinism as `not_measured`.
- `semantic_equal=True` may be claimed only after comparing against a second independent semantic projection.
- Task 4 Run A reported `semantic_equal=null`; independent Run B compared against Run A and reported `semantic_equal=true`.

## Portable artifact contract

The artifact must be portable and path-safe:

- no absolute/private paths;
- no audio bytes or committed generated corpus;
- no raw reports;
- no host/user/machine identity;
- pass `assert_portable_value`;
- include corpus, candidate, boundary-context, split, metric, HOLD, provenance, runtime, and determinism blocks.

## Exit vocabulary

Exactly one final issue exit:

- `AQ7_ROLE_DROP_BASELINE_MEASURED`
- `AQ7_ROLE_DROP_BASELINE_PARTIAL_HOLD`
- `AQ7_ROLE_DROP_BASELINE_INCOMPLETE`

Task-gate local exits:

- Task 1 docs gate: `DOCS_GATE_PASS`
- Task 2 test freeze: `TEST_GATE_PASS_TEST_FREEZE`
- Task 3 harness validation: `AQ7_ROLE_DROP_HARNESS_VALIDATED`
- Task 4 evidence validation: `AQ7_MEASURED_EVIDENCE_VALIDATED`

## Production behavior

No protected analyzer files may change in this delivery:

- `src/arrangement_classifier.py`
- `src/section_signals.py`
- `src/structure_v1.py`
- BeatGrid algorithm
- #1024 GT semantics
- #1025 boundary metric semantics

No algorithm/default change occurs. This baseline observes the current path and records evidence only.
