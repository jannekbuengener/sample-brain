# ADR-0006: Measurement Contract v1

**Status:** Accepted (READY_FOR_IMPLEMENTATION)  
**Date:** 2026-09-30  
**Related:** [SYSTEM_REQUIREMENTS](../SYSTEM_REQUIREMENTS.md) NFR-PRV-*, [DATA_AND_ARTIFACT_POLICY](../DATA_AND_ARTIFACT_POLICY.md), [TARGET_ARCHITECTURE](../TARGET_ARCHITECTURE.md) §9, [ADR-0005](ADR-0005-search-quality-evaluation.md), [evidence/README.md](../../evidence/README.md)

---

## Kontext

Sample Brain is local-first. Existing canon forbade “telemetry / analytics / usage tracking” in core pipeline components ([NFR-PRV-03](../SYSTEM_REQUIREMENTS.md), [TARGET_ARCHITECTURE §9](../TARGET_ARCHITECTURE.md)). That correctly blocks mandatory phone-home and provider coupling.

It does **not** solve a different need: engineering, evaluation and product-evidence measurement across real runs (pipeline duration, uncertainty rates, ranking→action, cache hit/miss, gate outcomes). Today those signals exist only as **opt-in harnesses** (`benchmark *`, FSLD/joint-key eval, curated `evidence/`) or as stdout progress — not as a durable local trend store.

### Live verification (2026-09-30)

| Check | Result |
|---|---|
| Branch base | `origin/main` @ `67df8bf0` (`docs/measurement-contract-v1`) |
| Open GitHub issue for Measurement Layer | **None** (architecture GO is owner-driven docs work) |
| Product Mixpanel / SaaS analytics in `src/` | **None** |
| Benchmark / eval surface | Present: `benchmark vec`, `search-quality`, `bpm-evidence`, `key-conf-evidence`, FSLD/joint-key modules, `search_eval.py` |
| Curated evidence privacy gate | `tests/test_evidence_policy.py` + `evidence/README.md` |
| User-local runtime path convention | `track_analysis_cache.get_cache_dir`, `stem_cache.resolve_cache_dir` (LOCALAPPDATA / XDG) |
| Catalog DB as metrics store | **Rejected** — would mix NFR-PRV-02 analysis data with measurement |

### Layer separation (normative)

| Layer | Answers | Existing examples |
|---|---|---|
| **Tests** | Is this case correct? | `tests/test_*.py` |
| **Benchmarks / Evaluation** | How good/fast on a controlled suite? | `benchmark search-quality`, FSLD eval, bpm/key evidence |
| **Measurement** | What happens across many real runs over time? | **This ADR** (local event store + optional export) |

```text
Measurement Layer ≠ Mixpanel ≠ mandatory telemetry
```

---

## Entscheidung

Introduce a **provider-neutral Measurement Contract v1**:

1. Core and Workbench may emit **redacted measurement events** through a narrow contract API.
2. Events persist only to a **sidecar SQLite store** outside the repo (never `catalog.db`).
3. Modes: `off` | `local` | `local+export`.
4. **Default mode = `off`** (see Storage / Modes).
5. External sinks (including Mixpanel) are **optional export adapters only**. Core must not import Mixpanel, HTTP clients, or sink SDKs.
6. Measurement is **fail-soft**: emit/store/export failures never change pipeline/Workbench success or exit behaviour beyond the measurement subsystem itself.
7. NFR-PRV-03 and architecture §9 are sharpened to forbid **external** telemetry in core while allowing **local** measurement and **explicit opt-in** export outside core.

---

## A. Canon implications (applied with this ADR)

- `NFR-PRV-03` distinguishes external telemetry vs local measurement vs opt-in export.
- `DATA_AND_ARTIFACT_POLICY` lists the measurement sidecar as local runtime state.
- `TARGET_ARCHITECTURE` §9 replaces blanket “No telemetry” with the three-way split.
- `EPIC_1_CONFIG_PROFILES` “No telemetry” means no phone-home; local measurement config keys are allowed.

---

## B. Measurement Contract v1

### B.1 Envelope

