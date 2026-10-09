# AQ7 Structure / Role / Drop Candidate Comparison (CALIBRATION)

**Status:** ACTIVE_SUPPORTING — reproducible candidate comparison for [#1028](https://github.com/jannekbuengener/sample-brain/issues/1028)
**Class:** ACTIVE_SUPPORTING
**Parents:** [#949](https://github.com/jannekbuengener/sample-brain/issues/949) (AQ7), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)
**Depends on (CLOSED):** [#1023](https://github.com/jannekbuengener/sample-brain/issues/1023) KPI, [#1024](https://github.com/jannekbuengener/sample-brain/issues/1024) corpus, [#1025](https://github.com/jannekbuengener/sample-brain/issues/1025) boundary baseline, [#1026](https://github.com/jannekbuengener/sample-brain/issues/1026) role/drop baseline, [#1027](https://github.com/jannekbuengener/sample-brain/issues/1027) diagnostics
**Normative KPI:** [`AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md`](AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md)
**Corpus:** [`AQ7_STRUCTURE_ROLE_DROP_CORPUS.md`](AQ7_STRUCTURE_ROLE_DROP_CORPUS.md) / `sample-brain.aq7.structure-role-drop.synthetic.v1`
**Boundary baseline:** [`AQ7_STRUCTURE_BOUNDARY_BASELINE.md`](AQ7_STRUCTURE_BOUNDARY_BASELINE.md) / `structure_v1.baseline.v1`
**Role/drop baseline:** [`AQ7_STRUCTURE_ROLE_DROP_BASELINE.md`](AQ7_STRUCTURE_ROLE_DROP_BASELINE.md) / `arrangement_classifier.baseline.v1`
**Diagnostics (candidate fuel):** [`AQ7_STRUCTURE_ROLE_DROP_DIAGNOSTICS.md`](AQ7_STRUCTURE_ROLE_DROP_DIAGNOSTICS.md)
**Compare runner:** `python -m src.aq7_structure_role_drop_candidate_compare`
**Related bootstrap:** [#1040](https://github.com/jannekbuengener/sample-brain/issues/1040) quality-loop consumer of machine-readable freeze (orchestrator out of scope here)
**Downstream:** [#1030](https://github.com/jannekbuengener/sample-brain/issues/1030) locked TEST/HOLDOUT evaluation (not started here)

## Architecture outcome

```text
AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE
```

Frozen identity before #1030: `aq7.baseline.v1` (StructureV1 defaults + ArrangementClassifier defaults).

This document freezes a **small, evidence-derived StructureV1 / ArrangementClassifier candidate set** and a **reproducible CALIBRATION-only comparison + freeze harness**. Planes stay separate. It does **not** promote production defaults, invent a global AQ7 composite score, tune on TEST/HOLDOUT, or start #1030.

Settings toggle: `N/A` — evaluation-only candidates; no product default or user-behavior change.

### Measured CALIBRATION summary (portable)

External JSON `exit_token=AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE`. Exact floats live outside the repo.

| Candidate | Boundary P@1bar | Boundary R@1bar | Role macro-F1 | Drop F1 | Drop FP | Justified? |
|---|---:|---:|---:|---:|---:|---|
| `aq7.baseline.v1` | 0.343 | 0.923 | 0.457 | 0.0 | 6 | retention anchor |
| `boundary.min_distance.4` | 0.417 | 0.769 | 0.457 | 0.0 | 6 | no — recall regression >0.05 |
| `role.unknown_margin.0.03` | 0.343 | 0.923 | 0.492 | 0.0 | 7 | no — unknown-ref honesty 1.0→0.0 |
| `drop.onset_thresh.0.80` | 0.343 | 0.923 | 0.457 | 0.0 | 4 | no — FP-only; F1/TP unchanged |

TEST/HOLDOUT was reported in the artifact and **not** used for selection (`test_used_for_selection=false`).

## Scope

| In | Out |
|---|---|
| ≤4 frozen candidate identities derived from #1027 CAL shortlist | All five shortlist hypotheses as separate bake-off IDs |
| Thin StructureV1 / ArrangementClassifier config adapters | New algorithms / production default switch |
| Separate `aq7.boundary` / `aq7.role` / `aq7.drop_event` metrics + hard-case deltas | Global AQ7 composite quality number |
| Role/drop on frozen GT reference geometry (`frozen_gt_reference_sections`) | Role/drop inventing or moving boundaries |
| CALIBRATION selection + freeze | TEST/HOLDOUT tuning or selection feedback |
| Machine-readable external JSON for #1040 | Committed audio / private paths / orchestrator |

## Candidate identity (frozen ≤4)

Shortlist fuel from #1027 (CAL support ≥ 2): `H-AQ7-1027-01` … `H-AQ7-1027-05`.
This bake-off selects **baseline + 3 adapters** (4 total). `H-AQ7-1027-03` / `H-AQ7-1027-04` remain shortlist-eligible but are **not** separate bake-off identities here (thin overlap / weight surgery deferred). `Sxx` singletons stay out.

| `candidate_id` | Hypothesis | Primary plane | Config delta vs baseline |
|---|---|---|---|
| `aq7.baseline.v1` | — | multi | StructureV1 + ArrangementClassifier defaults (#1025/#1026) |
| `boundary.min_distance.4` | `H-AQ7-1027-01` | `aq7.boundary` | `min_boundary_distance_bars` 2→4 |
| `role.unknown_margin.0.03` | `H-AQ7-1027-02` | `aq7.role` | `unknown_min_margin` 0.05→0.03 |
| `drop.onset_thresh.0.80` | `H-AQ7-1027-05` | `aq7.drop_event` | `drop_onset_threshold` 0.65→0.80 |

### Scoring / plane rules (normative)

1. Boundary metrics reuse `src.aq7_structure_boundary_baseline` aggregators on StructureV1 predictions for the candidate's `structure_config`.
2. Role/drop metrics reuse `src.aq7_structure_role_drop_baseline` aggregators on **frozen GT reference sections/boundaries** with the candidate's `arrangement_config` (bar_features from baseline StructureV1). Role/drop never create or move boundaries.
3. Planes remain separately visible in the artifact; no composite score.
4. `drop_onset` stays an event, not a section role.
5. TEST/HOLDOUT metrics may be reported once as frozen evidence; they must never drive candidate selection, tuning, or freeze.

### CALIBRATION justification (machine decision)

| Primary plane | Justified when (CAL only) | Explicit non-accept |
|---|---|---|
| `aq7.boundary` | P@1bar / extra_rate / over-seg / FP improves **and** recall does not drop by >0.05 | Recall collapse |
| `aq7.role` | macro-F1 or intro recall/F1 improves **and** unknown-reference honesty does not collapse | Unknown honesty collapse |
| `aq7.drop_event` | F1 improves **or** TP (`matched_count`) increases | FP-only reduction while F1 stays 0.0 (#1027 falsifier) |

**Completeness gate (fail-closed):** before any freeze, every candidate's CALIBRATION block must have all six corpus fixtures, boundary `n_usable=6`, measured role `macro_f1` with `support≥1` (not fully held), and drop `coverage>0`. Otherwise → `AQ7_CANDIDATE_COMPARE_INCOMPLETE` (do not emit KEEP_BASELINE from missing role/drop measurements).

If complete and no non-baseline candidate is justified → `AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE` with frozen `aq7.baseline.v1`.
If complete and one or more are justified → pick best by primary-plane score then lexicographic id → `AQ7_CANDIDATE_COMPARE_CALIBRATION_FROZEN`.

## Partition policy

| Corpus `split` | AQ7 role | Allowed use in this slice |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | candidate selection + freeze |
| `TEST` | TEST / HOLDOUT | frozen evidence report once; **no selection**; **no tuning** |

## How to run

Corpus audio/GT and JSON evidence stay **outside** the repository:

```powershell
python -m src.aq7_structure_role_drop_candidate_compare `
  --work-dir <external-directory>/aq7-structure-role-drop-corpus `
  --output <external-directory>/aq7-structure-role-drop-compare.json
```

The runner rejects outputs inside the git tree. Exact floats live in the external JSON; this document records identities, gates, and portable decision vocabulary.

## Artifact schema (compare)

| Field | Notes |
|---|---|
| `document_type` | `sample-brain.aq7.structure-role-drop-candidate-compare.v1` |
| `schema_version` | `1.0.0` |
| `corpus_id` / `corpus_version` | frozen #1024 identity |
| `baseline_candidate_id` | `aq7.baseline.v1` |
| `selection_partition` | always `CALIBRATION` |
| `test_used_for_selection` | always `false` |
| `no_tuning_on_test` | always `true` |
| `feature_toggle` | `N/A` |
| `production_defaults_changed` | always `false` |
| `candidates[]` | identity + per-split separate plane metrics + CAL hard-case deltas |
| `decision` | freeze block: exit token, frozen candidate/config, justification rows |
| `exit_token` / `exit_status` | one of the three AQ7 compare tokens |
| `fixtures[]` | join-keyed rows only (no host paths) |

## Non-goals

- no production switch / no promotion thresholds
- no TEST/HOLDOUT threshold discovery or selection
- no UI / Arrangement product feature / QML
- no optional stem/CLAP pseudo-ground-truth
- no role-created boundaries
- no new GT labels from observed results
- no private samples/DBs/caches/absolute host paths in committed artifacts
- no #1040 orchestrator / no #1030 holdout execution in this slice

## Exit vocabulary

Exactly one:

- `AQ7_CANDIDATE_COMPARE_CALIBRATION_FROZEN`
- `AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE`
- `AQ7_CANDIDATE_COMPARE_INCOMPLETE`

This slice exits `AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE` with frozen `aq7.baseline.v1`. The harness `decision` block is authoritative for the exit token and frozen config identity.
