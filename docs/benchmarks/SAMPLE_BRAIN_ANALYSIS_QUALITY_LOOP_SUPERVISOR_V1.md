# Sample Brain Analysis Quality-Loop Supervisor v1

**Status:** ACTIVE_SUPPORTING (frozen persistent supervisor state + self-start/resume)
**Issue:** [#1097](https://github.com/jannekbuengener/sample-brain/issues/1097)
**Parent:** [#1040](https://github.com/jannekbuengener/sample-brain/issues/1040) — Automated analyzer quality optimization loop
**Consumes:** [#1060](https://github.com/jannekbuengener/sample-brain/issues/1060) orchestration; [#1043](https://github.com/jannekbuengener/sample-brain/issues/1043) automation decision; [#1054](https://github.com/jannekbuengener/sample-brain/issues/1054) headless run; [#1064](https://github.com/jannekbuengener/sample-brain/issues/1064) candidate iterator; [#956](https://github.com/jannekbuengener/sample-brain/issues/956) analysis-eval helpers
**Tooling:** `src/analysis_quality_loop_state.py`, `src/analysis_quality_loop_supervisor.py`
**Conceptual identity:** `sample-brain.analysis-quality-loop-supervisor.v1`
**Schema version:** `1`
**Artifact version:** `1.0.0`
**Exit token:** `AQ_QUALITY_LOOP_SUPERVISOR_RESUME_V1_FROZEN`

## Purpose

Freeze the smallest Sample-Brain-owned **persistent quality-loop supervisor state**
plus a **self-start / resume seam** so already-frozen headless, decision,
orchestration, and iterator primitives can continue a bounded CALIBRATION loop
without a person translating prose into the next command after every run or
process restart.

```text
fresh or load supervisor state (host-supplied path)
  → run_orchestration (#1060)
  → consume decision.next_action unchanged (#1043)
  → iff continue_calibration: exactly one iterate_candidates (#1064)
  → build next portable supervisor state
  → atomic save via state store
  → commit boundary (iteration considered committed only after successful save)
```

This slice is deliberately **not** the promotion controller and does not claim
`AUTONOMOUS_QUALITY_LOOP_FIRST_CLOSED_CYCLE`.

## Ownership boundary

| Concern | Owner |
|---|---|
| Headless request/result + registry | #1054 — **read-only** |
| Portable analysis-eval helpers | #956 — **read-only** |
| Automation decision tokens / `next_action` | #1043 — **read-only** |
| Single-shot orchestration binder | #1060 — **read-only** |
| Bounded CALIBRATION candidate iterator | #1064 — **read-only** |
| Persistent supervisor state + atomic store | this contract (#1097) — `analysis_quality_loop_state.py` |
| One-step supervisor composition / resume | this contract (#1097) — `analysis_quality_loop_supervisor.py` |
| Workbench session / Live Kit / Channel Rack persistence | **out of scope** — never owned here |
| Track package / arrangement musical state | **out of scope** — never owned here |
| ARVP Evidence Bundle / gate engine | external opaque boundary — **no `import arvp`** |
| Promotion / PR / merge / scheduler / L3 codegen | later #1040 slices — **out of scope** |

**Hard rules:**

- automation-only surface; **not** Workbench UI, Track package, or session resume
- reuse frozen #1043 / #1054 / #1060 / #1064 vocabularies; no second decision,
  evaluator, iterator, or ARVP implementation
- consume `decision.next_action` unchanged (no reinterpretation)
- `production_authorized` always `false`
- DEVELOPMENT / CALIBRATION partition roles only for tuning iteration
- TEST / HOLDOUT / validation / external_check cannot drive candidate iteration
- no PR creation, merge, production promotion, scheduler/daemon, or L3 code generation
- persisted state holds portable refs / fingerprints, never dumps of evidence,
  audio, DB, indexes, caches, credentials, or host-private paths
- no persisted `running` status

## Artifact identity

| Field | Value |
|---|---|
| `document_type` | `sample-brain.analysis-quality-loop-supervisor.v1` |
| `artifact_version` | `1.0.0` |
| `schema_version` | `1` (integer) |
| State module | `src/analysis_quality_loop_state.py` |
| Supervisor module | `src/analysis_quality_loop_supervisor.py` |

Unsupported `document_type`, `artifact_version`, or `schema_version` values fail
closed. Corrupt or unreadable state fails closed. Neither case silently resets
to a fresh loop.

## Persisted fields (portable)

Supervisor state is a portable JSON object. It stores identities and opaque
references, not private dumps.

Required conceptual fields (v1):

| Field | Meaning |
|---|---|
| `document_type` | `sample-brain.analysis-quality-loop-supervisor.v1` |
| `artifact_version` | `1.0.0` |
| `schema_version` | `1` |
| `domain` | Supported domain id (AQ1 Path B proof: `aq1.tempo`) |
| `partition` | `{partition_id, role}` — role must be `development` or `calibration` for tuning |
| `baseline_candidate` | `{candidate_id, config_fingerprint}` |
| `active_candidate` | `{candidate_id, config_fingerprint}` — current loop tip |
| `last_known_good` | Optional `{candidate_id, config_fingerprint}` when already meaningful |
| `visited_candidate_ids` | Ordered portable candidate ids already committed in this loop |
| `search_space_id` / `search_space_version` / `search_space_fingerprint` | Domain search-space identity (#1064) |
| `iteration_index` | Non-negative committed iteration count |
| `max_iterations` | Optional finite bound (≤ search-space size when set) |
| `loop_status` | Machine status (see state machine) |
| `last_decision` | Portable refs only: `decision_status`, `decision_token` (nullable), `next_action`, `decision_fingerprint` |
| `last_orchestration_ref` | Opaque portable refs: `outcome_fingerprint`, optional `analysis_eval_fingerprint`, optional `evidence_fingerprint`, optional `gate_verdict` |
| `last_iterator_ref` | When an iterator step ran: `iterator_effect`, optional `next_candidate`, `result_fingerprint` |
| `retry` | `{budget_remaining, budget_initial, consecutive_failures, last_failure_class}` |
| `generation` | Monotonic non-negative integer advanced on each successful commit |
| `state_fingerprint` | Deterministic semantic fingerprint of the portable payload |
| `production_authorized` | Always `false` |

Optional portable history refs (not dumps):

- `history_refs`: ordered list of opaque fingerprints / identities for prior
  committed steps (orchestration outcome fingerprint and/or iterator result
  fingerprint). Must remain portable and bounded.

**Forbidden in persisted state:**

- absolute host paths, usernames, machine identity
- private sample / audio paths or audio payloads
- local DB / index / cache / model-cache paths or contents
- credentials, tokens, secrets
- full ARVP Evidence Bundles, full analysis-eval dumps, unbounded logs
- Workbench session fields, Track package fields, Live Kit / Channel Rack state

Host-local bind inputs (`work_dir`, etc.) stay outside the portable envelope and
are supplied per invocation, never persisted inside supervisor state.

## State machine

`loop_status` is the only persisted health/status vocabulary for this slice:

| Status | Meaning | May invent next candidate? |
|---|---|---|
| `ready` | Resumable; a further supervisor step may run | only if later decision says `continue_calibration` and iterator advances |
| `held` | Controlled HOLD / defer — wait for evidence or governance | no |
| `frozen` | Candidate frozen; loop tip retained | no |
| `stopped` | Explicit stop / keep-baseline / require-human-governance | no |
| `exhausted` | Search space / iteration bound exhausted | no |
| `controlled_failure` | Fail-closed business/infrastructure stop | no |
| `retry_exhausted` | Bounded retry budget consumed | no |

**No persisted `running`.** In-flight work is ephemeral process state. An
iteration is not committed until the atomic state write succeeds.

Terminal / held statuses (`held`, `frozen`, `stopped`, `exhausted`,
`controlled_failure`, `retry_exhausted`) must not select another candidate.

Mapping from consumed `#1043` / `#1064` outcomes (normative intent):

| Consumed signal | Typical `loop_status` |
|---|---|
| `continue_calibration` + iterator `advance` | `ready` (after commit) |
| `continue_calibration` + iterator `exhausted` | `exhausted` |
| `freeze_candidate` / iterator `freeze` | `frozen` |
| `keep_baseline_and_stop` / `require_human_governance` / iterator `stop` | `stopped` |
| `defer_for_evidence` / iterator `hold` / decision `hold` | `held` |
| `stop_controlled_failure` / iterator `controlled_failure` / decision `controlled_failure` | `controlled_failure` |
| retry budget reaches zero after counted failure | `retry_exhausted` |

## Commit boundary

One supervisor step owns exactly this commit boundary:

```text
1. load or create fresh state (fail-closed on corrupt/unsupported)
2. run_orchestration(...)                     # #1060 primitive, unchanged
3. read decision.next_action unchanged        # #1043 vocabulary
4. iff next_action == continue_calibration:
      exactly one iterate_candidates(...)     # #1064 primitive, unchanged
   else:
      no candidate invention
5. build next portable supervisor state
6. atomic write via state store
7. only after successful save: iteration is committed
```

Rules:

- orchestration → decision → optional one iterator → build → atomic write → commit
- at most one `#1064` iterator call per committed step
- duplicate completion / replay of an already-committed step must not advance
  generation, visited history, or active candidate again
- process restart resumes from the last successfully persisted state
- if atomic save fails, the previous committed state remains authoritative and
  the failure is observable (exception / controlled failure path); the step is
  not committed

## Retry (bounded, persisted, restart-safe)

Retry policy fields live in persisted `retry` but the **state store does not own
retry policy** — it only persists the fields the supervisor updates.

| Field | Meaning |
|---|---|
| `budget_initial` | Positive finite initial budget chosen by the host/supervisor at fresh start |
| `budget_remaining` | Decrements on counted unknown/infrastructure failures |
| `consecutive_failures` | Count of consecutive counted failures |
| `last_failure_class` | Portable short class string (e.g. `write_failure`, `unknown`) or null |

Rules:

- budget is finite and restart-safe (survives process restart via persisted state)
- repeated unknown / infrastructure failure cannot spin forever
- when `budget_remaining` reaches `0`, `loop_status` becomes `retry_exhausted`
  and further iteration is refused
- successful committed steps may clear consecutive failure counters per
  supervisor policy without inventing unbounded retries
- business terminal actions (`freeze` / `stop` / `hold` / `exhausted` /
  `controlled_failure`) are not an excuse to invent extra candidates

## Resume / replay semantics

| Situation | Required behavior |
|---|---|
| Fresh (no state file) | Deterministic initial `ready` state from explicitly selected supported domain/config |
| Restart (valid state present) | Continue from persisted identities / visited / retry / generation — no silent loss |
| Already committed step replay | Idempotent: do not double-advance visited, generation, or active candidate |
| Duplicate completion signal | Observable no-op or explicit already-committed outcome; never silent second advance |
| Write failure | Observable failure; previous committed state retained |
| Corrupt state | Fail closed with explicit error/status; **never** silent fresh reset |
| Unsupported version / type / schema | Fail closed; **never** silent fresh reset |

Corrupt or unsupported state must not be repaired by inventing a new loop that
erases provenance.

## Firewalls

### Partition firewall

Only `development` and `calibration` partition roles may drive tuning iteration
(`continue_calibration` → iterator advance). TEST / HOLDOUT / validation /
external_check roles cannot feed candidate iteration in this slice.

### Production firewall

- `production_authorized` is always `false` on persisted state and step results
- no PR creation
- no merge
- no production promotion
- no scheduler / daemon / cloud service requirement
- no L3 agent-generated code candidate generation

## Public API (planned)

### State store — `src/analysis_quality_loop_state.py`

```python
from src.analysis_quality_loop_state import (
    DOCUMENT_TYPE,
    ARTIFACT_VERSION,
    SCHEMA_VERSION,
    fresh_state,
    validate_state,
    load_state,
    save_state_atomic,
    state_fingerprint,
)

state = fresh_state(...)            # deterministic initial ready state
validated = validate_state(state)   # fail-closed
loaded = load_state(path)           # host-supplied path; fail-closed corrupt/unsupported
save_state_atomic(path, state)      # mkstemp → write → flush → fsync → os.replace
```

Atomic save requirements:

- host-supplied path only (outside repo checkout per artifact policy)
- temp file created in the same directory as the destination
- write → flush → `fsync` → `os.replace`
- reuse `#956` helpers: `canonical_json_dumps`, `fingerprint`, `assert_portable_value`

### Supervisor — `src/analysis_quality_loop_supervisor.py`

```python
from src.analysis_quality_loop_supervisor import run_supervisor_step

result = run_supervisor_step(
    state_path=host_state_path,
    request=headless_request,
    bind_kwargs={"work_dir": work_dir},
    evidence_fingerprint="<opaque sha256>",
    gate_verdict="PASS",  # opaque ARVP handoff
    # optional host override seam (existing #1060):
    next_action="continue_calibration",
)
```

`run_supervisor_step`:

1. loads or creates state at `state_path`
2. calls `run_orchestration` with the supplied request / bind / opaque gate inputs
3. consumes `decision.next_action` unchanged (host override allowed only through
   the existing orchestration `next_action=` seam for continue-proof)
4. iff that action is `continue_calibration`, calls exactly one
   `iterate_candidates` against the domain search-space provider
5. builds the next portable state and atomically saves it
6. returns a portable step result including updated state refs and
   `production_authorized: false`

## AQ1 Path B proof domain

First proof domain is AQ1 tempo candidate compare (Path B), reusing:

- adapter `aq1.tempo.candidate_compare` (#1054 / #1060)
- search space `aq1.tempo.candidate-search-space` (#1064)
- synthetic / public fixtures only — no private audio

Proof obligations for this slice:

1. fresh deterministic start
2. real AQ1 CALIBRATION orchestration through existing primitives
3. `continue_calibration` routes to exactly one `#1064` candidate
4. atomic commit of supervisor state
5. restart resumes the same committed state
6. completed iteration is not repeated
7. duplicate completion does not double-advance
8. write failure is observable
9. corrupt state fails closed
10. unsupported version fails closed
11. retry budget decrements and persists
12. retry exhaustion terminates
13. freeze / stop produce no next candidate
14. defer / HOLD produce no next candidate
15. exhaustion does not further iterate
16. TEST / HOLDOUT cannot drive iteration
17. `production_authorized` remains false
18. persisted state contains no forbidden / private paths

## Security / privacy

Supervisor state is local runtime state at a **host-supplied path outside the
repository**. See `docs/DATA_AND_ARTIFACT_POLICY.md`. Never commit supervisor
state files, private audio, DB/index/cache dumps, or machine-local sensitive
paths. Portable refs and fingerprints only.

## Explicit non-goals

- locked TEST / HOLDOUT transition and final promotion decision
- isolated PR creation / CI gate / auto-merge controller
- post-merge verification / rollback controller
- L3 agent-generated code candidate generation
- background scheduler / daemon / cloud requirement
- dashboards / telemetry
- Workbench / Track / session persistence
- AQ algorithm changes / re-baseline
- ARVP clone / second gate engine
- second decision or iterator vocabulary

## Exit

Exactly one delivery exit for [#1097](https://github.com/jannekbuengener/sample-brain/issues/1097):

```text
AQ_QUALITY_LOOP_SUPERVISOR_RESUME_V1_FROZEN
AQ_QUALITY_LOOP_SUPERVISOR_RESUME_PARTIAL_HOLD
AQ_QUALITY_LOOP_SUPERVISOR_RESUME_INSUFFICIENT
```

Expected delivery state for this slice: `DONE_MERGED_CLOSED`.
