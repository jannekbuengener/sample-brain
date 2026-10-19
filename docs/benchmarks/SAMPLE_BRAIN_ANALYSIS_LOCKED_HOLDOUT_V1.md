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
POSIX additionally fsyncs the parent directory after claim creation (before
dispatch) and result replacement (before reporting success). Windows flushes
the claim/final result file metadata, reopening the destination after rename;
see [Microsoft File Caching](https://learn.microsoft.com/en-us/windows/win32/fileio/file-caching).
Metadata-barrier errors fail closed. A replay also finishes the result metadata
barrier before returning a committed outcome. These checks prove barrier ordering
and error handling, not hardware power-loss testing.
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


## Additive decision-provider seam (#1179)

Legacy calls, claims and result version 1.0.0 remain unchanged. The optional
`provider` remains the search-space provider. A separate `decision_provider`
callable and declared portable `decision_provider_id` select provider mode;
both are required together. Any explicitly supplied legacy policy argument,
even None, mixed with provider mode is rejected before claiming or dispatch.
The ID identifies a declared policy, never a callable repr, address, path or hash.

Provider claims contain exactly freeze_state_fingerprint, request_fingerprint,
mode=provider and decision_provider_id. The canonical claim fingerprint binds
the invocation before any adapter/evaluation/provider execution. The immutable
supervisor state and the existing durable write/barrier protocol remain authority.
Claim without result always means uncertain execution, including provider failure:
no automatic evaluation or provider retry is permitted.

The existing orchestration binder invokes the provider once after validating the
real adapter result and constructing the real analysis-eval artifact, before
building the decision. The provider receives one defensive portable mapping:
domain, benchmark, partition, baseline_candidate, current_candidate,
request_fingerprint, analysis_eval_fingerprint, headless_result and analysis_eval.
Its evidence_fingerprint is the canonical fingerprint of that mapping before
adding evidence_fingerprint. This identifies the evaluation context; the provider
may return a different opaque fingerprint identifying its own gate evidence.
No bind_kwargs, runtime paths, adapter instances or supervisor state are exposed.

The provider returns exactly evidence_fingerprint, gate_verdict, decision_token,
and next_action. These use the existing S6 policy validation and #1043 builder;
PASS/FAIL require explicit policy, tuning actions remain forbidden, and existing
HOLD/controlled-failure mapping is retained. No provider-supplied Decision is
accepted. production_authorized remains false.

Provider result version 1.1.0 adds decision_provider_provenance with
 decision_provider_id, eval_context_fingerprint and policy_inputs. These are
covered by result_fingerprint; invocation_fingerprint binds the original claim.
The existing #1043 versions and semantics are unchanged. Replay checks the
committed result, mode, declared ID, freeze/request identities and stored policy
against the decision, and returns without calling the adapter or provider.
The result stores provenance and references, not a full evaluation evidence dump.

The S7 source reader supports both versions, verifies provider claim/provenance
and stored policy consistency, and retains every existing promotion criterion.
It never calls providers or recomputes evaluations or decisions. Fingerprints
provide integrity binding, not a cryptographic signature of a policy's code.
