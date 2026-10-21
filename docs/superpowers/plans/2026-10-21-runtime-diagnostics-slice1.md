# Runtime Diagnostics Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver #1242 by hardening Measurement Contract v1, freezing safe diagnostics correlation/privacy semantics, adding the minimal diagnostics-oriented Measurement events, and defining a privacy-tested Diagnostic Bundle V1 contract without adding runtime logging, Qt/native instrumentation, CLI export, or CI artifact upload.

**Architecture:** ADR-0006 remains the only Measurement authority. Slice 1 strengthens the existing Measurement envelope and event catalog, gives Workbench one stable session correlation seam independent of Measurement enablement, fixes per-query `run_id` drift by reusing one observer run id, and adds a pure no-I/O Diagnostic Bundle V1 validator plus normative contract documentation. Runtime diagnostics writers, Qt/faulthandler hooks, native snapshot collection, bundle generation, CLI and CI integration remain later slices.

**Tech Stack:** Python 3.12, dataclasses, `uuid`, `datetime`, SQLite-backed existing Measurement bus/sink, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-10-21-runtime-diagnostics-agent-evidence-design.md`

## Global Constraints

- ADR-0006 remains the sole Measurement authority; do not create another event bus or Measurement store.
- Measurement default remains `off`; Slice 1 must not enable local Measurement implicitly.
- No private absolute paths, sample/library identity, device identity, query text, credentials, raw exception text, traceback text, raw audio, DB/index/cache content, or host identity may enter export-safe evidence.
- Raw/private runtime diagnostics are contract-only in this slice; do not implement JSONL writers, Qt handlers, faulthandler file capture, native polling, CLI bundle generation, CI artifacts, dumps or external telemetry.
- No diagnostic I/O, SQLite access, serialization, logging callback, allocation-heavy work, network access, or blocking synchronization may be added to the realtime audio callback.
- Existing valid `pipeline.stage_finished` and `match.query_finished` behavior remains compatible except for the intentional correlation fix that stops generating a new match `run_id` per query.
- Diagnostics/Measurement failures remain fail-soft and must not change product success/exit behavior.
- TDD order: RED test → verify failure → minimal implementation → GREEN → focused regression → commit.

## Review Focus

1. **Malformed or privacy-bearing envelope metadata** — invalid UUID/timestamp/app/reason-code values must fail closed rather than pass because `props` are safe. Task 1 owns these tests.
2. **Measurement disabled** — Workbench must still have one stable session correlation ID while no Measurement DB is created and no observer writes occur. Task 3 owns this test.
3. **Repeated match queries** — one composed observer/session must reuse the same run/session correlation instead of creating one `run_id` per query. Task 3 owns this test.
4. **Bundle privacy bypass through nesting** — forbidden keys/private paths must be rejected recursively inside `last_events`, summaries or embedded Measurement payloads. Task 4 owns this test.
5. **Realtime scope creep** — Slice 1 must not touch native callback code or add runtime writers/hooks. Task 4 owns a source-scope assertion/review gate and final diff inspection.

---

### Task 1: Harden Measurement envelope and privacy validation

**Files:**
- Modify: `src/measurement/contract.py`
- Modify: `tests/test_measurement_contract_v1.py`

**Interfaces:**
- Consumes: existing `MeasurementEvent` and `validate_event(event) -> Optional[MeasurementEvent]`.
- Produces: hardened `validate_event()` semantics used by all later tasks; shared safe metadata constants/helpers may stay module-private unless Task 4 needs a public privacy helper.

- [ ] **Step 1: Write failing envelope-validation tests**

Add focused tests proving:
- `run_id` must be a canonical UUID v4 string;
- non-null `session_id` must be a canonical UUID v4 string;
- `occurred_at` must be a valid UTC ISO-8601 timestamp ending in `Z` with millisecond precision;
- `app` accepts only `app_version`, `git_sha`, `analyzer_version`, `search_backend`;
- `app` rejects extra/private identity keys and path-bearing values;
- `git_sha` is `None` or 7–40 hexadecimal characters;
- other non-null `app` values are bounded safe tokens, not arbitrary free text/paths;
- `reason_code=None` and stable machine codes such as `AUDIO_DEVICE_UNAVAILABLE` are valid;
- free-text/path-like/oversized reason codes are rejected;
- existing valid stage/match fixtures remain accepted.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:
```bash
python -m pytest tests/test_measurement_contract_v1.py -q
```
Expected: newly added UUID/timestamp/app/reason-code tests fail on current `main` while existing tests remain green.

- [ ] **Step 3: Implement minimal hardening in `src/measurement/contract.py`**

Keep envelope schema version `1.0.0`. Add internal validators/constants rather than changing `MeasurementEvent` shape:
- canonical UUID-v4 validation using `uuid.UUID`;
- UTC millisecond `Z` timestamp validation;
- exact allowed app-key set;
- safe-token validation with bounded length for app string values;
- short/full git SHA validation;
- stable reason-code pattern `^[A-Z][A-Z0-9_]{0,63}$`;
- path/private-value checks applied to `app` as well as `props`.

Do not raise from `validate_event`; invalid input still returns `None`.

- [ ] **Step 4: Run focused contract tests and confirm GREEN**

Run:
```bash
python -m pytest tests/test_measurement_contract_v1.py -q
```
Expected: PASS.

- [ ] **Step 5: Run existing match Measurement contract tests**

Run:
```bash
python -m pytest tests/test_measurement_match_query_v1.py -q
```
Expected: PASS before the intentional correlation assertions are changed in Task 3.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/measurement/contract.py tests/test_measurement_contract_v1.py
git commit -m "fix(measurement): harden envelope privacy validation"
```

