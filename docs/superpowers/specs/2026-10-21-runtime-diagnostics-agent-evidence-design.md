# Runtime Diagnostics + Agent Evidence — Design

**Date:** 2026-10-21
**Status:** PROPOSED / USER REVIEW REQUIRED BEFORE IMPLEMENTATION
**Issue:** #1241
**First implementation slice:** #1242
**Base:** `main` @ `45ca8b7c8a3d8fe24cf4258984b79e1ad31f4975`

## 1. Intent

Sample Brain needs stronger runtime evidence so humans and coding agents can diagnose failures from reproducible facts instead of symptoms, without requiring the owner to manually collect or interpret logs.

The design must stay:

- local-first and offline-first;
- privacy-conservative;
- compatible with ADR-0006 Measurement;
- safe for realtime audio;
- deterministic and automation-friendly;
- fail-soft;
- useful across QML, Python, native audio, Windows runtime and CI;
- explicit about which evidence may cross the worker/agent boundary.

This is an engineering diagnostics foundation, not product analytics and not authorization for external telemetry.

## 2. Existing live architecture to reuse

### 2.1 Measurement is already the safe structured-event authority

ADR-0006 already defines a provider-neutral Measurement layer with:

- `MeasurementEvent` envelope;
- privacy classes;
- fail-soft `MeasurementBus`;
- local `SidecarSqliteSink`;
- read-only `MeasurementReader`;
- local reporting;
- explicit opt-in modes (`off`, `local`, `local+export`);
- user-local sidecar storage outside the repo;
- hard privacy deny-list rules.

Current implementation enables only a subset of the ADR event catalog, notably `pipeline.stage_finished` and `match.query_finished`.

The ADR already anticipates event families useful to diagnostics, including `workbench.session_finished`, `rt.callback_stats`, `process.failure` and engineering/runtime events.

Therefore this design **extends Measurement; it does not replace it**.

### 2.2 Workbench already has a measurement session seam, but it is not yet a general session authority

`WorkbenchSession` currently carries `measurement_session_id`, and Harmonic Match measurement uses it when Measurement is enabled.

Live code also shows an important limitation: when Measurement mode is `off`, `make_match_query_finished_observer()` returns `(None, None)`, so `measurement_session_id` is absent. Diagnostics must still correlate a normal Workbench session while Measurement remains at its required default `off`.

Therefore the implementation must converge on **one general Workbench session correlation ID that exists independently of Measurement mode**, then pass/reuse that same ID for Measurement when Measurement is enabled. Do not create one diagnostics session ID plus a second measurement session ID.

Compatibility may preserve `measurement_session_id` temporarily as an alias/projection if needed, but the long-term authority is a general session correlation ID owned by `WorkbenchSession`.

### 2.3 Current Measurement run correlation needs reconciliation

ADR-0006 defines `run_id` as one invocation/run identity. Current `make_match_query_finished_observer()` generates a new `run_id` for each observed match query. That is valid as local uniqueness but does not provide the cross-event process/run correlation needed by diagnostics.

The diagnostics foundation must therefore freeze and later propagate one process/run correlation ID across related Workbench Measurement events without breaking existing event readers unnecessarily.

### 2.4 Native audio already owns rich snapshot evidence

The current native audio snapshot exposes safe diagnostic scalars including:

- engine frame/running/sample-rate/buffer frames;
- device status and recovery state;
- active/total voice counts and voice state arrays;
- requested/actual start frame and skew;
- sync/key-lock/latency/compensation fields;
- callback mean/p95/p99/p99.9/max;
- underflow/overflow/xrun counters;
- recording dropped frames/active state.

This remains the native runtime evidence authority. Diagnostics consume/project it from non-RT code; diagnostics do not create another engine truth.

### 2.5 Windows test harness already establishes useful crash/run evidence

The current Windows harness already records:

