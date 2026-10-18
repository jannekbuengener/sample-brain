# AQ7 Structure / Role / Drop Decision Memo (no production switch)

**Status:** ACTIVE_SUPPORTING — evidence-backed AQ7 decision for [#1031](https://github.com/jannekbuengener/sample-brain/issues/1031)
**Class:** ACTIVE_SUPPORTING
**Parents:** [#949](https://github.com/jannekbuengener/sample-brain/issues/949) (AQ7), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)
**Depends on (CLOSED):** [#1023](https://github.com/jannekbuengener/sample-brain/issues/1023), [#1024](https://github.com/jannekbuengener/sample-brain/issues/1024), [#1025](https://github.com/jannekbuengener/sample-brain/issues/1025), [#1026](https://github.com/jannekbuengener/sample-brain/issues/1026), [#1027](https://github.com/jannekbuengener/sample-brain/issues/1027), [#1028](https://github.com/jannekbuengener/sample-brain/issues/1028), [#1030](https://github.com/jannekbuengener/sample-brain/issues/1030)
**Automation contract reused by reference:** [`SAMPLE_BRAIN_ANALYSIS_AUTOMATION_DECISION_V1.md`](SAMPLE_BRAIN_ANALYSIS_AUTOMATION_DECISION_V1.md)

## Architecture outcome

```text
AQ7_STRUCTURE_ROLE_DROP_DECISION_MEMO_RECORDED

BOUNDARY_DECISION=KEEP_CURRENT_BASELINE_PATH
ROLE_DECISION=KEEP_CURRENT_BASELINE_PATH
DROP_EVENT_DECISION=NEED_MORE_EVIDENCE

PRODUCTION_SWITCH=false
```

This memo closes the bounded AQ7 measurement/decision campaign. It does not claim that the measured quality is sufficient, consumer-safe, representative of real music, or ready for production promotion.

## Scope

The decision question is limited to the evidence-backed disposition of:

1. neutral `StructureV1` boundary positions;
2. `ArrangementClassifier` roles on frozen reference sections;
3. `drop_onset` as an independent event.

The three planes remain separate. Role logic receives no authority to create or move boundaries, and `drop_onset` remains an event rather than a section role. No global AQ7 quality score is defined.

## Evidence chain

| Stage | Canonical artifact | Exit / result | Delivery evidence |
|---|---|---|---|
| Annotation + KPI contract | [`AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md`](AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md) | `AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT_FROZEN` | #1023; PR #1101; merge `f2254428` |
| Frozen corpus | [`AQ7_STRUCTURE_ROLE_DROP_CORPUS.md`](AQ7_STRUCTURE_ROLE_DROP_CORPUS.md) | `AQ7_STRUCTURE_ROLE_DROP_CORPUS_FROZEN` | #1024; PR #1109; merge `7db48b2e` |
| Neutral-boundary baseline | [`AQ7_STRUCTURE_BOUNDARY_BASELINE.md`](AQ7_STRUCTURE_BOUNDARY_BASELINE.md) | `AQ7_STRUCTURE_BOUNDARY_BASELINE_PARTIAL_HOLD` | #1025; PR #1111; merge `3852fb12` |
| Role + drop baseline | [`AQ7_STRUCTURE_ROLE_DROP_BASELINE.md`](AQ7_STRUCTURE_ROLE_DROP_BASELINE.md) | `AQ7_ROLE_DROP_BASELINE_PARTIAL_HOLD` | #1026; PR #1112; merge `3a593436` |
| Diagnostics | [`AQ7_STRUCTURE_ROLE_DROP_DIAGNOSTICS.md`](AQ7_STRUCTURE_ROLE_DROP_DIAGNOSTICS.md) | separate boundary/role/drop buckets and bounded CALIBRATION hypotheses | #1027; PR #1113; merge `f88a23e5` |
| Candidate compare | [`AQ7_STRUCTURE_ROLE_DROP_CANDIDATE_COMPARE.md`](AQ7_STRUCTURE_ROLE_DROP_CANDIDATE_COMPARE.md) | `AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE` | #1028; PR #1114; merge `fcc7d848` |
| Locked holdout | [`AQ7_STRUCTURE_ROLE_DROP_LOCKED_HOLDOUT.md`](AQ7_STRUCTURE_ROLE_DROP_LOCKED_HOLDOUT.md) | `AQ7_HOLDOUT_PARTIAL_HOLD` | #1030; PRs #1115/#1116; merges `847db30f` / `b9e28d09` |

Decision order: **contract -> corpus -> independent boundary baseline -> role/drop baseline on frozen reference geometry -> diagnostics -> CALIBRATION-only candidate freeze -> locked TEST/HOLDOUT -> this memo**.

## Frozen identities

| Field | Value |
|---|---|
| AQ/domain identities | `aq7.boundary`, `aq7.role`, `aq7.drop_event` |
| Corpus id / version / seed | `sample-brain.aq7.structure-role-drop.synthetic.v1` / `1.0.0` / `1024001` |
| CALIBRATION partition | 6 frozen fixtures; candidate selection permitted |
| Locked partition | 4 frozen `TEST` fixtures mapped to TEST/HOLDOUT; tuning forbidden |
| Baseline candidate | `aq7.baseline.v1` |
| Frozen candidate/config | `aq7.baseline.v1`; StructureV1 defaults + ArrangementClassifier defaults pinned by #1116 |
| Freeze token | `AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE` |
| Locked holdout artifact type | `sample-brain.aq7.structure-role-drop-locked-holdout.v1` / `1.0.0` |
| Locked holdout exit | `AQ7_HOLDOUT_PARTIAL_HOLD` |

The candidate and baseline identities are intentionally equal. Rejected adapters are not synthetic challengers in the holdout and have no promotion status.

## Locked holdout integrity

The #1028 freeze preceded #1030. The locked run consumed only `aq7.baseline.v1` and reported:

```text
evaluated_partition=TEST
candidate_equals_baseline=true
test_used_for_selection=false
no_tuning_on_test=true
post_reveal_tuning=false
annotation_changes=false
partition_changes=false
tolerance_changes=false
```

No threshold, feature, candidate, config, annotation, tolerance, ground truth, or split assignment is changed by this memo. The rejected CALIBRATION adapters remain rejected:

- `boundary.min_distance.4`;
- `role.unknown_margin.0.03`;
- `drop.onset_thresh.0.80`.

## Boundary decision (`aq7.boundary`)

```text
BOUNDARY_DECISION=KEEP_CURRENT_BASELINE_PATH
```

Evidence:

- CALIBRATION baseline: precision `0.343`, recall `0.923`, F1 `0.500`; over-segmentation rate `1.0`.
- `boundary.min_distance.4` improved CALIBRATION precision to `0.417` but reduced recall to `0.769`, exceeding the frozen `0.05` recall-regression allowance; it was not justified.
- Locked TEST/HOLDOUT on the retained baseline: precision `0.360`, recall `1.000`, F1 `0.529`, 16 false positives, over-segmentation rate `1.0`, usable 3/4, gate `HOLD`.

Result: among the frozen tested paths, the current baseline is the best-supported retained path. This is not a quality-sufficiency claim: low precision, systematic over-segmentation, large section-count error, the BeatGrid HOLD, and thin synthetic support remain visible.

## Role decision (`aq7.role`)

```text
ROLE_DECISION=KEEP_CURRENT_BASELINE_PATH
```

Evidence:

- CALIBRATION baseline macro-F1: `0.457` on support 17.
- `role.unknown_margin.0.03` raised CALIBRATION macro-F1 to `0.492` but collapsed unknown-reference honesty from `1.0` to `0.0`; it was not justified by the frozen role gate.
- Locked TEST/HOLDOUT baseline: macro-F1 `0.297`, coverage `0.75`, support 12, one abstention, usable 3/4, gate `HOLD`.

Result: the tested role adapter does not dominate the current path because its apparent macro gain violates the independent unknown/abstention constraint. Keep-current means only retention of the best-supported tested path; weak role accuracy and coverage remain explicit limitations.

## Drop-event decision (`aq7.drop_event`)

```text
DROP_EVENT_DECISION=NEED_MORE_EVIDENCE
```

Evidence:

- CALIBRATION baseline: F1 `0.0`, 0 matched events, 6 false positives.
- `drop.onset_thresh.0.80` reduced false positives from 6 to 4 but did not improve F1 or true-positive count; the frozen falsifier explicitly rejects FP-only reduction as a promotion basis.
- Locked TEST/HOLDOUT baseline: F1 `0.0`, 0 matched events, 3 false positives, 2 missed events, usable 3/4, gate `HOLD`.

Result: no tested path demonstrates positive `drop_onset` detection evidence. The production baseline remains factually unchanged, but the evidence does not support `KEEP_CURRENT_BASELINE_PATH` as a positive drop-quality decision and identifies no promotion candidate. A later campaign needs new, independently frozen evidence and a bounded CALIBRATION candidate before another locked holdout; this holdout must not become tuning feedback.

## Remaining HOLDs and limitations

| Limitation | Status / consequence |
|---|---|
| BeatGrid dependency | One locked TEST fixture has missing BeatGrid provenance; all three plane gates remain `HOLD`. No timing positions are invented. |
| Corpus scale / representativeness | 6 CALIBRATION + 4 TEST synthetic fixtures are enough for the bounded harness, not for library-wide or genre-wide claims. |
| Synthetic/public evidence | Synthetic generator evidence only; no independently annotated public/human-reference music corpus is established here. |
| Optional signals | Stem/CLAP or other optional-signal evidence is not ground truth and was not promoted into labels. |
| Boundary difficult slices | High recall coexists with low precision, over-segmentation `1.0`, and large section-count error. |
| Role difficult slices | Locked macro-F1 is `0.297`; coverage is `0.75`; unknown/abstention honesty cannot be traded away for a small macro gain. |
| Drop difficult slices | Zero matched events on CALIBRATION and TEST/HOLDOUT; current evidence cannot support a positive drop-quality path decision. |
| Determinism | Harness repeatability is regression-tested; the reproduced single CLI artifact itself reports determinism `unknown` rather than claiming two-run equality. |
| Runtime | Diagnostic single-pass timing only; #958 cold/steady track-length buckets remain `HOLD`. |
| ARVP handoff | No committed #956 analysis-eval artifact or ARVP Evidence Bundle fingerprint exists for this decision; references remain explicit and missing fingerprints are not fabricated. |

## Machine-readable handoff (#1040-facing)

The following JSON is a **decision projection over existing contracts and artifact identities**, not a second decision schema. `automation_v1` names the existing #1043 vocabulary. Formal #956/ARVP fingerprints remain `null` with an explicit status because those artifacts were not materialized by #1023-#1030.

```json
{
  "automation_v1": {
    "contract": "sample-brain.analysis-automation-decision.v1",
    "decision_status": "ready",
    "decision_token": "DEFER_INSUFFICIENT_EVIDENCE",
    "next_action": "defer_for_evidence",
    "production_authorized": false
  },
  "domain": "aq7.structure_role_drop",
  "benchmark": {
    "corpus_id": "sample-brain.aq7.structure-role-drop.synthetic.v1",
    "corpus_version": "1.0.0",
    "generator_seed": 1024001
  },
  "partitions": {
    "selection": "CALIBRATION",
    "locked_evaluation": "TEST/HOLDOUT",
    "test_used_for_selection": false,
    "no_tuning_on_test": true
  },
  "baseline_candidate": {
    "candidate_id": "aq7.baseline.v1"
  },
  "frozen_candidate": {
    "candidate_id": "aq7.baseline.v1",
    "freeze_token": "AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE",
    "candidate_equals_baseline": true
  },
  "evidence": {
    "candidate_compare": {
      "document_type": "sample-brain.aq7.structure-role-drop-candidate-compare.v1",
      "schema_version": "1.0.0",
      "repo_reference": "docs/benchmarks/AQ7_STRUCTURE_ROLE_DROP_CANDIDATE_COMPARE.md",
      "exit_token": "AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE"
    },
    "locked_holdout": {
      "document_type": "sample-brain.aq7.structure-role-drop-locked-holdout.v1",
      "schema_version": "1.0.0",
      "repo_reference": "docs/benchmarks/AQ7_STRUCTURE_ROLE_DROP_LOCKED_HOLDOUT.md",
      "exit_token": "AQ7_HOLDOUT_PARTIAL_HOLD"
    },
    "analysis_eval_fingerprint": null,
    "arvp_evidence_fingerprint": null,
    "fingerprint_status": "NOT_MATERIALIZED_DO_NOT_INVENT"
  },
  "planes": {
    "aq7.boundary": {
      "decision_token": "KEEP_CURRENT_BASELINE_PATH",
      "holdout_gate": "HOLD",
      "hold_reason": "BEATGRID_PROVENANCE_LIMITATION"
    },
    "aq7.role": {
      "decision_token": "KEEP_CURRENT_BASELINE_PATH",
      "holdout_gate": "HOLD",
      "hold_reason": "BEATGRID_PROVENANCE_LIMITATION"
    },
    "aq7.drop_event": {
      "decision_token": "NEED_MORE_EVIDENCE",
      "automation_v1_token": "DEFER_INSUFFICIENT_EVIDENCE",
      "holdout_gate": "HOLD",
      "hold_reason": "BEATGRID_PROVENANCE_LIMITATION"
    }
  },
  "provenance": {
    "issues": [1023, 1024, 1025, 1026, 1027, 1028, 1030, 1031],
    "merge_shas": [
      "f2254428ec7b1fcd0d5616c14441e2ee12c6474d",
      "7db48b2e093a93953adf4ca73e187a942482557b",
      "3852fb123013c701415d5693c6853146d4bbb4bb",
      "3a5934363f93acbf5691302897b0f035c5833704",
      "f88a23e5308dc24bfece4028beafbc24a02e6d35",
      "fcc7d8488317f10bd7b47ba75bbc46a0e7f14d18",
      "847db30f60e4a2b2316bb127eabf17dc6ea01881",
      "b9e28d09712325717a397670de8f1b67e707f7ea"
    ]
  }
}
```

The top-level automation token maps the mixed plane result to the existing V1 alias rule: issue token `NEED_MORE_EVIDENCE` -> automation token `DEFER_INSUFFICIENT_EVIDENCE`. It does not blend plane metrics and does not overwrite the two keep-current plane decisions.

## Production consequence

**This slice changes no production algorithm, default, threshold, feature extraction, candidate configuration, QML surface, Windows runtime, audio engine, search/matching path, or user-facing behavior.**

No `PROMOTION_CANDIDATE_IDENTIFIED` token is emitted. Any future StructureV1, ArrangementClassifier, or drop-event production change requires a separate test-first implementation slice with newly frozen CALIBRATION evidence and a new locked holdout. The existing #1030 TEST/HOLDOUT results may not be recycled into tuning.

## #949 disposition

The #949 measurement campaign is closable after this memo because its canonical chain is complete and the three decisions are explicit, even though one plane exits `NEED_MORE_EVIDENCE` and all locked gates preserve a BeatGrid HOLD. Closing #949 means the bounded AQ7 evidence/decision campaign is complete; it does not mean AQ7 quality is proven or production promotion is authorized.

No follow-up issue is created by this memo. A future drop-event evidence campaign is only actionable when an independently frozen corpus/candidate scope exists; creating algorithm work from the current holdout would violate the TEST/HOLDOUT firewall.

## Exit vocabulary

Exactly one:

- `AQ7_STRUCTURE_ROLE_DROP_DECISION_MEMO_RECORDED`
- `AQ7_STRUCTURE_ROLE_DROP_DECISION_INSUFFICIENT_EVIDENCE`

This slice exits `AQ7_STRUCTURE_ROLE_DROP_DECISION_MEMO_RECORDED`: the decision question is answerable with separate plane tokens, the drop-plane insufficiency and all HOLDs remain visible, and no production switch occurs.