```json
{
  "document_type": "sample_brain.measurement_event",
  "schema_version": "1.0.0",
  "event_name": "pipeline.stage_finished",
  "event_version": 1,
  "occurred_at": "2026-09-30T20:15:00.123Z",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": null,
  "domain": "pipeline",
  "privacy_class": "export_safe",
  "status": "ok",
  "reason_code": null,
  "app": {
    "app_version": "0.1.0",
    "git_sha": "optional-short-sha-or-null",
    "analyzer_version": "optional-or-null",
    "search_backend": "optional-or-null"
  },
  "props": {
    "stage": "analyze",
    "wall_ms": 1234,
    "items_ok": 100,
    "items_skip": 5,
    "items_fail": 1
  }
}
```

| Field | Rule |
|---|---|
| `document_type` | Always `sample_brain.measurement_event` |
| `schema_version` | Envelope semver; breaking envelope → major bump |
| `event_name` | Dotted name from Event Catalog v1 |
| `event_version` | Integer per event_name; breaking props → increment |
| `occurred_at` | UTC ISO-8601 with milliseconds |
| `run_id` | UUID v4 per CLI invocation / harness run; required |
| `session_id` | UUID v4 per Workbench session; required for workbench domain; else null |
| `domain` | `pipeline` \| `cache` \| `search` \| `match` \| `workbench` \| `rt` \| `workflow` \| `eval` \| `eng` |
| `privacy_class` | `local_only` \| `export_safe` \| `aggregate_only` |
| `status` | `ok` \| `error` \| `cancelled` \| `skipped` |
| `reason_code` | Stable enum string or null (never free-text paths/messages) |
| `app.*` | Versions/backends only; no paths |
| `props` | Catalog-defined keys only; privacy-gated |

Canonical JSON serialization (when written to disk/export): sorted keys, `ensure_ascii=False`, `allow_nan=False`, trailing newline — consistent with FSLD/stem-cache conventions.

### B.2 Privacy classes

| Class | Persist locally | Eligible for external export | Intent |
|---|---|---|---|
| `export_safe` | Yes | Yes (when mode=`local+export`) | Enums, counts, durations, bools, buckets, versions |
| `aggregate_only` | Raw may be stored locally | **Only** derived aggregates may export | Per-run detail stays local; export histograms/rates |
| `local_only` | Yes | **Never** | Opaque local correlation tokens, anything not proven export-safe |

**Hard deny (any class, any sink, including curated `evidence/` promotion):**

- absolute/relative paths, library roots, FL paths
- filenames, titles, folder names
- raw audio, embeddings, waveforms
- search/match query text or prompts
- stable `sample_id`, content hashes, or other cross-run library identity in export payloads
- host/user/device names or machine IDs
- secrets, tokens, API keys
- free-text exception messages that may embed paths

Opaque **local** correlation (e.g. salted session-scoped token) may exist only under `privacy_class=local_only` and must be stripped by the export adapter.

Reuse deny-list spirit from [`tests/test_evidence_policy.py`](../../tests/test_evidence_policy.py); Measurement adds keys such as `path`, `relpath`, `query`, `filename`, `sample_id`, `source_hash`, `embedding`.

### B.3 Sink interface (provider-neutral)

```text
MeasurementBus
  emit(event) -> None          # fail-soft
  flush() -> None              # fail-soft

Sink (protocol)
  write(event) -> None
  flush() -> None

Implementations (v1 scope):
  NullSink           # mode=off
  SidecarSqliteSink  # mode=local and local+export (always write local first)
  # Export adapters (NOT in first implementation slice):
  # JsonlExportSink, MixpanelSink, ...
```

Rules:

- Core modules call only `MeasurementBus.emit` / helpers — never a concrete SaaS sink.
- Export adapters live behind an optional packaging/extra or separate module path loaded only when `mode=local+export`.
- Offline / auth failure / network error → export no-op; local store unaffected.

### B.4 Sidecar store