- exact commit;
- interpreter information;
- isolated test root/basetemp;
- `PYTHONFAULTHANDLER=1`;
- stdout/stderr suite log;
- exit code;
- explicit separation of assertions, process exit and native diagnostics.

The new design should generalize this discipline into the product/runtime path rather than creating an unrelated harness model.

## 3. Design choice

Use **four explicitly separated evidence planes**.

```text
                   product/runtime execution
                           |
              +------------+------------+
              |                         |
      Safe structured facts       Raw local diagnostics
       (ADR-0006 Measurement)      (operator/private only)
              |                         |
              +------------+------------+
                           |
                   Sanitizer / projector
                           |
                Diagnostic Bundle V1
                 (agent / CI safe)
                           |
                  GitHub log/artifact

        Deep native dump tools remain explicit/local only
```

This separation is the central architectural rule.

## 4. Evidence plane A — Measurement

Measurement remains the only provider-neutral structured-event authority.

### 4.1 Purpose

Measurement answers safe factual questions over time:

- did a session finish successfully;
- did a process fail in component class X;
- what were callback/xrun counters;
- how long did a bounded operation take;
- what renderer/runtime class was involved.

### 4.2 Payload rule

Measurement stores only allowlisted, typed technical facts:

- enums;
- booleans;
- integer/float counters;
- durations/buckets;
- version/provenance identifiers safe under ADR-0006.

It must not contain:

- arbitrary free text;
- exception messages;
- tracebacks;
- paths;
- filenames/sample names;
- library roots;
- device names/IDs;
- query/prompt text;
- DB content;
- credentials/secrets;
- raw audio/waveform/embeddings.

### 4.3 Privacy hardening gap proven by self-review

The existing validator is strict for `props`, but currently validates `app` only as a generic mapping and `reason_code` only as `str | None`.

ADR-0006 itself calls for strict allow-lists to prevent path leakage through `reason_code`; the implementation has not yet fully enforced that rule.

Before Measurement events are used as normal agent/CI evidence, Slice #1242 must close this gap:

- define an allowlisted `app` schema/keys and safe value constraints;
- reject private-path/identity leakage in `app` values;
- make `reason_code` a stable machine code contract rather than arbitrary free text;
- apply length/character and preferably event-specific allowlist constraints where practical;
- keep existing valid Measurement events backward-compatible.

The sanitized bundle must never assume an event is safe merely because it came from the Measurement table; events are revalidated against the hardened contract before inclusion.

### 4.4 First event extensions

Slice #1242 should evaluate and implement the smallest immediately useful subset, preferably:

#### `workbench.session_finished`

- domain: `workbench`
- privacy: `export_safe`
- props: renderer + bounded duration representation only
- status/reason remain envelope fields

#### `rt.callback_stats`

- domain: `rt`
- privacy: `export_safe`
- props: buffer size, callback latency scalar(s), xrun/underflow/overflow counts
- never device identity or sample/voice identity

#### `process.failure`

- domain: ADR-consistent engineering/runtime domain
- privacy: `export_safe`
- props: allowlisted component only
- stable reason code in envelope
- no message/exception/traceback

If ADR reconciliation shows that a smaller first subset is cleaner, choose smaller scope. Do not add events speculatively.

## 5. Evidence plane B — Private Runtime Diagnostics

### 5.1 Purpose

This plane is for data that is genuinely useful for debugging but cannot safely enter Measurement.

Examples:

- Python faulthandler text;
- raw Qt messages;
- raw exception/trace context;
- bounded runtime event timeline before sanitization;
- operator-only local crash context.

### 5.2 Storage

Windows default target:

```text
%LOCALAPPDATA%/SampleBrain/diagnostics/<run_id>/
  meta.json
  runtime.jsonl
  python-fault.log
  qt.log
  exit.json
```

The precise directory helper should follow existing LocalAppData/XDG conventions and remain outside the repo.

### 5.3 Raw-data boundary

Raw diagnostics are:

- local-only;
- private/operator evidence;
- ignored/untracked;
- never automatically committed;
- never automatically uploaded to CI;
- never automatically injected into worker prompts;
- never written into Measurement DB;
- never promoted to curated `evidence/` without deliberate review/sanitization.

### 5.4 Retention

Runtime diagnostics must be bounded. Later implementation must choose deterministic retention by age/count/size. Unbounded append-only log growth is not acceptable.

### 5.5 Runtime diagnostics mode

Runtime diagnostics are separate from ADR-0006 Measurement mode.

Recommended producer behavior:

- `minimal` — default for the production Workbench: bounded local run provenance, high-value lifecycle/failure boundaries, faulthandler target, and warning/critical-class capture needed to make crashes diagnosable without owner setup;
- `verbose` — explicit opt-in for denser operator diagnostics, additional safe operation boundaries and optional low-frequency native snapshot sampling;
- `off` — explicit opt-out of the new local runtime diagnostics layer.

`minimal` remains local-only, bounded and fail-soft. It does not enable Measurement, external export or raw dump upload. The exact environment/profile key and retention limits belong to the runtime implementation slice.

## 6. Evidence plane C — Sanitized Diagnostic Bundle V1

### 6.1 Purpose

The bundle is the **only normal worker/agent evidence boundary**.

It converts private/raw diagnostics plus revalidated safe Measurement events into deterministic, privacy-gated evidence that CI, ChatGPT, Jules, Codex or another worker can inspect without exposing private local runtime state.

### 6.2 Document contract

Suggested identity:

```text
document_type = sample_brain.diagnostic_bundle
schema_version = 1.0.0
```

Minimum logical shape:

```json
{
  "document_type": "sample_brain.diagnostic_bundle",
  "schema_version": "1.0.0",
  "run_id": "uuid",
  "session_id": "uuid-or-null",
  "app": {
    "git_sha": "safe-sha",
    "app_version": "...",
    "python_version": "...",
    "qt_version": "...",
    "renderer": "qml",
    "platform": "windows"
  },
  "outcome": {
    "exit_code": 0,
    "failure_class": null,
    "reason_code": null
  },
  "last_events": [],
  "qt_summary": {},
  "native_summary": {},
  "measurement_events": []
}
```

Exact field names are frozen in #1242; this design freezes the architectural responsibilities.

### 6.3 Bundle privacy rule

The bundle must reject or strip:

- absolute/private paths;
- usernames/host/machine identity;
- sample/audio names or paths;
- library roots;
- stable device names/IDs;
- query/prompt text;
- DB/index/cache content or identities;
- secrets/credentials/tokens;
- raw exception strings/traces;
- raw Qt messages by default;
- raw native memory dumps.

Safe Qt content should normally be counts and stable classification codes, not arbitrary text.

### 6.4 Bounded timeline

`last_events` should contain only a bounded final window, e.g. the last N sanitized events. The exact N is implementation detail, but the contract must prevent unbounded bundle size.

## 7. Evidence plane D — Deep native crash tools

Windows minidumps/WER LocalDumps/PageHeap/ASan-family tooling is valuable for specific memory defects but is **not normal telemetry**.

Rules:

- explicit diagnostic mode only;
- raw dumps remain local/private by default;
- no automatic upload;
- no automatic worker context;
- sanitizer may project safe crash classification/provenance into a bundle, never arbitrary memory contents.

This plane is later work and not part of Slice #1242.

## 8. Correlation contract

### 8.1 IDs

- `run_id`: UUID v4 per process/diagnostic run, generated independently of Measurement enablement.
- `session_id`: UUID v4 per Workbench session, generated independently of Measurement enablement.

Both fields must be structurally validated as UUIDs at persistence/export boundaries; arbitrary non-empty strings are insufficient for an agent-readable evidence contract.

The same `session_id` is reused by Measurement when Measurement is active. A measurement-specific alias may remain temporarily for compatibility, but there must not be two independently generated Workbench session identities.

