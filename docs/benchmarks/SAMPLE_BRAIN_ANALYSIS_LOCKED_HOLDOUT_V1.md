# Frozen candidate to locked TEST/HOLDOUT (#1170)

Status: contract frozen for implementation; supporting #1040, #1097, #1064,
#1060, #1054, #1043 and #956. No production authorization.

## Composition and compatibility

`run_locked_holdout_transition(state_path, request, bind_kwargs,
evidence_fingerprint, gate_verdict, decision_token, next_action, provider=None)`
loads the existing supervisor state and accepts only `loop_status=frozen` with
a recorded ready `freeze_candidate` decision. Baseline/current identities must
exactly match the state, including config fingerprints. The finite provider's
id/version/content/order and membership must match the persisted search space.
Only `operation=locked_evaluation`, role `test|holdout` may execute.

The CALIBRATION supervisor and its state format remain unchanged. A separate
`sample-brain.analysis-locked-holdout-result.v1` portable artifact is stored at
the state path plus `.locked-result.json`. It contains the freeze-state and
request fingerprints, frozen identities, partition, invocation fingerprint,
orchestration/eval refs, and the complete existing #1043 decision (no evidence
dump). Terminal status is the existing decision status, not a new taxonomy.
`production_authorized=false` throughout; generation/history are never changed.

The host supplies explicit domain/policy token and action for PASS/FAIL; no
gate-to-token defaults are permitted in S6. HOLD/failure use the existing binder
mapping and never acquire a ready token. No new scoring or promotion policy.

## Necessary #1043 contract correction

The old next actions cannot represent automated handoff of a locked promotion
candidate: `keep_baseline_and_stop` contradicts that handoff, while
`require_human_governance` incorrectly mandates human intervention. Add only
`handoff_promotion_controller` to the existing decision contract. Its envelopes
use artifact version `1.1.0` (same v1 document type); only ready
`PROMOTION_CANDIDATE_IDENTIFIED`, TEST/HOLDOUT and gate PASS may use it.
All existing 1.0.0 decisions remain valid and old builder paths stay byte stable.
Readers unaware of the extension fail closed on its version/action. This is a
handoff reference only; no controller or authorization is implemented here.

## Durable execution and replay

An exclusive durable claim at state path plus `.locked-claim.json` fixes the
entire portable invocation before domain execution, including request, opaque
evidence claim, explicit policy inputs and freeze-state fingerprint. All callers
for one state use these derived paths. Concurrent/reentrant callers fail closed.
The result is flushed, fsynced and atomically replaced before success is returned.
The claim is retained. A committed identical invocation returns
`already_committed=true` without adapter execution, policy reinterpretation or
state mutation. Any changed input, state/provenance, partition or policy fails
closed. Corrupt/unsupported result/state fails closed, never resets.

A claim without a committed result is an uncertain interrupted execution and
requires external evidence reconciliation; automatic rerun is forbidden. This
deliberately provides at-most-once dispatch, not invented exactly-once crash
recovery. Write/evaluation failures preserve the claim and surface an error.
The freeze state is rechecked before result commit. Host-local adapter input
paths remain runtime bindings, never portable state; their content integrity is
the domain adapter's existing manifest/hash responsibility.

## Proof and boundaries

Real registered AQ1 Path B with sanitized synthetic manifest/predictions proves
CALIBRATION freeze then locked TEST/HOLDOUT through the existing orchestration,
eval projection and decision builder. Missing evidence, nonfinite/private paths,
wrong identities, search-space drift, invalid states, tuning actions and replay
conflicts fail closed. HOLD and controlled failure remain terminal as delivered
by #1043. No private audio, ARVP imports, second evaluator/decision engine,
promotion controller, PR automation, production switch, UI or algorithm tuning.

Exit after all delivery gates: `AQ_LOCKED_HOLDOUT_FINAL_DECISION_V1_FROZEN`.