| Concern | Decision |
|---|---|
| Engine | SQLite file |
| Default path | User-local outside repo, same pattern as track/stem cache: `%LOCALAPPDATA%/sample-brain/measurement/measurement.db` (Windows) or `$XDG_CACHE_HOME/sample-brain/measurement/measurement.db` / `~/.cache/sample-brain/measurement/measurement.db` |
| Override | Env `SAMPLE_BRAIN_MEASUREMENT_DB_PATH` and/or profile key `measurement.db_path` |
| Not | `data/catalog.db`, repo-relative defaults, committed artifacts |
| Retention | Implementation-defined pruning later; v1 may keep append-only with optional max-rows config |
| Schema (logical) | `events(id, occurred_at, event_name, domain, privacy_class, run_id, session_id, payload_json)` + optional `aggregates` table in a later slice |

### B.5 Failure behaviour

- Emit/validate/write/flush exceptions are caught at the bus boundary, logged at most at debug/warning locally, and **swallowed**.
- Invalid events (unknown event_name, forbidden props, bad privacy_class) are dropped, not raised to callers.
- Enabling measurement must not change CLI exit codes for successful pipeline work.

### B.6 Aggregation

- Local raw events are the source of truth for `export_safe` and `local_only`.
- `aggregate_only` events require a documented aggregate view before export (e.g. daily histogram of `key_conf` buckets).
- First implementation slice may persist raw `export_safe` events only; aggregate views can follow.

---

## C. Event Catalog v1 (minimal)

Only decision-oriented events. No UI click spam.

### Pipeline / Analyzer

| event_name | privacy_class | Key props | Decision enabled |
|---|---|---|---|
| `pipeline.run_finished` | export_safe | `command`, `wall_ms`, `status`, `reason_code` | Which commands dominate wall time / fail |
| `pipeline.stage_finished` | export_safe | `stage` (`scan`\|`analyze`\|`autotype`\|`embed`\|`index_build`), `wall_ms`, `items_ok`, `items_skip`, `items_fail`, `status` | Stage bottlenecks and failure rates |
| `analyze.uncertainty_summary` | aggregate_only | `key_conf_below_threshold_rate`, `bpm_relation_bucket_counts`, `n` | Whether analyzer changes reduce uncertainty |

### Cache

| event_name | privacy_class | Key props | Decision enabled |
|---|---|---|---|
| `cache.lookup` | export_safe | `cache_kind` (`track`\|`stem`\|`analyze_skip`), `result` (`hit`\|`miss`\|`bypass`), `stage` | Whether cache investment pays off |

### Search / Matching / Ranking

| event_name | privacy_class | Key props | Decision enabled |
|---|---|---|---|
| `search.query_finished` | export_safe | `backend`, `wall_ms`, `result_count`, `filters_used` (bool), `status` | Backend/latency tradeoffs on real queries |
| `match.query_finished` | export_safe | `wall_ms`, `result_count`, `status` | Match cost vs value |
| `rank.action` | export_safe | `action` (`preview`\|`live_kit_assign`), `rank_index` (1-based or null), `list_size_bucket` | Whether Top-1/Top-5 ranking is musically useful |

### Workbench / Producer flow

| event_name | privacy_class | Key props | Decision enabled |
|---|---|---|---|
| `workbench.session_finished` | export_safe | `renderer` (`tk`\|`qml`), `duration_ms_bucket`, `status` | Renderer adoption / session length classes |
| `workbench.preview_finished` | export_safe | `duration_ms_bucket`, `completed` (bool) | Audition depth |
| `workflow.deconstruct_finished` | export_safe | `wall_ms`, `status`, `reason_code`, `stem_cache_result` | Deconstruct reliability/perf |

### Performance / Failure

| event_name | privacy_class | Key props | Decision enabled |
|---|---|---|---|
| `rt.callback_stats` | export_safe | `buffer_size`, `callback_mean_us`, `callback_p95_us`, `xrun_count` | RT stability trends (align with `evidence/buffer_*`) |
| `process.failure` | export_safe | `component`, `reason_code`, `status=error` | Hot failure classes without path leakage |

### Benchmark / Evaluation / Engineering