The same `run_id` should correlate related Workbench events for one process/run. Current per-match-query `run_id` generation is an implementation gap to reconcile rather than a contract to preserve.

### 8.2 Event order

Private runtime diagnostics use:

- `seq`: monotonically increasing integer per run;
- `occurred_at`: UTC wall time for human correlation;
- `monotonic_ns`: monotonic ordering/duration clock.

Persisted/exported `occurred_at` must be validated as a real UTC ISO-8601 timestamp rather than accepted as arbitrary non-empty text.

Measurement keeps the ADR-0006 envelope unless a narrowly justified compatible change is needed. Raw-diagnostics-only fields do not justify a breaking Measurement schema bump.

### 8.3 Vocabulary

Use stable, code-like fields:

- `component`
- dotted `event`
- `status`
- `reason_code`

Avoid free-text as machine contract.

## 9. QML / Python integration design

The production QML startup already exposes a clean sequence:

```text
QGuiApplication
→ QQmlApplicationEngine
→ context properties
→ engine.loadData(...)
→ rootObjects()
→ window placement/show
→ app.exec()
```

Later runtime diagnostics should instrument lifecycle boundaries around this flow without moving state authority into QML.

### 9.1 Qt message capture

A process-level Qt message handler may capture Qt/QML diagnostics when diagnostics are enabled.

Constraints:

- install before QML load;
- remove/close deterministically on teardown;
- keep handler reentrant and minimal;
- avoid complex blocking persistence from the Qt callback itself;
- queue/project from safe control code where practical.

### 9.2 Early startup

The Windows distributable entry point should begin diagnostic run setup before importing the production QML module, so import/QML/native startup failures can still produce provenance/fault evidence.

## 10. Native audio integration design

### 10.1 Reuse snapshot authority

Native diagnostics consume `NativeAudioEngine.snapshot()` and existing native counters.

### 10.2 Safe checkpoints

Good later checkpoints include:

- engine open/start/stop/close;
- device-state transition;
- voice start/stop at control boundary;
- failure/recovery transition;
- optional low-frequency diagnostic sampling when explicitly enabled.

### 10.3 Realtime hard boundary

Never perform from the realtime callback:

- file writes;
- SQLite access;
- JSON serialization;
- Python logging callbacks;
- network/export;
- blocking locks/synchronization;
- allocation-heavy diagnostic work.

Existing atomics/snapshots are preferred. If future fidelity requires more event detail, use a bounded RT-safe ring buffer drained by non-RT control code; that is later scope and requires separate evidence.

## 11. CLI / operator surface

Target later commands:

```text
sample-brain diagnostics status
sample-brain diagnostics bundle --latest
sample-brain diagnostics bundle --run <run_id>
```

Requirements:

- deterministic;
- read-only over source evidence;
- privacy-safe;
- machine-readable mode available;
- useful without network access;
- no requirement for the owner to find files manually.

## 12. CI integration design

Relevant Windows/native/Workbench jobs should eventually follow:

```text
build/test/repro
      |
      +--> always create sanitized diagnostic summary
      |
      +--> print concise safe summary in Actions log
      |
      +--> upload safe diagnostic bundle artifact
```

Do not automatically upload raw local diagnostics or native dumps.

This allows connected GitHub tooling/workers to inspect failures directly from workflow logs/artifacts.

## 13. Failure behavior

Diagnostics and Measurement remain fail-soft:

- writer/sink/handler failure must not turn successful product work into failure;
- invalid unsafe events are dropped/rejected;
- diagnostic teardown must not mask the original failure;
- explicit diagnostics CLI failures may report their own error normally.

## 14. Privacy and artifact policy

The design preserves current policy:

- Measurement sidecar remains local runtime state outside repo;
- raw diagnostics remain local runtime state outside repo;
- curated `evidence/` remains intentionally reviewed public evidence only;
- worker/CI boundary uses only the sanitized bundle;
- no external telemetry/crash-reporting SDK is added to core.

