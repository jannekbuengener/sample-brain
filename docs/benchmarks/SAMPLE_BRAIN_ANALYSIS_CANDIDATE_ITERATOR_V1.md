# Sample Brain Analysis Candidate Iterator v1

**Status:** ACTIVE_SUPPORTING  
**Issue:** #1064  
**Parent:** #1040 — Automated analyzer quality optimization loop  
**Consumes:** #1060 orchestration, #1043 automation decision, #1054 headless run, #956 analysis-eval  
**Runtime:** `src/analysis_candidate_iterator.py`  
**Domain proof:** `src/aq_candidate_search_spaces/aq1_tempo.py`  
**Document type:** `sample-brain.analysis-candidate-iterator.v1`  
**Artifact version:** `1.0.0`

## Purpose

Freeze the smallest Sample-Brain-owned single-shot CALIBRATION iterator that turns an existing machine-readable `next_action` into either one deterministic next candidate/config identity or one terminal iterator effect.

```text
validated orchestration/decision outcome
  -> domain-owned finite ordered search space
  -> one iterator step
  -> advance | freeze | stop | hold | controlled_failure | exhausted
```

This contract is an iterator primitive only. It is not the repeat-loop driver, scheduler, ARVP evaluator, code generator, locked TEST/HOLDOUT runner, or production-promotion controller.

## Ownership boundary

| Concern | Owner |
|---|---|
| decision token / `next_action` | #1043 / #1060 |
| finite allowed candidates/configs and declaration order | domain-owned search-space provider |
| partition firewall reuse, visited/exhaustion, deterministic next selection | shared iterator |
| evaluation/gates/evidence | ARVP boundary, opaque here |
| repeat loop / locked TEST transition | later #1040 slice |
| production promotion | later #1040 promotion controller |

No `import arvp` is permitted in the iterator or AQ search-space provider.

## Shared contract

`SearchSpaceProvider` exposes:

- `search_space_id`
- `search_space_version`
- `ordered_members()`
- `search_space_fingerprint()`

Each ordered member is exactly:

```json
{
  "candidate_id": "stable-domain-candidate-id",
  "config_fingerprint": "<lowercase sha256>"
}
```

Declaration order is domain policy. The shared iterator must not lexically re-sort it.

## Iterator state

One call consumes:

- domain id;
- partition role;
- #1043 `next_action`;
- current candidate id/config fingerprint;
- ordered visited candidate ids;
- search-space fingerprint;
- optional iteration index/max-iteration bound.

The shared layer validates that current/visited candidates belong to the declared search space and that the supplied search-space/config fingerprints match the domain declaration.

## Effects

| `next_action` | iterator effect | next candidate? |
|---|---|---|
| `continue_calibration` | `advance` when an unvisited member remains, otherwise `exhausted` | only on `advance` |
| `freeze_candidate` | `freeze` | no |
| `keep_baseline_and_stop` | `stop` | no |
| `defer_for_evidence` | `hold` | no |
| `require_human_governance` | `stop` | no |
| `stop_controlled_failure` | `controlled_failure` | no |

Only `development` / `calibration` may use tuning actions. TEST/HOLDOUT/validation/external-check roles cannot emit another tuning candidate through this contract.

## Determinism and termination

Selection rule:

```text
next = first domain-declared member
       whose candidate_id is not in visited_candidate_ids
```

The iterator fails closed on:

- duplicate candidate ids in a provider declaration;
- unknown current/visited candidate;
- current config mismatch;
- search-space fingerprint mismatch;
- unsupported partition role or illegal tuning action;
- non-portable/private-path data;
- malformed or non-finite portable values.

Finite search spaces always terminate. No candidate may be selected twice in one visited history. `max_iterations` is capped at the finite search-space size.

## Portable result

The result echoes the input identity and adds iterator-specific state only:

- `document_type` / `artifact_version` / `producer_id`;
- domain and partition role;
- original `next_action`;
- `iterator_effect`;
- search-space identity/version/fingerprint;
- current candidate identity;
- visited candidate ids;
- iteration/max-iteration counts;
- optional `next_candidate` only for `advance`;
- deterministic `result_fingerprint`;
- `production_authorized: false`.

It deliberately does not hoist ARVP gate verdicts or create another decision-token/status taxonomy.

## AQ1 real-domain proof

AQ1 tempo is the first proof domain because it already has a finite ordered candidate tuple and stable config identity.

Search-space id: `aq1.tempo.candidate-search-space`  
Version: `1.0.0`

The provider reuses the exact declaration order from `TEMPO_CANDIDATES`:

1. `extract_features.bpm_normalization.none`
2. `extract_features.bpm_normalization.heuristic`
3. `extract_features.bpm_normalization.domain_110_170`

Each config fingerprint is derived from the frozen AQ1 public candidate fields: analyzer id, BPM normalization mode, candidate id and AQ1 schema version.

The proof tests show deterministic advance from baseline -> heuristic -> domain_110_170 -> exhausted without creating a new candidate or production mutation.

## Security / privacy

The iterator result is portable evidence only. No private audio, absolute host path, username, DB/index/cache data, credential or model cache may enter the portable result.

## Explicit non-goals

- no loop/daemon/scheduler;
- no dynamic source generation;
- no arbitrary code mutation;
- no ARVP gate/evidence reimplementation;
- no TEST/HOLDOUT tuning;
- no production authorization;
- no UI.

These are later #1040 concerns; #1064 provides the deterministic bounded primitive they can compose.

## Exit

Successful delivery exit:

`AQ_BOUNDED_CALIBRATION_ITERATOR_V1_FROZEN`
