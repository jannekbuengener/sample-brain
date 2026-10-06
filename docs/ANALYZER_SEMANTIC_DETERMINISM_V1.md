# Analyzer Semantic Determinism Comparator v1

**Status:** ACTIVE_SUPPORTING — contract freeze for [#959](https://github.com/jannekbuengener/sample-brain/issues/959)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#950](https://github.com/jannekbuengener/sample-brain/issues/950), [#942](https://github.com/jannekbuengener/sample-brain/issues/942)  
**Related (boundary only):**
- [#956](https://github.com/jannekbuengener/sample-brain/issues/956) may serialize comparator evidence into a portable benchmark artifact — does not own equality semantics.
- [#960](https://github.com/jannekbuengener/sample-brain/issues/960) audits non-finite / unsafe portable outputs — comparator fail-closed behavior routes there for inventory, not repair.
- [#957](https://github.com/jannekbuengener/sample-brain/issues/957) / [#958](https://github.com/jannekbuengener/sample-brain/issues/958) own perturbation fixtures and runtime methodology; not equality.

## Architecture outcome

```text
ANALYZER_SEMANTIC_DETERMINISM_CONTRACT_FROZEN
```

This contract owns **semantic projection + equality / mismatch / incompatibility** for analyzer evidence. It does **not** own musical correctness thresholds, runtime budgets, perturbation transforms, or ARVP generic comparison engines.

## Ownership

| Concern | Owner |
|---|---|
| Decision-relevant semantic fields per registered shape | this contract (`src/analyzer_semantic_determinism.py`) |
| Explicit volatile operational field exclusion | this contract |
| Structured equal / mismatch / incompatible / invalid outcomes | this contract |
| Cache-hit vs fresh projection reuse | this contract (projection only; cache algorithms remain `#237` / `track_analysis_cache`) |
| Order / tie handling | this contract, following each shape’s declared order rule |
| Non-finite / unsupported value fail-closed | this contract; durable inventory remains [#960](https://github.com/jannekbuengener/sample-brain/issues/960) |
| Portable artifact envelope / ARVP mapping | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| AQ1–AQ7 correctness thresholds / ground truth | domain epics |

## Non-goals

- no analyzer algorithm changes merely to make comparison green
- no track-analysis cache rebuild / invalidation redesign
- no blanket float rounding or silent sorting
- no heuristic “strip everything unknown”
- no WorkbenchFeatureSettings toggle / UI
- no global quality score
- no ARVP core equality engine
- no private audio, DB, cache, or absolute host paths in semantic projections

## Contract identity

| Field | Value |
|---|---|
| `contract_id` | `sample-brain.analyzer-semantic-determinism.v1` |
| `contract_version` | `1` |
| Runtime module | `src/analyzer_semantic_determinism.py` |
| Artifact policy | synthetic/public fixtures only; projections must be portable (no absolute paths / usernames) |

## Hard rules

1. **No blanket float rounding** — numeric equality is exact bit-for-bit after validating finiteness.
2. **No silent sorting** — list order is significant unless a shape explicitly declares order-irrelevant (v1 shapes do not).
3. **No ignoring missing fields** — a field present on one side and absent on the other is a mismatch (or invalid if required by the shape).
4. **Fail closed on non-finite / unsupported** — `NaN`, `±Inf`, and non-JSON-safe unsupported objects abort projection as `invalid` rather than coerce to zero/null.
5. **Volatile fields are enumerated** — only the listed operational keys are excluded; unknown decision keys are not stripped.
6. **Context incompatibility is explicit** — differing analyzer/backend/config fingerprints yield `incompatible`, not `equal` or a silent value mismatch.

## Volatile operational fields (NOT part of semantic equality)

These keys may remain audit/runtime metadata on a wrapper object. They must **not** enter the semantic projection and must **not** create false mismatches when only they differ:

| Key / family | Reason |
|---|---|
| `timestamp`, `created_at`, `updated_at`, `analyzed_at`, `wall_clock` | wall-clock time |
| `run_id`, `attempt`, `attempt_count`, `transient_id` | transient run identity |
| `duration_ms`, `runtime_ms`, `elapsed_ms`, `elapsed_sec` | pure runtime duration (not a result identity) |
| `source_path`, `absolute_path`, `host_path`, `local_path`, `file_path` | host-local absolute / path-like location |
| `username`, `hostname`, `user_home` | machine / user identity |
| `cache_dir`, `work_dir`, `tmp_path`, `temp_dir` | local operational directories |
| `cache_status` | operational hit/miss/disabled evidence — not musical semantics |
| `cache_key` | operational lookup token — identity belongs in `analysis_fingerprint` / content hash when required |

Anything **not** in this table remains candidate semantic material and is handled by the shape’s allowlisted projection (unknown keys outside the allowlist are left on the wrapper and ignored only because they were never selected — they are not heuristically deleted from a semantic object).

## Registered shapes (v1)

### 1. `track_analysis.v1`

Decision-relevant projection for Track Map / Context Analyze style results (and cache-hit vs fresh equivalence of the same blocks).

**Required semantic surface:**

| Path | Meaning |
|---|---|
| `analyzer_context.analysis_fingerprint` | analyzer/backend/config identity fingerprint |
| `overall_status` | aggregate analysis status |
| `musical.bpm` | status + value/unit/normalization/reason when present |
| `musical.key` | status + root/mode/key_conf/mode_evidence/reason when present |
| `audio_summary.loudness` | status + value/unit/method/reason when present |
| `audio_summary.brightness` | status + value/unit/method/reason when present |
| `quality_notes` | ordered quality note objects (code/severity/path/message) |

**Order rule:** `quality_notes` list order is significant.

**Input helpers:** accept either a bare analysis dict (`musical` / `audio_summary` / …) or a wrapper that also carries volatile fields and/or `track_map.analysis`.

### 2. `ranked_retrieval.v1`

Decision-relevant projection for ordered ranked retrieval / gesture-library-style rankings.

**Required semantic surface:**

| Path | Meaning |
|---|---|
| `analyzer_context.analysis_fingerprint` | ranking/analyzer config identity when supplied |
| `status` | overall ranking status (`ok`, abstention/failure codes) |
| `rankings` | ordered cluster/query ranking blocks |
| `rankings[].cluster_id` | cluster / query identity |
| `rankings[].ranked` | ordered hits: `sample_id`, `distance`, `rank` |

**Order rule:** both `rankings` and each `ranked` list are order-significant (deterministic tie order must be preserved; no re-sort during projection/compare).

## Mismatch model

`compare_semantic(left, right, *, shape)` returns a frozen outcome:

| `outcome` | When |
|---|---|
| `equal` | both sides project successfully and projections are exactly equal |
| `mismatch` | same compatible analyzer context; at least one decision-relevant path differs |
| `incompatible` | analyzer context fingerprints differ (or one missing when the other is present under strict context mode) |
| `invalid` | projection fails (non-finite number, unsupported type, malformed required shape) |

Mismatch evidence is structured and deterministic:

```json
{
  "outcome": "mismatch",
  "shape": "track_analysis.v1",
  "mismatches": [
    {"path": "musical.bpm.value", "left": 120.0, "right": 121.0}
  ]
}
```

Paths use dotted notation; list indices use `[i]` (for example `rankings[0].ranked[1].sample_id`).

## Cache-hit vs fresh

Cache-hit and fresh Track Map analysis results are compared by projecting the **same** `track_analysis.v1` semantic surface. Operational `cache_status` / `cache_key` / path rebuild metadata are volatile and must not create mismatches when the decision-relevant analysis blocks and fingerprint match.

## Reuse requirement

The same comparator seam must serve at least two structurally different shapes (`track_analysis.v1` and `ranked_retrieval.v1`) without domain-specific one-off equality helpers leaking into AQ epics.

## Relationship to existing seams

- Canonical JSON discipline for fingerprints remains `allow_nan=False` / sorted keys as used by `src/track_analysis_cache.py` and `src/fsld_current_analyzer_eval.py`.
- This module does **not** replace cache key computation; it compares projected results.
- Serialization for #956 may consume projections later; this contract does not implement the artifact envelope.

## Exit vocabulary

Exactly one program exit for #959:

- `ANALYZER_SEMANTIC_DETERMINISM_CONTRACT_FROZEN`
- `DETERMINISM_CONTRACT_INSUFFICIENT`
- `BLOCKED_BY_UNSTABLE_ANALYZER_RESULT_CONTRACT`