## 15. Delivery slices

### Slice 1 — #1242: Contract + safe Measurement extensions

Freeze:

- run/session correlation semantics independent of Measurement enablement;
- current per-event `run_id` drift and compatibility path;
- safe event catalog subset;
- hardened `app` and `reason_code` privacy validation;
- bundle V1 contract;
- privacy deny rules;
- raw/private boundary;
- realtime no-I/O rule.

Implement only minimal safe Measurement extensions, privacy hardening and focused tests. A small Workbench-session correlation helper/field change is allowed only if required to establish the single session authority; do not add QML/native runtime instrumentation yet.

### Slice 2 — Workbench runtime diagnostics

Implement:

- local diagnostic run lifecycle/path/retention;
- early producer startup integration;
- faulthandler capture;
- bounded JSONL writer;
- Qt message capture;
- selected QML/Workbench lifecycle events;
- propagation of the frozen run/session correlation through production runtime seams.

### Slice 3 — Native snapshot diagnostics

Implement non-RT projection of existing native snapshots/counter deltas.

### Slice 4 — Bundle + CLI

Implement sanitizer, deterministic bundle builder and diagnostics CLI.

### Slice 5 — CI evidence automation

Integrate safe summary/artifact generation into relevant GitHub Actions jobs.

### Later — explicit deep native crash diagnostics

Add targeted dump tooling only when a concrete native defect needs it.

## 16. Alternatives considered

### A. Add more Python logging everywhere

Rejected as primary architecture.

Pros:
- cheap;
- familiar.

Cons:
- weak schema/correlation;
- privacy leakage risk;
- poor native/CI contract;
- hard for agents to consume deterministically;
- duplicates Measurement semantics.

Useful only as an implementation detail inside private runtime diagnostics.

### B. Put all diagnostics into Measurement SQLite

Rejected.

Pros:
- one store;
- existing reader/report tooling.

Cons:
- violates the intentional privacy shape of ADR-0006;
- encourages exception/path/raw-message leakage;
- mixes product-safe measurement with operator-only debugging evidence.

### C. External observability provider

Rejected for core.

Pros:
- mature dashboards/crash tooling.

Cons:
- conflicts with local/offline-first architecture;
- privacy/network/account coupling;
- unnecessary for current engineering objective.

External export remains optional and separately governed by ADR-0006 only.

### D. Chosen: split safe Measurement, private diagnostics, sanitized bundle

Chosen because it:

- reuses existing infrastructure;
- preserves privacy contracts;
- gives agents deterministic evidence;
- keeps raw crash context available locally;
- avoids realtime hazards;
- supports CI without exposing private state.

## 17. Acceptance for the architecture

The architecture is delivered when:

- ADR-0006 remains sole Measurement authority;
- raw private diagnostics are separate from Measurement;
- run/session correlation is deterministic and available even when Measurement is off;
- `app` and `reason_code` cannot bypass privacy rules;
- QML/Python/native lifecycle can be reconstructed from bounded evidence;
- no realtime callback diagnostic I/O exists;
- sanitized bundle has a frozen privacy-tested V1 contract;
- workers can consume CI-safe evidence without owner log collection;
- raw dumps/private logs never upload automatically;
- local retention is bounded;
- diagnostics remain fail-soft;
- no external telemetry dependency is introduced.

## 18. Explicit non-scope

- SaaS analytics/crash phone-home;
- Mixpanel/Sentry SDK in core;
- user clickstream analytics;
- continuous profiling;
- analyzer semantic changes;
- new audio/transport authority;
- committing local logs/dumps/private DBs;
- automatically exposing raw local logs to agents.

## 19. Implementation gate

This document is the architectural design artifact for #1241.

Per the repository development workflow, implementation planning for #1242 starts only after the user reviews and approves this written spec.