---

### Task 2: Add the minimal diagnostics-oriented Measurement event contracts

**Files:**
- Modify: `src/measurement/contract.py`
- Modify: `src/measurement/emit.py`
- Create: `tests/test_measurement_diagnostics_events_v1.py`

**Interfaces:**
- Consumes: hardened `MeasurementEvent` / `validate_event()` from Task 1 and existing `MeasurementBus`.
- Produces:
  - `emit_workbench_session_finished(...) -> None`
  - `emit_rt_callback_stats(...) -> None`
  - `emit_process_failure(...) -> None`
  - supported event contracts for `workbench.session_finished`, `rt.callback_stats`, `process.failure`.

- [ ] **Step 1: Write failing event-contract tests**

Create tests covering exact V1 shapes:

`workbench.session_finished`
- domain `workbench`, privacy `export_safe`;
- props exactly `renderer`, `duration_ms_bucket`;
- renderer only `qml` or `tk`;
- duration bucket only `lt_1m`, `1m_5m`, `5m_15m`, `15m_60m`, `ge_60m`;
- non-null valid session ID required.

`rt.callback_stats`
- domain `rt`, privacy `export_safe`;
- props exactly `buffer_size`, `callback_mean_us`, `callback_p95_us`, `xrun_count`;
- buffer size is positive int, xrun count non-negative int;
- callback values are finite non-negative int/float and bool is rejected.

`process.failure`
- domain `eng`, privacy `export_safe`;
- `status` must be `error`;
- props exactly `component`;
- component is from the explicit allowlist: `startup`, `workbench`, `qml`, `python`, `native_audio`, `measurement`, `unknown`;
- non-null stable `reason_code` required.

All events must reject extra props, forbidden identifiers, private paths and wrong domains.

- [ ] **Step 2: Run the new tests and confirm RED**

Run:
```bash
python -m pytest tests/test_measurement_diagnostics_events_v1.py -q
```
Expected: FAIL because event names/contracts/emitters do not exist yet.

- [ ] **Step 3: Extend the Measurement catalog and validators**

