# Sample Brain Analysis Orchestration Run v1

**Status:** ACTIVE_SUPPORTING (frozen single-shot headless → decision binder)
**Issue:** [#1060](https://github.com/jannekbuengener/sample-brain/issues/1060)
**Planning sibling:** [#1059](https://github.com/jannekbuengener/sample-brain/issues/1059)
**Parents:** [#1040](https://github.com/jannekbuengener/sample-brain/issues/1040), [#942](https://github.com/jannekbuengener/sample-brain/issues/942)
**Consumes:** [#1054](https://github.com/jannekbuengener/sample-brain/issues/1054) headless run; [#956](https://github.com/jannekbuengener/sample-brain/issues/956) analysis-eval; [#1043](https://github.com/jannekbuengener/sample-brain/issues/1043) automation decision
**Tooling:** `src/analysis_orchestration_run.py`
**Conceptual identity:** `sample-brain.analysis-orchestration-run.v1`
**Schema version:** `1.0.0`

## Purpose

Freeze the smallest Sample-Brain-owned **single-shot in-process orchestration binder**
that chains a registered headless AQ adapter through portable evaluation evidence
into a machine-readable automation decision — without a human translating reports.

```text
orchestration request (headless request + host bind + opaque ARVP refs)
  → validate / bind registered adapter (fail-closed)
  → DomainAdapter.run
  → validate headless result
  → binder forms/attaches portable analysis-eval.v1 fingerprint
  → host opaque evidence_fingerprint + gate_verdict
  → build_decision (#1043)
  → deterministic orchestration outcome
```

## Ownership boundary

| Concern | Owner |
|---|---|
| Headless request/result + registry | [#1054](https://github.com/jannekbuengener/sample-brain/issues/1054) — **read-only** |
| Portable analysis-eval envelope | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) — **read-only** |
| Automation decision tokens / next_action | [#1043](https://github.com/jannekbuengener/sample-brain/issues/1043) — **read-only** |
| Single-shot binder + mapping + outcome fingerprint | this contract (#1060) |
| Domain metrics / AQ runners | existing AQ modules (via thin adapters) |
| ARVP Evidence Bundle / gate engine | external opaque boundary — **no `import arvp`** |
| Candidate optimizer / scheduler / production promotion | later #1040 slices — **out of scope** |

**Hard rules:**

- no second status taxonomy (`READY` / `RUNNING` / …)
- reuse headless `completed|hold|controlled_failure` and #1043 decision vocabularies
- no `import arvp`; opaque `evidence_fingerprint` + `gate_verdict` only
- no second eval or decision schema
- `production_authorized` always `false`
- unknown adapter / unknown operation fail closed
- completed headless without valid portable eval evidence must not become `ready`
- TEST/HOLDOUT must not emit tuning `next_action` values
- host-local paths stay in bind kwargs, never in portable outcome envelopes
- prefer binder-side analysis-eval projection (adapters stay thin)
- after `adapter.run`, binder fail-closes unless `request_fingerprint` and adapter
  identity/version match the submitted request and bound adapter (#1063)
- candidate identity authority never disappears: result candidates when present,
  else validated request; sealed into the outcome `headless_result` for portable
  cross-envelope validation (#1063)
- supplied analysis-eval / decision / outcome duplicated identities must match
  that invocation authority (#1063)

## Artifact identity

| Field | Value |
|---|---|
| `document_type` | `sample-brain.analysis-orchestration-run.v1` |
| `artifact_version` | `1.0.0` |
| Runtime module | `src/analysis_orchestration_run.py` |

## Status mapping (no new taxonomy)

| Headless `run_status` | Gate (when completed) | Decision `decision_status` |
|---|---|---|
| `hold` | (ignored / unused) | `hold` — no ready token |
| `controlled_failure` | (ignored / unused) | `controlled_failure` |
| `completed` | `HOLD` | `hold` — no ready token |
| `completed` | `PASS` or `FAIL` | `ready` with existing #1043 tokens only |

Default ready pairings for the AQ1 proof path:

| Gate | Default `decision_token` | Default `next_action` |
|---|---|---|
| `PASS` | `KEEP_CURRENT_BASELINE_PATH` | `keep_baseline_and_stop` |
| `FAIL` | `NO_JUSTIFIED_CANDIDATE` | `keep_baseline_and_stop` |

Hold / controlled-failure pairings follow #1043:

- `hold` → `defer_for_evidence` (default) or `require_human_governance`
- `controlled_failure` → `stop_controlled_failure`

## Public API

```python
from src.analysis_orchestration_run import run_orchestration

outcome = run_orchestration(
    request=headless_request,
    bind_kwargs={"work_dir": work_dir},
    evidence_fingerprint="<opaque sha256>",
    gate_verdict="PASS",  # required for completed→ready; HOLD maps to decision hold
)
```

Outcome envelope (portable):

- `headless_result` — validated `#1054` result
- `analysis_eval` — `{document_type, artifact_fingerprint}` (+ optional artifact body when projected)
- `decision` — validated `#1043` decision
- `outcome_fingerprint` — semantic fingerprint of the portable outcome
- `production_authorized` — always `false`

## Proof adapter

Registered `aq1.tempo.candidate_compare` on CALIBRATION compare (Path B).
AQ6 remains registry/firewall regression only in this slice.

## Non-goals

- scheduler / cron / cloud service
- candidate optimizer / calibration loop
- autonomous production promotion
- AQ algorithm changes / AQ4 re-baseline / AQ7
- ARVP clone / second gate engine
- UI / QML
- generic subprocess framework

## Exit

```text
AQ_ORCHESTRATION_CONTRACT_DRAFT_READY
AQ_ORCHESTRATION_PROOF_TESTS_READY
AQ_ORCHESTRATION_SLICE_MERGED
```
