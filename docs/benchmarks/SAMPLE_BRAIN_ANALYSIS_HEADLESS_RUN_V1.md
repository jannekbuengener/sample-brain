# Sample Brain Analysis Headless Run v1

**Status:** ACTIVE_SUPPORTING (frozen headless request/result + static adapter registry)
**Issue:** [#1054](https://github.com/jannekbuengener/sample-brain/issues/1054)
**Planning sibling:** [#1055](https://github.com/jannekbuengener/sample-brain/issues/1055)
**Parents:** [#1040](https://github.com/jannekbuengener/sample-brain/issues/1040), [#942](https://github.com/jannekbuengener/sample-brain/issues/942)
**Consumes:** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) (`sample-brain.analysis-eval.v1` helpers import-only); [#1043](https://github.com/jannekbuengener/sample-brain/issues/1043) partition/production firewall ideas (no decision tokens)
**Tooling:** `src/analysis_headless_run.py`, `src/aq_headless_adapters/`
**Conceptual identity:** `sample-brain.analysis-headless-run.v1`
**Schema version:** `1.0.0`

## Purpose

Freeze the smallest Sample-Brain-owned **headless run request/result envelope**
plus an in-process **DomainAdapter Protocol** and **static adapter registry** so
[#1040](https://github.com/jannekbuengener/sample-brain/issues/1040) can invoke a
declared AQ surface non-interactively and receive a portable run result.

```text
headless request
  → validate + operation×partition preflight
  → STATIC_ADAPTER_REGISTRY[adapter_id]  (fail-closed)
  → bind host paths (outside portable envelope)
  → DomainAdapter.run (wraps existing run_*)
  → headless result {completed|hold|controlled_failure}
```

This slice owns the shared seam, registry, preflight, and thin AQ1/AQ6 proofs.
It does **not** own ARVP evaluation, `#1043` decision tokens/`next_action`,
candidate search, schedulers, production promotion, or domain metric schemas.

## Ownership boundary

| Concern | Owner |
|---|---|
| Request/result envelope + fingerprints + portability | this contract (#1054) |
| Protocol + static registry + op×partition preflight | this contract (#1054) |
| Domain metrics / GT / runners | existing AQ modules (wrap only) |
| Thin AQ1 / AQ6 adapters | `src/aq_headless_adapters/` |
| Portable analysis-eval envelope | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| Automation decision tokens / next_action | [#1043](https://github.com/jannekbuengener/sample-brain/issues/1043) — **not emitted here** |
| ARVP / Evidence Bundle | external opaque boundary — **no `import arvp`** |

**Hard rules:**

- no `import arvp` in public Sample Brain runtime
- no CLI/subprocess-primary dispatch; in-process Protocol only
- no dynamic plugin loading
- `production_authorized` always false on request/result
- never emit `decision_token` / `next_action` on headless run results
- unknown adapter / unknown operation fail closed
- TEST/HOLDOUT/validation/external_check reject exploratory `baseline`/`compare`;
  `locked_evaluation` allowed
- host-local paths stay outside the portable request envelope (bind before run)

## Artifact identity

| Field | Value |
|---|---|
| `document_type` | `sample-brain.analysis-headless-run.v1` |
| `artifact_version` | `1.0.0` |
| Runtime module | `src/analysis_headless_run.py` |

## Registered proof adapters (M6)

| `adapter_id` | Domain | Capabilities | Host bind |
|---|---|---|---|
| `aq1.tempo.candidate_compare` | `aq1.tempo` | `baseline`, `compare`, `locked_evaluation` | `work_dir=` |
| `aq6.ranking.candidate_compare` | `aq6.ranking` | `compare`, `locked_evaluation` | `output_path=` (+ optional fixture paths) |

Lookup:

```python
from src.analysis_headless_run import bind_adapter, lookup_adapter

entry = lookup_adapter("aq1.tempo.candidate_compare")
bound = bind_adapter("aq1.tempo.candidate_compare", work_dir=work_dir)
result = bound.run(request)
```

Unbound registry entries refuse `run` with a controlled contract error so host
paths cannot leak into portable fingerprints by accident.

## Status vocabulary

| `run_status` | Meaning |
|---|---|
| `completed` | Adapter finished with a portable domain artifact reference/fingerprint |
| `hold` | Explicit non-success hold (e.g. incomplete evidence) — not success |
| `controlled_failure` | Machine-readable failure with error code/detail — not success |

This vocabulary is **not** `#1043` `ready` / decision-token status.

## Non-goals

- AQ4 re-baseline, AQ7 implementation
- analyzer/metric/taxonomy algorithm changes
- production switch / default mutation
- optimizer / candidate generator / scheduler technology
- full `#956` projection from every adapter on day one (optional when defensible)
- UI/QML

## Architecture outcome

```text
AQ_HEADLESS_RUN_CONTRACT_V1_FROZEN
AQ_HEADLESS_INTEGRATION_SLICE_READY
```