In `src/measurement/contract.py`:
- add the three event names to `SUPPORTED_EVENT_NAMES`;
- add `workbench`, `rt`, `eng` to `SUPPORTED_DOMAINS`;
- add exact allowed-prop/value constants and event-specific validation branches matching Step 1;
- do not add speculative events from the larger ADR catalog.

- [ ] **Step 4: Add minimal fail-soft emit helpers**

In `src/measurement/emit.py`, add exact signatures:

```python
def emit_workbench_session_finished(
    *, bus: MeasurementBus, renderer: str, duration_ms_bucket: str,
    status: str = "ok", reason_code: Optional[str] = None,
    run_id: Optional[str] = None, session_id: Optional[str] = None,
    app: Optional[Mapping[str, Any]] = None,
) -> None: ...


def emit_rt_callback_stats(
    *, bus: MeasurementBus, buffer_size: int, callback_mean_us: float,
    callback_p95_us: float, xrun_count: int, status: str = "ok",
    reason_code: Optional[str] = None, run_id: Optional[str] = None,
    session_id: Optional[str] = None, app: Optional[Mapping[str, Any]] = None,
) -> None: ...


def emit_process_failure(
    *, bus: MeasurementBus, component: str, reason_code: str,
    run_id: Optional[str] = None, session_id: Optional[str] = None,
    app: Optional[Mapping[str, Any]] = None,
) -> None: ...
```

Use the existing timestamp/app defaults and `bus.emit()`/`flush()` pattern. `emit_process_failure` always emits `status="error"`. Do not wire any production call sites in this task.

- [ ] **Step 5: Run diagnostics-event and legacy Measurement tests**

Run:
```bash
python -m pytest tests/test_measurement_diagnostics_events_v1.py tests/test_measurement_contract_v1.py tests/test_measurement_match_query_v1.py tests/test_measurement_report_v1.py -q
```
Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/measurement/contract.py src/measurement/emit.py tests/test_measurement_diagnostics_events_v1.py
git commit -m "feat(measurement): add diagnostics event contracts"
```

---

### Task 3: Freeze Workbench correlation semantics without enabling Measurement

**Files:**
- Modify: `src/measurement/emit.py`
- Modify: `src/workbench_session.py`
- Modify: `tests/test_measurement_match_query_v1.py`

**Interfaces:**
- Consumes: existing Workbench composition and Match observer hook.
- Produces:
  - `WorkbenchSession.session_id: str` as the general Workbench-session authority;
  - compatibility property `WorkbenchSession.measurement_session_id -> str` returning the same ID;
  - `make_match_query_finished_observer(..., run_id: Optional[str] = None, session_id: Optional[str] = None)` that resolves one stable run ID per observer and reuses it for every query.

- [ ] **Step 1: Replace old correlation expectations with failing tests**

Update/add tests proving:
- `compose_workbench_session()` has a valid UUID-v4 `session.session_id` even when `SAMPLE_BRAIN_MEASUREMENT_MODE=off`;
- compatibility `session.measurement_session_id == session.session_id`;
- Measurement off still creates no sidecar DB and installs no match observer;
- Measurement local mode emits repeated match-query events with one shared `session_id` and one shared `run_id` for that observer/session;
- passing explicit `run_id` / `session_id` to `make_match_query_finished_observer` preserves those exact IDs;
- observer failure remains fail-soft.

Remove/replace the existing assertion that two match queries must have different `run_id` values.

- [ ] **Step 2: Run the correlation tests and confirm RED**

Run:
```bash
python -m pytest tests/test_measurement_match_query_v1.py -q
```
Expected: new stable-correlation assertions fail on current behavior.

- [ ] **Step 3: Implement one Workbench session authority**

In `src/workbench_session.py`:
- generate one UUID-v4 session ID during composition regardless of Measurement mode;
- store it as `WorkbenchSession.session_id`;
- preserve `measurement_session_id` only as a compatibility property/alias to the same value, not a separately generated authority;
- pass the explicit session ID into `make_match_query_finished_observer`.

Do not add runtime diagnostics writers or process-start hooks here.

- [ ] **Step 4: Fix observer run correlation**

In `src/measurement/emit.py`:
- add optional `run_id` argument to `make_match_query_finished_observer`;
- resolve one UUID-v4 `resolved_run_id` once when the observer is created;
- reuse that same value for all observer emissions;
- keep `session_id` stable and caller-injectable;
- when Measurement is `off`, return no observer and do not create a DB; the general Workbench session ID still comes from `WorkbenchSession`, not from sidecar creation.

This creates the injection seam for Slice 2 to supply the true process/diagnostic `run_id`; Slice 1 does not yet own process-start lifecycle.

- [ ] **Step 5: Run Workbench/Measurement focused regressions**

Run:
```bash
python -m pytest tests/test_measurement_match_query_v1.py tests/test_workbench_qml_runtime.py -q
```
Expected: PASS or only pre-existing environment-dependent skips documented by the repo; no new failures.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/measurement/emit.py src/workbench_session.py tests/test_measurement_match_query_v1.py
git commit -m "fix(workbench): stabilize diagnostics correlation ids"
```

