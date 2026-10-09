# AQ7 Structure / Role / Drop Locked TEST/HOLDOUT Evaluation

**Status:** ACTIVE_SUPPORTING — locked holdout evaluation + regression gates for [#1030](https://github.com/jannekbuengener/sample-brain/issues/1030)
**Class:** ACTIVE_SUPPORTING
**Parents:** [#949](https://github.com/jannekbuengener/sample-brain/issues/949) (AQ7), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)
**Depends on (CLOSED):** [#1023](https://github.com/jannekbuengener/sample-brain/issues/1023) KPI, [#1024](https://github.com/jannekbuengener/sample-brain/issues/1024) corpus, [#1025](https://github.com/jannekbuengener/sample-brain/issues/1025) boundary baseline, [#1026](https://github.com/jannekbuengener/sample-brain/issues/1026) role/drop baseline, [#1027](https://github.com/jannekbuengener/sample-brain/issues/1027) diagnostics, [#1028](https://github.com/jannekbuengener/sample-brain/issues/1028) CALIBRATION freeze
**Normative KPI:** [`AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md`](AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md)
**Corpus:** [`AQ7_STRUCTURE_ROLE_DROP_CORPUS.md`](AQ7_STRUCTURE_ROLE_DROP_CORPUS.md) / `sample-brain.aq7.structure-role-drop.synthetic.v1`
**Freeze provenance:** [`AQ7_STRUCTURE_ROLE_DROP_CANDIDATE_COMPARE.md`](AQ7_STRUCTURE_ROLE_DROP_CANDIDATE_COMPARE.md) / `AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE`
**Runner:** `python -m src.aq7_structure_role_drop_locked_holdout`
**Related bootstrap:** [#1040](https://github.com/jannekbuengener/sample-brain/issues/1040) quality-loop consumer of machine-readable holdout evidence (orchestrator out of scope here)
**Downstream:** [#1031](https://github.com/jannekbuengener/sample-brain/issues/1031) decision memo (not started here)

## Architecture outcome

```text
AQ7_HOLDOUT_PARTIAL_HOLD
```

Frozen identity consumed from #1028 (immutable in this slice):

| Field | Value |
|---|---|
| Freeze token | `AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE` |
| Frozen candidate / config | `aq7.baseline.v1` |
| Candidate vs baseline | **same identity** — no artificial challenger; rejected CALIBRATION adapters stay rejected |

This document freezes a **locked TEST/HOLDOUT evaluation harness** and **separate plane regression-gate evidence** for the #1028-retained baseline. It does **not** retune thresholds, promote rejected candidates, invent a global AQ7 composite score, switch production defaults, or start #1031.

Settings toggle: `N/A` — evaluation/gating only; no product behavior change.

`PARTIAL_HOLD` is the honest measured outcome when the frozen #1024 `beatgrid_hold` TEST fixture keeps BeatGrid-provenance correctness as HOLD/unknown on one or more planes while the remaining TEST fixtures are measured. Do not convert that HOLD into PASS by dropping the fixture, inventing bars, or loosening tolerances.

### Measured TEST/HOLDOUT summary (portable)

External JSON `exit_token=AQ7_HOLDOUT_PARTIAL_HOLD`. Exact floats live outside the repo. Candidate ≡ baseline (`aq7.baseline.v1`); challenger deltas are structurally zero.

| Plane | Gate | Coverage / usable | Primary locked metrics (portable) | HOLD reason |
|---|---|---|---|---|
| `aq7.boundary` | `HOLD` | usable 3/4 TEST | P@1bar ≈ 0.36; R@1bar = 1.0; F1@1bar ≈ 0.53 | `BEATGRID_PROVENANCE_LIMITATION` (1 fixture) |
| `aq7.role` | `HOLD` | coverage 0.75; usable 3/4 | macro-F1 ≈ 0.30 | `BEATGRID_PROVENANCE_LIMITATION` (1 fixture) |
| `aq7.drop_event` | `HOLD` | usable 3/4 | F1@1bar = 0.0; FP = 3; TP = 0 | `BEATGRID_PROVENANCE_LIMITATION` (1 fixture) |

Firewall after reveal: no post-reveal tuning, annotation, partition, or tolerance changes.

## Scope

| In | Out |
|---|---|
| Evaluate frozen `aq7.baseline.v1` on locked TEST/HOLDOUT only | New CALIBRATION bake-off / candidate search |
| Separate `aq7.boundary` / `aq7.role` / `aq7.drop_event` gate evidence | Global AQ7 composite quality number |
| Explicit same-identity candidate=baseline mapping | Artificial challenger deltas |
| Preserve BeatGrid / corpus HOLDs | Gate weakening / silent exclusion |
| Machine-readable external JSON for #1040 | Committed audio / private paths / orchestrator |
| Determinism/runtime evidence by reference (#959/#958) | Production switch / #1031 decision |

## Unchangeable freeze (fail closed)

This slice **must not** alter after TEST/HOLDOUT reveal:

- candidate identity / parameters / thresholds / features / feature selection
- classifier/structure configuration
- annotations / ground truth / partition membership
- benchmark tolerances / difficult slices / evaluation criteria

Rejected #1028 CALIBRATION identities remain rejected and are **not** evaluable here:

- `boundary.min_distance.4`
- `role.unknown_margin.0.03`
- `drop.onset_thresh.0.80`
- shortlist hypotheses `H-AQ7-1027-03` / `H-AQ7-1027-04` (not promoted)

Wrong freeze token, wrong candidate identity, mutated corpus identity, or incomplete TEST partition → refuse authoritative PASS (`AQ7_HOLDOUT_INCOMPLETE` or hard error before write).

## TEST/HOLDOUT firewall

Holdout is **terminal evidence** for this iteration.

1. contracts + freeze identity checked first
2. harness + output schema prepared
3. gate / completeness / failure tests frozen
4. implementation completed with **no open selection/tuning path**
5. only then evaluate locked TEST/HOLDOUT

After reveal: **no optimization from results** (no threshold chase, candidate swap, feature edit, label fix, corpus edit, hard-case removal, tolerance loosening, or new CALIBRATION loop from holdout findings).

Technical re-runs are allowed only with the **exact same** frozen code/config/corpus identity and must be documented as reproduction, not a new selection round.

## Three evidence planes (strict)

| Plane | Evaluation rule |
|---|---|
| `aq7.boundary` | Neutral StructureV1 boundaries on locked TEST/HOLDOUT; role logic must not create boundaries |
| `aq7.role` | Arrangement roles on frozen GT reference sections only |
| `aq7.drop_event` | Independent `drop_onset` event evidence; never merged into a joint quality score |

No plane may compensate for another plane's HOLD or incomplete measurement.

## Regression gates (per plane)

Each plane gate evidence block must include at least:

- frozen config identity
- partition identity (`TEST` → TEST/HOLDOUT)
- provenance
- usable coverage
- HOLDs / excluded records with reason
- relevant baseline metrics (same identity as candidate)
- locked TEST/HOLDOUT metrics
- relevant regressions (explicit zero deltas when candidate ≡ baseline)
- difficult-slice evidence
- gate outcome: `MEASURED` | `HOLD` | `INCOMPLETE`

Plane gate rules:

| Outcome | When |
|---|---|
| `MEASURED` | Usable TEST coverage on non-HOLD fixtures with measured primary metrics |
| `HOLD` | Material BeatGrid/corpus/provenance limitation prevents a full claim while remaining fixtures may still be measured |
| `INCOMPLETE` | Missing fixtures, missing provenance, or unusable surface without an authorized HOLD reason |

Overall exit:

| Token | When |
|---|---|
| `AQ7_LOCKED_HOLDOUT_EVALUATED` | All three planes `MEASURED` on full TEST pack with no material HOLD |
| `AQ7_HOLDOUT_PARTIAL_HOLD` | At least one plane `HOLD` (e.g. `beatgrid_hold`) while freeze identity and remaining measured evidence are complete |
| `AQ7_HOLDOUT_INCOMPLETE` | Freeze/corpus/partition/plane completeness failure |

## Partition policy

| Corpus `split` | AQ7 role | Allowed use in this slice |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | context / reproducibility only; **no selection**; **no tuning** |
| `TEST` | TEST / HOLDOUT | **locked evaluation + gate evidence only** |

`TEST` fixture count for completeness: **4** (frozen #1024).

## How to run

Corpus audio/GT and JSON evidence stay **outside** the repository:

```powershell
python -m src.aq7_structure_role_drop_locked_holdout `
  --work-dir <external-directory>/aq7-structure-role-drop-corpus `
  --output <external-directory>/aq7-structure-role-drop-locked-holdout.json
```

The runner rejects outputs inside the git tree. Exact floats live in the external JSON; this document records identities, firewall, and portable gate vocabulary.

## Artifact schema (locked holdout)

| Field | Notes |
|---|---|
| `document_type` | `sample-brain.aq7.structure-role-drop-locked-holdout.v1` |
| `schema_version` | `1.0.0` |
| `issue_id` | `1030` |
| `aq7_slice` | `locked_holdout_evaluation` |
| `frozen_candidate_id` / `frozen_config` | must be `aq7.baseline.v1` |
| `freeze_token` | must be `AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE` |
| `freeze_provenance` | #1028 compare document_type + freeze token + candidate |
| `evaluated_partition` | always `TEST` |
| `corpus_id` / `corpus_version` / `generator_seed` | frozen #1024 identity |
| `code_head_identity` | git HEAD when available, else `unknown` |
| `test_holdout_firewall` | post-reveal tuning / annotation / partition / tolerance flags all false; no selection on TEST |
| `candidate_equals_baseline` | always `true` for this freeze |
| `candidate_vs_baseline` | explicit same-identity mapping; plane deltas are zero |
| `gates.aq7.boundary` / `gates.aq7.role` / `gates.aq7.drop_event` | separate gate blocks |
| `splits` | CALIBRATION context + TEST locked metrics (planes separate) |
| `determinism` / `runtime` | #959 / #958 by reference; runtime separate from quality metrics |
| `exit_token` / `exit_status` | one of the three #1030 tokens |

## Non-goals

- no production switch / no #1031 decision
- no post-holdout tuning or new CALIBRATION loop
- no UI / Arrangement product / QML
- no role-created boundaries
- no new GT labels from observed results
- no private samples/DBs/caches/absolute host paths in committed artifacts
- no #1040 orchestrator

## Exit vocabulary

Exactly one:

- `AQ7_LOCKED_HOLDOUT_EVALUATED`
- `AQ7_HOLDOUT_PARTIAL_HOLD`
- `AQ7_HOLDOUT_INCOMPLETE`

Choose solely from measured evidence. Do not optimize toward a preferred status.
