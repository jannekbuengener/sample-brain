# Sample Brain Analysis-Eval Artifact v1

**Status:** ACTIVE_SUPPORTING (frozen portable envelope + ARVP mapping)  
**Issue:** [#956](https://github.com/jannekbuengener/sample-brain/issues/956)  
**Parents:** [#950](https://github.com/jannekbuengener/sample-brain/issues/950), [#942](https://github.com/jannekbuengener/sample-brain/issues/942)  
**Cross-repo:** [arvp#2](https://github.com/jannekbuengener/arvp/issues/2), [arvp#7](https://github.com/jannekbuengener/arvp/issues/7) (consumed); [arvp#11](https://github.com/jannekbuengener/arvp/issues/11) / [arvp#12](https://github.com/jannekbuengener/arvp/issues/12) deferred  
**Tooling:** `src/analysis_eval_artifact.py`  
**Conceptual identity:** `sample-brain.analysis-eval.v1`  
**Schema version:** `1.0.0`

## Purpose

Freeze the smallest versioned, deterministic, portable Sample Brain benchmark
artifact that can carry analyzer observations from multiple AQ domains into the
ARVP artifact-first pipeline.

```text
Sample Brain artifact  →  ARVP (typed metrics / observations)  →  Evidence Bundle
```

This slice owns the **envelope, status vocabulary, privacy rules, and structural
ARVP #7 mapping**. It does not own AQ domain metric semantics, perturbation
mechanics (#957), runtime measurement methodology (#958), or semantic equality
(#959).

## Ownership boundary

| Concern | Owner |
|---|---|
| Audio loading, analyzer execution, ground truth, eligibility, domain metrics | Sample Brain (AQ epics) |
| Portable artifact envelope / status / provenance / record identity | this contract (#956) |
| Safe/unsafe portable projection inventory | [#960](https://github.com/jannekbuengener/sample-brain/issues/960) baseline |
| Perturbation / metamorphic transform mechanics | [#957](https://github.com/jannekbuengener/sample-brain/issues/957) |
| Analyzer runtime measurement methodology | [#958](https://github.com/jannekbuengener/sample-brain/issues/958) |
| Semantic analyzer equality / cache equivalence | [#959](https://github.com/jannekbuengener/sample-brain/issues/959) |
| Domain-neutral identities, typed MetricDefinition / MetricValue / Observation | ARVP #6 / #7 (merged) |
| FailureEvidence portable safety | ARVP #5 (merged; optional companion, not required here) |
| Evidence Bundle v1 + artifact-first runner | ARVP #11 / #12 — **deferred** |
| Comparison / gates / Evidence Bundle serialization | ARVP |

**Hard rule:** no `import arvp` in normal/public Sample Brain runtime. Mapping is
documented and proven with pure structural field-shape tests.

**Settings:** internal eval contract only — no `WorkbenchFeatureSettings` toggle.

## Architecture outcome

```text
SAMPLE_BRAIN_ARVP_ARTIFACT_BRIDGE_V1_FROZEN
```

## Consumed #960 baseline

Worktree deliverable `docs/benchmarks/ANALYZER_PORTABLE_OUTPUT_BASELINE.md`
(exit `ANALYZER_PORTABLE_OUTPUT_BASELINE_AUDITED`) is the safe/unsafe inventory
this envelope consumes:

| Value class | Artifact rule |
|---|---|
| Finite JSON number / bool / string / null | Allowed |
| Analyzer miss (`None`) | `null` + explicit status — **never** coerced to `0` |
| Non-finite float (`NaN` / `±Inf`) | Reject at serialize / validate |
| Absolute paths, usernames, private filenames, audio, DB dumps, caches, credentials | Reject |
| Raw `Path` / `bytes` / `numpy` / sets | Reject unless an AQ epic declares an explicit portable codec |
| Gesture/search zero without status | Not “measured” — status required |

Sample Brain owns sanitization before ARVP sees values.

## Artifact identity

| Field | Value |
|---|---|
| `document_type` | `sample-brain.analysis-eval.v1` |
| `artifact_version` | `1.0.0` |
| Runtime module | `src/analysis_eval_artifact.py` |

## Envelope shape

```json
{
  "document_type": "sample-brain.analysis-eval.v1",
  "artifact_version": "1.0.0",
  "benchmark": {
    "benchmark_id": "synthetic.aq1.tempo.smoke",
    "dataset_id": "synthetic.aq1.tempo.v1",
    "dataset_content_fingerprint": "<sha256 hex of canonical membership>"
  },
  "partition": {
    "partition_id": "validation-smoke",
    "role": "validation"
  },
  "candidate": {
    "candidate_id": "sample-brain.analyze.bpm.baseline",
    "implementation_id": "src.analyze",
    "revision": "contract-fixture",
    "configuration": {"profile": "baseline"},
    "config_fingerprint": "<sha256 hex of canonical configuration>"
  },
  "provenance": {
    "source_benchmark": {
      "benchmark_id": "synthetic.aq1.tempo.smoke",
      "benchmark_version": "1.0.0",
      "origin": "synthetic-public"
    },
    "run": {
      "run_id": "run-synthetic-001",
      "producer": "sample-brain.analysis-eval",
      "producer_version": "1.0.0"
    }
  },
  "records": []
}
```

### Identity / provenance rules

- Semantic IDs are portable tokens (public dataset ids or sanitized
  benchmark-local references). Host paths and usernames are forbidden.
- `partition.role` ∈ `{development, calibration, validation, test, external_check}`
  (aligned with ARVP #6 `EvaluationPartition` roles).
- Candidate `configuration` must be JSON-safe and portable; fingerprint is
  SHA-256 of canonical JSON (`sort_keys`, compact separators, `allow_nan=False`).
- Run provenance is portable only: no machine hostname, absolute work dirs, or
  local DB paths.

### Record shape

```json
{
  "record_id": "rec-001",
  "domain": "aq1.tempo",
  "eligibility": {"status": "eligible"},
  "ground_truth": {"bpm": 120.0},
  "observations": [
    {
      "observation_id": "rec-001.bpm.abs_error",
      "metric_id": "bpm.abs_error",
      "status": "measured",
      "value": 0.5,
      "unit": "bpm",
      "direction": "minimize",
      "payload": null
    }
  ]
}
```

`domain` is a free portable token owned by the emitting AQ epic (examples:
`aq1.tempo`, `aq3.onset`, `aq5.ranking`). The common envelope does not encode
all AQ schemas.

Excluded records use:

```json
"eligibility": {"status": "excluded", "reason": "duration_below_min"}
```

and must not emit ARVP observations.

## Status vocabulary

| Status | Meaning | Numeric `value` |
|---|---|---|
| `measured` | Finite measured (or derived-into-envelope) evidence | Required, finite |
| `unknown` | Missing / unknown evidence | Must be `null` / absent |
| `not_applicable` | Metric does not apply to this record | Must be `null` / absent |
| `controlled_failure` | Analyzer/adapter failed in a controlled way | Must be `null` / absent; optional `failure_code` |
| `excluded` | Record ineligible (also via `eligibility.status`) | No measured value |

Rules:

- Never coerce missing/invalid evidence to numeric zero.
- No global confidence scale.
- `direction` ∈ `{maximize, minimize, neutral}` when a metric is declared
  (aligned with ARVP #7 `MetricDefinition.direction`).
- `metric_id` must match `^[a-z][a-z0-9_.-]{0,63}$` (ARVP #7).
- `observation_id` must match `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$` (ARVP #7).

## Domain payload boundary

The envelope stays domain-neutral. Domain-specific structures live under
optional `payload` / `ground_truth` maps and remain owned by AQ1–AQ7.

Proof fixtures (synthetic only):

1. **AQ1-style scalar/timing** — single finite BPM absolute error.
2. **AQ5-style ranking** — ordered hit list with portable ids + scores (not paths).

## Canonical serialization

```text
json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
```

Fingerprints: SHA-256 hex of the UTF-8 canonical bytes. Round-trip load →
re-serialize must be byte-identical for valid artifacts.

## ARVP #7 mapping (structural)

Consumed from merged ARVP main (`arvp.metrics`):

| ARVP type | Contract version |
|---|---|
| `MetricDefinition` | `arvp.metric-definition.v1` |
| `MetricContract` | `arvp.metric-contract.v1` |
| `MetricValue` | `arvp.metric-value.v1` |
| `Observation` | `arvp.observation.v1` |
| `MetricValueStatus` | `measured` \| `derived` \| `unknown` \| `not_applicable` |

### Status mapping

| SB status | ARVP `MetricValue.status` | ARVP `value` | Notes |
|---|---|---|---|
| `measured` | `measured` | finite number | SB may mark domain-derived scalars as `measured` in the envelope; ARVP `derived` reserved for ARVP-side derivation |
| `unknown` | `unknown` | omitted / null | |
| `not_applicable` | `not_applicable` | omitted / null | |
| `controlled_failure` | `unknown` | omitted / null | SB keeps `failure_code` / reason in artifact; optional ARVP #5 FailureEvidence is out of band |
| `excluded` | *(no Observation)* | — | Record omitted from ARVP observation set |

### Field mapping (SB observation → ARVP Observation dict shape)

| SB field | ARVP Observation / MetricValue field |
|---|---|
| `observation_id` | `observation_id` |
| `metric_id` | `metric.metric_id` |
| mapped status | `metric.status` |
| finite `value` when measured | `metric.value` (ARVP stores Decimal; portable JSON number OK for mapping inventory) |
| candidate fingerprint | `candidate_fingerprint` |
| `partition.partition_id` | `partition_id` |
| partition fingerprint | `partition_fingerprint` |
| metric contract fingerprint | `metric.metric_contract_fingerprint` |
| — | `contract_version` = `arvp.observation.v1` |

Candidate / partition identity fields align with ARVP #6 (`CandidateSpec`,
`EvaluationPartition`) by portable field names; Sample Brain does not import
those classes at runtime.

### Deferred

- ARVP #11 Evidence Bundle v1 — mapping inventory ≠ Evidence Bundle.
- ARVP #12 artifact-first runner — not implemented here.

## Adjacent foundation (do not re-implement)

| Slice | Relationship |
|---|---|
| #957 | May feed synthetic fixtures into analyzers that later emit this artifact |
| #958 | Runtime methodology observations may later be carried as domain payloads / metrics |
| #959 | Semantic equality compares analyzer meaning; this envelope carries portable results |
| #960 | Portable projection baseline consumed above |

## Non-goals

- no analyzer algorithm changes or threshold tuning
- no global analysis-quality score
- no Evidence Bundle reimplementation
- no hard ARVP runtime dependency
- no Workbench / UI / settings toggle
- no private audio, DB, cache, or credentials in fixtures

## Validation

```powershell
python -m pytest -q tests/test_analysis_eval_artifact.py
```

## Exit

`SAMPLE_BRAIN_ARVP_ARTIFACT_BRIDGE_V1_FROZEN`