| event_name | privacy_class | Key props | Decision enabled |
|---|---|---|---|
| `eval.suite_finished` | export_safe | `suite_id`, `tier`, `metrics` (P@K/MRR or gate booleans), `status` | Algorithm regression across versions |
| `eng.gate_finished` | export_safe | `gate_id`, `result` (`PASS`\|`FAIL`\|`SKIP`), `wall_ms` | Local validation friction / repair loops |

**Explicitly out of catalog v1:** per-widget UI events, per-sample feature dumps, query text, path-bearing payloads, continuous profiling streams.

---

## D. Reuse / Emit Map

Boundary emission preferred (CLI dispatch, Workbench controller, harness finish).

| Event | Existing source / hook | New emit point | Reused evidence | Raw vs aggregate |
|---|---|---|---|---|
| `pipeline.run_finished` | `src/cli.py` command dispatch | End of each command handler (wrapper) | — | Raw export_safe |
| `pipeline.stage_finished` | `scan`/`analyze`/`embed` return counts + timing at CLI | CLI after stage returns | tqdm counts today (no timing) | Raw |
| `analyze.uncertainty_summary` | `key_conf_evidence.py`, `bpm_evidence.py` bucket logic | Post-`analyze` aggregate query or harness bridge | BPM/Key evidence docs | Aggregate_only |
| `cache.lookup` | `track_analysis_cache`, `stem_cache`, analyze `only_missing` | Cache get/set boundary helpers | Cache path conventions | Raw |
| `search.query_finished` | `src/search.py` / CLI `search` | CLI/search façade return | ADR-0004/0005 latency spirit | Raw |
| `match.query_finished` | `src/matching.py` / CLI match | CLI/match façade return | Score printout (not timed) | Raw |
| `rank.action` | Workbench preview + Live Kit assign | `workbench_controller` / Live Kit assign paths | Screen-1 workflow canon | Raw ranks only |
| `workbench.session_finished` | `workbench` / `workbench_qml` entry | Session teardown | Renderer lock docs | Raw |
| `workbench.preview_finished` | Preview playback finish callbacks | Preview controller boundary | Playhead contract (state ≠ SaaS) | Raw |
| `workflow.deconstruct_finished` | `deconstruct` CLI finish + stem cache flags | CLI deconstruct end | deconstruct `document_type` runs | Raw |
| `rt.callback_stats` | Native buffer evidence writers | Same producers → bus | `evidence/buffer_*` fields | Raw |
| `process.failure` | Controlled CLI error paths with reason codes | CLI error boundary | CLI exit-code work | Raw |
| `eval.suite_finished` | `benchmark_search_quality`, `search_eval.MetricSummary`, FSLD eval | Harness end → bus (+ optional `--json`) | ADR-0005, FSLD envelope | Raw metrics object |
| `eng.gate_finished` | stdout gate lines in vec/quality benches | Harness after gate compute | Gate evidence markdown | Raw |

---

## E. Storage / Modes

### Modes

| Mode | Local sidecar writes | External export | Core dependency |
|---|---|---|---|
| `off` | No | No | Bus = NullSink |
| `local` | Yes | No | Sidecar only |
| `local+export` | Yes (always) | Yes, via adapter after privacy filter | Sidecar + optional export module |

### Default mode: `off`

**Rationale (normative for v1):**

1. Live canon previously treated any usage tracking in core as forbidden; flipping default to `local` would change privacy posture for every install without soak evidence.
2. Fail-soft + privacy gates must be proven by the first implementation slice and tests before recommending always-on local capture.
3. Opt-in `local` is one profile/env change for developers who need Measurement Evidence immediately.
4. Promoting default to `local` is a **separate explicit decision** after soak (not part of Contract v1 acceptance).

Export remains **never** default: `local+export` requires explicit user/config action every time.

### Config keys (planned)

```yaml
measurement:
  mode: off   # off | local | local+export
  db_path: null  # null → platform user-local default
```

Env overrides: `SAMPLE_BRAIN_MEASUREMENT_MODE`, `SAMPLE_BRAIN_MEASUREMENT_DB_PATH`.

---

## F. Optional provider (Mixpanel)