---

### Task 4: Freeze Diagnostic Bundle V1 privacy/schema contract

**Files:**
- Create: `src/diagnostics_contract.py`
- Create: `tests/test_diagnostics_contract_v1.py`
- Create: `docs/RUNTIME_DIAGNOSTICS_CONTRACT_V1.md`
- Modify: `docs/adr/ADR-0006-measurement-contract-v1.md` only if needed to record implemented privacy hardening/correlation clarification without changing the accepted architecture.

**Interfaces:**
- Consumes: hardened Measurement privacy rules from Task 1.
- Produces:
  - `DIAGNOSTIC_BUNDLE_DOCUMENT_TYPE = "sample_brain.diagnostic_bundle"`
  - `DIAGNOSTIC_BUNDLE_SCHEMA_VERSION = "1.0.0"`
  - `validate_diagnostic_bundle(bundle: Mapping[str, Any]) -> bool`
  - normative Slice-1 contract doc for later writer/CLI/CI slices.

- [ ] **Step 1: Write failing bundle-contract tests**

Define one valid minimal bundle containing exactly:
- `document_type`, `schema_version`, `run_id`, nullable `session_id`;
- safe `app` provenance;
- `outcome` with integer `exit_code`, nullable stable `failure_class`, nullable stable `reason_code`;
- bounded `last_events` entries using only `seq`, `occurred_at`, `monotonic_ns`, `component`, `event`, `status`, `reason_code`;
- `qt_summary` with counts/codes only;
- `native_summary` with safe scalar counters only;
- `measurement_events` list.

Tests must reject recursively:
- Windows/UNC/Unix private absolute paths;
- forbidden identity keys (`sample_id`, `device_name`, `username`, `hostname`, etc.);
- secrets/tokens;
- raw `message`, `exception`, `traceback`, raw Qt message text;
- arbitrary extra top-level fields;
- malformed UUIDs/timestamps;
- unbounded/free-text reason/failure/component values;
- nested privacy leaks inside `last_events`, summaries and Measurement payloads.

- [ ] **Step 2: Run bundle tests and confirm RED**

Run:
```bash
python -m pytest tests/test_diagnostics_contract_v1.py -q
```
Expected: FAIL because the contract module does not exist.

- [ ] **Step 3: Implement pure no-I/O bundle validation**

Create `src/diagnostics_contract.py` with constants and `validate_diagnostic_bundle(...) -> bool` only. Keep it deterministic and side-effect free.

Requirements:
- exact top-level allowlist;
- bounded `last_events` length (freeze V1 maximum at 128 events);
- recursive deny-list/path scan;
- UUID/timestamp validation consistent with Measurement Task 1;
- only scalar/count/code summaries; no raw message text;
- embedded Measurement events must be mappings whose envelope can be reconstructed/revalidated through the hardened Measurement contract before inclusion;
- return `False` on malformed input; do not raise.

