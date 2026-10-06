# Sample Brain Analysis Automation Decision v1

**Status:** ACTIVE_SUPPORTING (frozen machine-readable decision / orchestration handoff)  
**Issue:** [#1043](https://github.com/jannekbuengener/sample-brain/issues/1043)  
**Parents:** [#1040](https://github.com/jannekbuengener/sample-brain/issues/1040), [#942](https://github.com/jannekbuengener/sample-brain/issues/942)  
**Planning sibling:** [#1047](https://github.com/jannekbuengener/sample-brain/issues/1047)  
**Consumes:** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) (`sample-brain.analysis-eval.v1`); ARVP Evidence Bundle / Gate by opaque reference (`arvp.evidence.v1`, `GateVerdict`)  
**Tooling:** `src/analysis_automation_decision.py`  
**Conceptual identity:** `sample-brain.analysis-automation-decision.v1`  
**Schema version:** `1.0.0`

## Purpose

Freeze the smallest Sample-Brain-owned **machine-readable decision / orchestration
handoff** between portable analyzer evidence and a later bounded candidate/config
iteration loop.

```text
sample-brain.analysis-eval.v1
  → (private/offline) ARVP evaluate → arvp.evidence.v1
  → sample-brain.analysis-automation-decision.v1   ← this contract
  → future headless orchestrator (#1040; out of scope here)
```

This slice owns decision status, ready tokens, next-action vocabulary, partition
firewall, production-governance firewall, and the decision semantic fingerprint.
It does **not** own ARVP metrics/gates/Evidence Bundle serialization, `#956`
observation envelopes, candidate search, runners, schedulers, or production
promotion.

## Ownership boundary

| Concern | Owner |
|---|---|
| Domain execution / GT / AQ metrics | Sample Brain (AQ epics) |
| Portable analysis-eval envelope | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| Typed metrics / compare / GateVerdict / Evidence Bundle | ARVP (merged #7/#8/#11/#12) — **opaque refs only** |
| Decision status / ready token / next-action / firewalls / decision fingerprint | this contract (#1043) |
| Candidate search / headless runner / production switch | later #1040 slices |

**Hard rules:**

- no `import arvp` in public Sample Brain runtime
- no second Evidence Bundle / Gate engine inside Sample Brain
- do not coerce ARVP `PASS|FAIL|HOLD` or observation statuses into ready tokens
- `PROMOTION_CANDIDATE_IDENTIFIED` never authorizes production mutation

**Settings:** internal evaluation/orchestration tooling only — no
`WorkbenchFeatureSettings` toggle.

## Artifact identity

| Field | Value |
|---|---|
| `document_type` | `sample-brain.analysis-automation-decision.v1` |
| `artifact_version` | `1.0.0` |
| Runtime module | `src/analysis_automation_decision.py` |

## Envelope shape

```json
{
  "document_type": "sample-brain.analysis-automation-decision.v1",
  "artifact_version": "1.0.0",
  "domain": "aq1.tempo",
  "benchmark": {
    "benchmark_id": "synthetic.aq1.tempo.decision.smoke",
    "dataset_id": "synthetic.aq1.tempo.v1",
    "dataset_content_fingerprint": "<sha256 hex>"
  },
  "partition": {
    "partition_id": "aq1-cal-smoke",
    "role": "calibration"
  },
  "baseline_candidate": {
    "candidate_id": "sample-brain.analyze.bpm.baseline",
    "config_fingerprint": "<sha256 hex>"
  },
  "current_candidate": {
    "candidate_id": "sample-brain.analyze.bpm.baseline",
    "config_fingerprint": "<sha256 hex>"
  },
  "evidence": {
    "analysis_eval_fingerprint": "<opaque sha256>",
    "evidence_fingerprint": "<opaque sha256>",
    "evidence_contract_version": "arvp.evidence.v1",
    "gate_decision": {
      "verdict": "PASS",
      "contract_version": "arvp.gate-decision.v1"
    }
  },
  "decision_status": "ready",
  "decision_token": "KEEP_CURRENT_BASELINE_PATH",
  "next_action": "keep_baseline_and_stop",
  "production_authorized": false,
  "generated_at": "2026-10-06T00:00:00Z",
  "decision_fingerprint": "<sha256 hex of semantic payload>"
}
```

Ranking / multi-plane domains (AQ5/AQ6-style) use the same envelope identity and
may carry an optional portable `planes` map (e.g. ranking vs companion status).
The shared contract must **not** invent a blended promotion score.

## Decision status (orthogonal)

| Status | Meaning |
|---|---|
| `ready` | A business decision token may be attached |
| `hold` | Evidence/availability HOLD — **no** ready token |
| `controlled_failure` | Fail-closed stop — **no** ready token |

Never coerce HOLD / controlled failure into a ready decision token.

## Ready decision tokens (only when `decision_status=ready`)

| Token | Meaning |
|---|---|
| `KEEP_CURRENT_BASELINE_PATH` | Evidence supports staying on the measured baseline |
| `PROMOTION_CANDIDATE_IDENTIFIED` | Evidence-backed candidate exists; **not** production authorization |
| `DEFER_INSUFFICIENT_EVIDENCE` | Evidence insufficient for KEEP vs promote |
| `NO_JUSTIFIED_CANDIDATE` | Candidates evaluated; none justified |

### Alias map (writers must emit V1 tokens)

| Historical / issue alias | V1 mapping |
|---|---|
| `NEED_MORE_EVIDENCE` | `DEFER_INSUFFICIENT_EVIDENCE` |
| `NEED_FURTHER_CANDIDATES` | `NO_JUSTIFIED_CANDIDATE` |
| `DEFER_PROMOTION` | **deprecated / ambiguous** — disambiguate to KEEP / DEFER_INSUFFICIENT / PROMOTION_CANDIDATE; never accept as V1 ready token |

## Next-action vocabulary

| Action | Intent |
|---|---|
| `continue_calibration` | Bounded CALIBRATION iteration |
| `freeze_candidate` | Freeze current candidate/config for locked TEST/HOLDOUT |
| `keep_baseline_and_stop` | Retain baseline; stop iteration |
| `defer_for_evidence` | Wait / HOLD for evidence |
| `require_human_governance` | Explicit human/governance decision required |
| `stop_controlled_failure` | Fail-closed stop |

Preferred pairing when `decision_status=ready`:

| Ready token | Preferred next_action |
|---|---|
| `KEEP_CURRENT_BASELINE_PATH` | `keep_baseline_and_stop` |
| `NO_JUSTIFIED_CANDIDATE` | `keep_baseline_and_stop` |
| `DEFER_INSUFFICIENT_EVIDENCE` | `defer_for_evidence` |
| `PROMOTION_CANDIDATE_IDENTIFIED` | `require_human_governance` |

## Partition firewall

Decision `partition.role` ∈:

```text
development | calibration | validation | test | external_check | holdout
```

(`holdout` is a decision-envelope alias for locked final check; analysis-eval.v1
has no `holdout` role — map fixture HOLDOUT here without inventing AQ metric rules.)

| Role class | Roles | May emit `continue_calibration` / tuning feed? |
|---|---|---|
| Tunable | `development`, `calibration` | YES |
| Non-tuning | `validation`, `test`, `external_check`, `holdout` | **NO** (fail-closed) |

Hard invariant: **TEST/HOLDOUT → tuning** is invalid. Non-tuning partitions may
only emit terminal / defer / governance / controlled-failure actions.

## Production-governance firewall

- `production_authorized` must be `false` on every valid V1 decision.
- `PROMOTION_CANDIDATE_IDENTIFIED` means only that an evidence-backed candidate
  exists and requires human/governance follow-up.
- It must never mean production/default switched, global analyzer mutation,
  user-facing enablement, or deployment authorization.

## Evidence consumption seam

Consume ARVP Evidence Bundle / gate outcomes by **opaque reference**:

| Field | Rule |
|---|---|
| `evidence.evidence_fingerprint` | Opaque SHA-256; do not recompute ARVP semantics |
| `evidence.evidence_contract_version` | Must be `arvp.evidence.v1` when evidence ref present |
| `evidence.gate_decision.verdict` | `PASS` \| `FAIL` \| `HOLD` — input only |
| `evidence.analysis_eval_fingerprint` | Opaque ref to `#956` artifact identity |

Do not embed a second gate/bundle payload. Do not reimplement ARVP compare/gate.

## Canonical serialization / fingerprint

Reuse `#956` helpers from `src/analysis_eval_artifact.py`:

- `canonical_json_dumps`
- `fingerprint`
- `assert_portable_value`

Semantic fingerprint excludes:

- `generated_at`
- the decision’s own `decision_fingerprint`
- optional `artifact_hash`

Fingerprint includes contract identity, domain, benchmark/dataset, partition,
candidates, evidence refs, `decision_status`, `decision_token` (when present),
`next_action`, `production_authorized`, and optional portable `planes`.

## Domain fixtures (synthetic only)

1. **Fixture A (AQ1-style scalar)** — keep-baseline / calibration / terminal proofs.
2. **Fixture B (AQ5/AQ6-style ranking / multi-plane)** — promotion-candidate,
   no-justified-candidate, TEST/HOLDOUT firewall proofs.

No private paths, audio, DB, caches, or credentials.

## Non-goals

- no headless AQ runner / scheduler / candidate search
- no production promotion / analyzer algorithm changes
- no ARVP core reimplementation / `import arvp`
- no AQ-specific metric redesign inside this shared layer
- no UI / QML / Workbench settings toggle

## Validation

```powershell
python -m pytest -q tests/test_analysis_automation_decision.py
python -m pytest -q tests/test_analysis_eval_artifact.py
```

## Exit

`AQ_AUTOMATION_DECISION_CONTRACT_V1_FROZEN` (after merge + issue close)