- Mixpanel is a **possible future sink**, not part of Contract v1 implementation.
- No Mixpanel dependency, auth, SDK, or MCP requirement for Sample Brain core.
- If added later: map only `export_safe` events and approved aggregates; strip `local_only`; never send catalog content.
- Cursor Mixpanel plugin skills may analyze an exported project only after a human enables export and authenticates MCP — outside this ADR’s runtime scope.

---

## Privacy Matrix (summary)

| Data | local store | export | curated evidence |
|---|---|---|---|
| stage timings, counts, status, reason_code | yes | yes if export_safe | yes if reviewed |
| renderer, backend enums, gate PASS/FAIL | yes | yes | yes if reviewed |
| rank_index + action | yes | yes | yes if reviewed |
| key_conf / BPM bucket rates | yes | aggregates only | yes if reviewed |
| sample_id / path / filename / query text | **no** (deny) | **no** | **no** |
| audio / embeddings | **no** | **no** | **no** |
| salted local correlation token | local_only only | **no** | **no** |

---

## Risks

| Risk | Mitigation |
|---|---|
| Accidental path leakage in `reason_code` or props | Strict allow-lists per event; privacy tests; drop on violation |
| Catalog DB pollution | Sidecar only; tests assert no measurement tables in catalog schema helpers |
| Performance regression from emit | Boundary-only; fail-soft; default off |
| Event catalog sprawl | v1 freeze; new events require catalog amendment |
| Misreading NFR-PRV-03 | Canon wording updated with this ADR |
| Treating Measurement as Benchmark replacement | Layer table above; harnesses remain for suite gates |
| Export enabled casually | Default off; `local+export` explicit; no SDK in core |

---

## First implementation slice (after this ADR)

**Slice class:** `product_code` (small) following docs GO — still **not** implemented in this docs change.

### Scope

1. `measurement` package/module: envelope dataclass, validation, privacy deny-list, `MeasurementBus`, `NullSink`, `SidecarSqliteSink`.
2. Profile/env mode resolution; default `off`.
3. **One** production emit: `pipeline.stage_finished` for `analyze` at CLI boundary when mode=`local` or `local+export` (export adapter still no-op / absent).
4. No Mixpanel, no Workbench events, no aggregate jobs yet.

### Non-goals

- Mixpanel/HTTP/MCP
- Catalog schema changes
- Emitting from deep inside `analyze.py` loops
- Changing default mode to `local`

### Acceptance criteria

1. mode=`off` → zero DB files created; analyze behaviour unchanged.
2. mode=`local` → sidecar DB created at user-local path; one valid `pipeline.stage_finished` row after analyze; forbidden props rejected in unit tests.
3. Forced sink exception → analyze still exits success (fail-soft test).
4. No imports of mixpanel/httpx/requests in measurement core modules.
5. `python tools/check_canon_drift.py` remains green with canon docs from this ADR.

### Minimum tests

- `tests/test_measurement_contract_v1.py`: envelope validation, deny-list, mode resolution, fail-soft emit, sidecar write/read smoke with tmp_path.
- Optional CLI integration test with monkeypatched mode + tmp measurement DB.

### Test-first sequence (when implementing)

```text
DOCS_GATE (this ADR + canon) -> TEST_GATE -> TEST_FREEZE -> IMPLEMENTATION -> CHECKS
```

---

## Consequences

- Engineering can capture real-run evidence without SaaS.
- Privacy posture remains default-conservative (`off`).
- Benchmarks/tests stay authoritative for suite correctness; Measurement adds trends.
- Future Mixpanel (or any sink) plugs in without core redesign.

---

## READY_FOR_IMPLEMENTATION checklist

- [x] Live git/GitHub state verified
- [x] Existing benches/evidence/privacy/cache conventions verified
- [x] Canon split (external vs local vs export) specified
- [x] Envelope, privacy classes, sinks, sidecar, failure, aggregation specified
- [x] Minimal event catalog + reuse map
- [x] Default mode decided and justified (`off`)
- [x] Mixpanel deferred as optional sink only
- [x] First slice + AC + tests named
- [ ] Runtime implementation (explicit follow-up GO)