Do not implement bundle collection, serialization to disk, CLI, retention, Qt/native hooks or artifact upload.

- [ ] **Step 4: Write the normative Slice-1 contract document**

`docs/RUNTIME_DIAGNOSTICS_CONTRACT_V1.md` must freeze:
- four evidence planes and their boundaries;
- run/session correlation semantics;
- Measurement event subset delivered by #1242;
- Diagnostic Bundle V1 field table and maximum `last_events=128`;
- raw/private deny rules;
- `minimal` / `verbose` / `off` runtime diagnostics mode semantics as future runtime requirements, explicitly noting that mode implementation is **not** part of #1242;
- realtime no-I/O invariant;
- later-slice ownership for runtime writer, Qt/faulthandler, native snapshots, bundle CLI, CI artifacts and deep dumps.

Do not claim those later capabilities are implemented.

- [ ] **Step 5: Run contract/docs gates**

Run:
```bash
python -m pytest tests/test_diagnostics_contract_v1.py tests/test_measurement_contract_v1.py tests/test_measurement_diagnostics_events_v1.py tests/test_measurement_match_query_v1.py tests/test_measurement_report_v1.py -q
python tools/check_canon_drift.py
python -m ruff check src/measurement src/diagnostics_contract.py tests/test_measurement_contract_v1.py tests/test_measurement_diagnostics_events_v1.py tests/test_measurement_match_query_v1.py tests/test_diagnostics_contract_v1.py
```
Expected: all focused tests PASS, `CANON_DRIFT_CHECK: PASS`, Ruff PASS.

- [ ] **Step 6: Verify no realtime/runtime scope leak**

Inspect final diff and confirm no files under `native/`, QML runtime startup, `.github/workflows/`, CLI diagnostics commands, or runtime log writers were changed. Any such change is out of #1242 unless required to repair a directly caused regression and separately justified in the issue.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/diagnostics_contract.py tests/test_diagnostics_contract_v1.py docs/RUNTIME_DIAGNOSTICS_CONTRACT_V1.md docs/adr/ADR-0006-measurement-contract-v1.md
git commit -m "docs(diagnostics): freeze agent-safe evidence contract"
```

---

### Task 5: Final branch validation and handoff evidence

**Files:**
- No new product scope; only repair files already owned by Tasks 1–4 if validation exposes a regression.

**Interfaces:**
- Consumes: complete #1242 branch.
- Produces: review-ready PR evidence against #1242 acceptance.

- [ ] **Step 1: Run the full relevant core suite**

Run:
```bash
python -m pytest -q
```
Expected: full suite green apart from explicitly documented pre-existing environment/baseline failures; do not weaken tests to get green.

- [ ] **Step 2: Run static/canon/diff checks**

Run:
```bash
python -m ruff check .
python tools/check_canon_drift.py
git diff --check origin/main...HEAD
```
Expected: PASS.

- [ ] **Step 3: Review privacy and compatibility evidence**

Confirm from tests/diff:
- Measurement default remains `off`;
- existing stage/match event readers/reports still work;
- no catalog DB measurement tables were added;
- no external HTTP/telemetry dependency/import was added;
- Workbench has one session ID authority;
- repeated match queries reuse one observer `run_id`;
- bundle validation rejects nested private evidence;
- no native callback/runtime-writer/CI scope entered the slice.

- [ ] **Step 4: Open/update the PR for #1242**

PR body must include:
- exact base/head SHA;
- task/commit summary;
- focused test commands/results;
- full-suite result;
- Ruff/canon/diff results;
- explicit privacy/realtime scope statement;
- `Closes #1242` only when all acceptance criteria are actually satisfied.

- [ ] **Step 5: Stop at review gate**

Do not merge solely from worker self-report. Supervisor must inspect final diff, CI, comments/review threads and live GitHub state before merge.
