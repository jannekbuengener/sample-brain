# Analyzer Runtime Methodology v1

**Status:** ACTIVE_SUPPORTING (frozen measurement contract)  
**Issue:** [#958](https://github.com/jannekbuengener/sample-brain/issues/958)  
**Parents:** [#950](https://github.com/jannekbuengener/sample-brain/issues/950), [#942](https://github.com/jannekbuengener/sample-brain/issues/942)  
**Tooling:** `src/analyzer_runtime_methodology.py`  
**Methodology id:** `sample_brain.analyzer_runtime_methodology.v1`  
**Schema version:** `1.0.0`

## Purpose

Freeze one reproducible Sample Brain **analyzer runtime measurement** contract so AQ1–AQ7 and #950 can reuse the same cold/steady, warm-up, repetition, percentile, provenance, and failure semantics.

This slice owns **comparable measurement**, not faster analyzers. No algorithm changes and no performance optimization belong here.

## Layer separation (normative)

| Layer | Authority | Role |
|---|---|---|
| Local Measurement (ADR-0006) | `docs/adr/ADR-0006-measurement-contract-v1.md` | Opt-in local event store / trend signals across real runs |
| Analyzer runtime bench (this doc) | `docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md` | Controlled suite timing for analyzers |
| Benchmark artifact / ARVP mapping | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) | Portable envelope that may later carry these values |

Do not conflate this bench methodology with Mixpanel, cloud telemetry, or ADR-0006 sidecar events. ARVP receives **values/evidence**; Sample Brain owns how runtime is measured. Do not put benchmark mechanics into ARVP core.

## Reuse of existing helpers

| Concern | Reuse |
|---|---|
| Percentile math | `src.measurement.stats.percentile` (linear interpolation; empty → `None`) |
| High-resolution wall clock | `time.perf_counter_ns` (same primitive family as FSLD / joint-key benches) |
| Domain harnesses | Keep `benchmark_vec`, FSLD eval, CLAP Tier-B docs as domain evidence; prefer this module for **new** shared analyzer runtime reporting |

Do not invent a second percentile implementation for this contract.

## Timing primitive

- Use `time.perf_counter_ns()` for start/stop.
- Report durations as milliseconds: `(end_ns - start_ns) / 1_000_000`.
- Do not use wall-clock datetime, ProcessTime alone, or fabricated constants for measured samples.

## Modes

| Mode | Meaning |
|---|---|
| `cold` | First measured invocation(s) with **zero discarded warm-ups**. Captures startup/import/backend init when the callable includes them. For multi-sample cold runs, callers must supply `cold_factory` so each measured sample reinitializes the analyzer; reusing one stateful callable makes only the first sample cold. |
| `steady` | Measured invocations **after** a fixed warm-up count. Warm-up timings are diagnostic only and never enter percentile aggregates. |

Comparisons are valid only within the same mode unless a report explicitly presents both.

## Warm-up policy

| Field | Default | Rule |
|---|---|---|
| `warmup_count` (`cold`) | `0` | Must be 0 |
| `warmup_count` (`steady`) | `2` | Discard exactly this many successful or attempted warm-up calls before measured samples |
| Warm-up inclusion | never | Warm-up runtimes are not part of `p50` / `p95` / `p99` |

Warm-up failures still record status/timing under `warmup_runs` and do not invent `0` ms.

## Repetition / sample-count policy

| Field | Default | Rule |
|---|---|---|
| `measured_repetitions` | `11` | Target measured attempts after warm-up |
| Minimum for `p50` | `1` ok sample | Else `p50_ms` is `null` |
| Minimum for `p95` | `5` ok samples | Else `p95_ms` is `null` |
| Minimum for `p99` | `100` ok samples | Else `p99_ms` is `null` (tiny datasets must not claim p99) |

Only runs with `status == "ok"` enter percentile and throughput aggregates. Non-ok runs remain in the run list as explicit evidence.

## Percentile semantics

- Implementation: `src.measurement.stats.percentile` (linear interpolation on a sorted copy).
- Report at least `p50_ms` (median) and `p95_ms` when sample-count gates pass.
- `p99_ms` only when `ok_count >= 100`; otherwise `null`.
- Empty ok set → all percentiles `null` (never `0.0` as a stand-in for missing).

## Input-size / record-set buckets

Every aggregate and observation must carry:

| Field | Rule |
|---|---|
| `input_bucket` | Stable bucket id (for example `clip_lt_1s`, `clip_1_5s`, `clip_5_30s`, `clip_gt_30s`, `synthetic_unit`, `record_set`) |
| `record_set_id` | Portable identity of the measured set (hash of sorted public/record ids, fixture name, or synthetic token). No absolute paths or usernames. |

Domain epics may define additional buckets but must not omit these two fields when emitting methodology-v1 observations.

## Timeout / fallback / failure semantics (hard rule)

| Status | Meaning | `runtime_ms` |
|---|---|---|
| `ok` | Callable completed normally | Elapsed ms (>= 0 only if truly elapsed) |
| `timeout` | Callable exceeded `timeout_ms` budget (enforced via bounded Future wait; observation returns without waiting forever for a hung callable) | Elapsed until timeout decision; **never fabricated `0`** |
| `failed` | Controlled exception / analyzer failure | Elapsed until failure; **never fabricated `0`** |
| `fallback` | Explicit fallback path taken (optional backend unavailable, etc.) | Elapsed for the fallback attempt; **never fabricated `0`** |
| `missing` | Could not start (absent input/fixture) | **`null`** — never `0` |

Missing, failed, or timeout runs must keep an explicit `status` and must **never** be rewritten as `0` ms success. If a non-ok path somehow records a literal `0.0` elapsed, tooling must coerce `runtime_ms` to `null` rather than publish a fake zero success. Status `missing` always forces `runtime_ms: null` regardless of measured elapsed time.

## Throughput semantics

When at least one `ok` sample exists:

```text
throughput_items_per_s = ok_count / (sum(ok_runtime_ms) / 1000.0)
```

Otherwise `throughput_items_per_s` is `null`. Throughput is derived from ok samples only and does not treat failures as free.

## Provenance / comparability

Minimum portable provenance on every suite result:

| Field | Purpose |
|---|---|
| `methodology_id` / `methodology_version` | Contract identity (`…v1` / `1.0.0`) |
| `mode` | `cold` or `steady` |
| `analyzer_id` | Stable analyzer/candidate name |
| `analyzer_revision` | Code/config fingerprint or revision token (no local paths) |
| `analyzer_config` | Portable config dict (enums/scalars only) |
| `backend_id` | Backend identity (`noop`, `numpy`, `clap`, …) |
| `dependency_versions` | Meaningful dependency/model versions used for interpretation |
| `input_bucket` / `record_set_id` | Input identity |
| `warmup_count` / `measured_repetitions` | Methodology parameters actually used |
| `timeout_ms` | Budget or `null` |

**Cross-machine equivalence is not claimed** unless a consumer later freezes an explicit environment contract. Optional host class hints (`python_version`, `platform_system`) may be attached as operational evidence only. Never embed usernames or absolute local paths in portable evidence.

## Portable observation shape (for #956)

Tooling emits values suitable for a later Sample Brain benchmark artifact / ARVP mapping. Conceptual fields:

```json
{
  "document_type": "sample_brain.analyzer_runtime_observation.v1",
  "schema_version": "1.0.0",
  "methodology_id": "sample_brain.analyzer_runtime_methodology.v1",
  "methodology_version": "1.0.0",
  "mode": "steady",
  "status": "ok",
  "runtime_ms": 12.5,
  "analyzer_id": "proof.lightweight_features",
  "analyzer_revision": "proof-v1",
  "backend_id": "synthetic",
  "input_bucket": "synthetic_unit",
  "record_set_id": "proof-lightweight-v1",
  "aggregates": {
    "ok_count": 11,
    "p50_ms": 12.1,
    "p95_ms": 13.4,
    "p99_ms": null,
    "throughput_items_per_s": 80.0
  }
}
```

#956 may rename envelope wrappers; this methodology freezes the **measurement semantics and value fields**, not ARVP type names.

## Proof cases (methodology reuse, not optimization)

1. **Lightweight deterministic path** — pure/synthetic feature-style callable with stable work and `status=ok`.
2. **Startup / fallback path** — callable with an explicit first-call startup cost and a fallback status when the optional backend is disabled.

Both must use this methodology module. Neither may change production analyzer algorithms.

## Non-goals

- No universal SLA before baselines exist
- No analyzer optimization or algorithm switch
- No hardware normalization framework
- No telemetry / cloud benchmark service / dashboard
- No p99 requirement for tiny datasets
- No WorkbenchFeatureSettings toggle (internal bench helper only)
- No implementation of #956 ARVP mapping in this slice

## Exit vocabulary

Exactly one of:

- `ANALYZER_RUNTIME_METHODOLOGY_FROZEN`
- `RUNTIME_METHODOLOGY_INSUFFICIENT`
- `INSUFFICIENT_RUNTIME_EVIDENCE`
