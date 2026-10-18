# Sample Brain Analysis Locked TEST/HOLDOUT Transition + Final Machine Decision v1

**Status:** ACTIVE_SUPPORTING (frozen-candidate → locked evaluation → final #1043 decision)
**Issue:** [#1170](https://github.com/jannekbuengener/sample-brain/issues/1170)
**Parent:** [#1040](https://github.com/jannekbuengener/sample-brain/issues/1040) — Automated analyzer quality optimization loop
**Consumes:** [#1097](https://github.com/jannekbuengener/sample-brain/issues/1097) supervisor state/resume; [#1064](https://github.com/jannekbuengener/sample-brain/issues/1064) candidate iterator; [#1060](https://github.com/jannekbuengener/sample-brain/issues/1060) orchestration binder; [#1054](https://github.com/jannekbuengener/sample-brain/issues/1054) headless run; [#1043](https://github.com/jannekbuengener/sample-brain/issues/1043) automation decision; [#956](https://github.com/jannekbuengener/sample-brain/issues/956) analysis-eval helpers
**Tooling:** `src/analysis_locked_holdout.py`, `src/analysis_quality_loop_state.py` (optional `locked_evaluation` state extension)
**Conceptual identity:** `sample-brain.analysis-locked-holdout-transition.v1`
**Artifact version:** `1.0.0`
**Exit token:** `AQ_LOCKED_HOLDOUT_FINAL_DECISION_V1_FROZEN`

## Purpose

Freeze the smallest Sample-Brain-owned **frozen-candidate → locked TEST/HOLDOUT transition + final machine decision seam**. This slice starts only after CALIBRATION has produced a persisted supervisor state with `loop_status="frozen"`. It executes exactly one locked non-tuning evaluation for the frozen candidate/config, binds the resulting portable evidence into the existing #1043 machine-readable decision contract, and persists a terminal final outcome that a later promotion controller can consume.

```text
persisted supervisor state: loop_status=frozen
        ↓
validate frozen candidate/config identity + baseline identity
        ↓
validate locked headless request (operation=locked_evaluation, role=test|holdout)
        ↓
run existing #1060 orchestration (unchanged)
        ↓
portable analysis-eval ref + opaque ARVP evidence fingerprint/gate verdict
        ↓
existing #1043 final machine-readable decision (unchanged vocabulary)
        ↓
persist terminal locked-evaluation outcome inside supervisor state
        ↓
future promotion controller (separate slice)
```

This slice is **not** the promotion controller: no branch/worktree creation, no PR, no merge, no production mutation, no `AUTONOMOUS_QUALITY_LOOP_FIRST_CLOSED_CYCLE` claim.

## Ownership boundary

| Concern | Owner |
|---|---|
| Persistent supervisor state + atomic store | #1097 — **read-only composition target** (optional field extension only) |
| Headless request/result + registry | #1054 — **read-only** |
| Portable analysis-eval helpers | #956 — **read-only** |
| Automation decision tokens / `next_action` / partition firewall | #1043 — **read-only** |
| Single-shot orchestration binder | #1060 — **read-only** |
| Bounded CALIBRATION candidate iterator | #1064 — **read-only** |
| Locked TEST/HOLDOUT transition + final decision composition | this contract (#1170) — `analysis_locked_holdout.py` |
| ARVP Evidence Bundle / gate engine | external opaque boundary — **no `import arvp`** |
| Promotion controller / PR / merge / scheduler / L3 codegen | later #1040 slices — **out of scope** |

**Hard rules:**

- reuse frozen #1043 / #1054 / #1060 / #1064 vocabularies; no second decision, evaluator, iterator, gate, or status taxonomy
- consume `decision.next_action` unchanged; no reinterpretation
- `production_authorized` always `false` everywhere
- `loop_status` remains `frozen` after the locked transition; #1097 CALIBRATION refusal is never weakened
- locked request must use `operation="locked_evaluation"` with a non-tuning partition role (`test` or `holdout`)
- TEST/HOLDOUT evidence is terminal for this iteration and can never feed `continue_calibration` or `freeze_candidate` again
- no thresholds, labels, partitions, candidate configs, tolerances, or search-space contents change after freeze
- ARVP stays opaque; domain/policy semantics produce the ready token via the existing #1060 host seam, never a generic PASS→promote coercion

## State extension (version-compatible)

Supervisor state gains one optional portable field, `locked_evaluation`. Absent fields keep the #1097 fingerprint payload byte-identical, so pre-S6 states stay valid without migration.

```json
"locked_evaluation": {
  "candidate": {"candidate_id": "...", "config_fingerprint": "..."},
  "baseline_candidate": {"candidate_id": "...", "config_fingerprint": "..."},
  "partition": {"partition_id": "...", "role": "test|holdout"},
  "request_fingerprint": "<sha256 hex>",
  "outcome_fingerprint": "<sha256 hex>",
  "analysis_eval_fingerprint": "<sha256 hex>",
  "evidence_fingerprint": "<sha256 hex>",
  "gate_verdict": "PASS|FAIL|HOLD",
  "decision": {
    "decision_status": "ready|hold|controlled_failure",
    "decision_token": "PROMOTION_CANDIDATE_IDENTIFIED|KEEP_CURRENT_BASELINE_PATH|NO_JUSTIFIED_CANDIDATE|null",
    "next_action": "keep_baseline_and_stop|defer_for_evidence|require_human_governance|stop_controlled_failure",
    "decision_fingerprint": "<sha256 hex>"
  },
  "terminal_status": "completed|held|controlled_failure",
  "production_authorized": false
}
```

Persisted values are portable refs / fingerprints only — no host paths, no evidence dumps, no private data.

## Transition semantics

Entry requirements (fail closed otherwise):

1. persisted supervisor state exists and validates; `loop_status == "frozen"`;
2. request validates under #1054 and uses `operation="locked_evaluation"`;
3. request partition role is `test` or `holdout`;
4. request domain equals state domain;
5. request `current` equals the frozen `active_candidate` exactly (candidate_id + config_fingerprint);
6. request `baseline` equals the persisted `baseline_candidate` exactly.

Outcome composition:

- run existing `run_orchestration` with host-supplied opaque `evidence_fingerprint` / `gate_verdict` and the existing #1060 host seam for `decision_token` / `next_action`;
- verify the produced decision's `next_action` is non-tuning (defense in depth over #1043's partition firewall);
- verify the outcome's bound `baseline` / `current` identities equal the frozen identities;
- map `decision_status` → `terminal_status`: `ready` → `completed`, `hold` → `held`, `controlled_failure` → `controlled_failure`;
- attach `locked_evaluation`, advance `generation` by one, append `outcome_fingerprint` and `decision_fingerprint` to `history_refs`, and atomically save; `loop_status` stays `frozen`.

Idempotent replay:

- if `locked_evaluation` is already committed, the transition must not rerun orchestration, must not mutate the state, and must return an observable `already_committed` result — but only when the incoming inputs match the committed claim: identical `request_fingerprint`, identical `evidence_fingerprint`, and any supplied `gate_verdict` / `decision_token` / `next_action` identical to the committed values.
- any differing input against a committed locked evaluation fails closed (post-freeze identity change refused). A changed request, evidence claim, gate verdict, or decision seam can never silently re-run or rewrite the frozen outcome.

## Final-decision semantics

ARVP `PASS|FAIL|HOLD` is an evidence input, never a promotion trigger. The existing #1043 mapping remains binding:

- ready + domain/policy token (`PROMOTION_CANDIDATE_IDENTIFIED`, `KEEP_CURRENT_BASELINE_PATH`, `NO_JUSTIFIED_CANDIDATE`) → terminal non-tuning handoff; `production_authorized` stays `false`;
- insufficient/unknown evidence → `hold`, no ready token, `defer_for_evidence` or explicit governance handoff;
- controlled execution/evidence failure → `controlled_failure` + `stop_controlled_failure`.

`PROMOTION_CANDIDATE_IDENTIFIED` means only evidence-backed promotion candidacy; it does not authorize production.

## Firewalls

- **Partition firewall:** locked evaluation runs only on `test`/`holdout` roles. CALIBRATION/development roles fail closed before any domain execution. Non-tuning partition roles can never produce tuning `next_action`s (#1043 rule; re-asserted here).
- **Freeze firewall:** no frozen-identity substitution, no post-freeze candidate/config/partition mutation, no second locked evaluation under changed inputs.
- **Terminal firewall:** after a committed locked evaluation, #1097's `frozen` status continues to refuse CALIBRATION iteration; the locked outcome is terminal for the loop iteration.
- **Production firewall:** no PR, no merge, no production switch; `production_authorized` stays `false` on state, result, and decision.

## Public API

```python
from src.analysis_locked_holdout import (
    AnalysisLockedHoldoutError,
    build_locked_evaluation_ref,
    run_locked_holdout_transition,
    validate_locked_evaluation_ref,
)

result = run_locked_holdout_transition(
    state_path=host_state_path,      # persisted supervisor state with loop_status=frozen
    request=locked_headless_request, # #1054 request, operation=locked_evaluation, role=test|holdout
    bind_kwargs={"work_dir": work_dir},
    evidence_fingerprint="<opaque sha256>",
    gate_verdict="PASS",             # opaque ARVP handoff
    # optional existing #1060 host seam (domain/policy token selection):
    decision_token="PROMOTION_CANDIDATE_IDENTIFIED",
    next_action="keep_baseline_and_stop",
)
```

Result shape (portable): `production_authorized: false`, `already_committed: bool`, `locked_evaluation` ref, `decision` ref, committed `state`.

## Proof domain

AQ1 Path B (`aq1.tempo.candidate_compare`, `locked_evaluation`, `test`/`holdout` → TEST split) is the first proof domain, reusing #1097's AQ1 fixture harness. No private audio.

## Explicit non-goals

- promotion controller (branch/worktree/PR/CI/merge)
- post-merge verification / LAST_KNOWN_GOOD recovery
- L3 agent-generated code candidates
- scheduler/daemon/cloud requirement
- dashboards / telemetry / UI
- ARVP clone / second gate engine / second decision vocabulary
- CALIBRATION iteration changes (do not reopen #1097/#1064 semantics)

## Exit

Exactly one:

```text
AQ_LOCKED_HOLDOUT_FINAL_DECISION_V1_FROZEN
AQ_LOCKED_HOLDOUT_FINAL_DECISION_PARTIAL_HOLD
AQ_LOCKED_HOLDOUT_FINAL_DECISION_INSUFFICIENT
```

Expected delivery state: `DONE_MERGED_CLOSED` for this slice only.
