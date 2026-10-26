# Runtime Diagnostics Contract V1

## Status and scope

This document freezes the privacy and schema boundary delivered by issue #1242.
The delivered code is a deterministic, side-effect-free validator. It does not
collect diagnostics, write files, install runtime hooks, expose a CLI, retain
artifacts, or upload evidence.

ADR-0006 remains the authority for Measurement. This contract consumes that
event contract; it does not replace it.

## Evidence planes

Runtime evidence is separated into four planes:

1. **Measurement** contains stable, structured, privacy-classified product and
   engineering events. Only events that pass the Measurement validator and are
   classified `export_safe` may enter a Diagnostic Bundle.
2. **Private local diagnostics** may later contain bounded raw runtime details
   needed for local diagnosis. They stay outside the repository, are not
   Measurement events, and are not an automatic worker or CI input.
3. **Sanitized Diagnostic Bundle V1** is the normal agent/CI-safe evidence
   boundary. It contains only the exact allowlisted schema below.
4. **Deep native crash tools** include dumps and memory-oriented tooling. They
   are explicit, local, exceptional diagnostics and are never normal telemetry
   or automatic bundle content.

No data moves from a more private plane to a less private plane merely because
it was collected successfully. Projection across a boundary requires explicit
sanitization and validation.

## Correlation

- `run_id` is a canonical lowercase, hyphenated RFC-4122 UUID v4 for one
  related process/run.
- `session_id` is either `null` or a canonical UUID v4 for one Workbench
  session.
- A composed Workbench session owns one stable `session_id`, including when
  Measurement is disabled. `measurement_session_id` is only a compatibility
  alias for that same identity.
- One composed Measurement observer reuses one `run_id` for its related events.
- Embedded Measurement events retain their own validated run/session fields;
  Bundle V1 does not silently rewrite them.

## Measurement subset delivered by #1242

The existing ADR-0006 events remain compatible. The following additive,
`export_safe` event contracts are available for later runtime instrumentation:

| Event | Domain | Required semantics |
| --- | --- | --- |
| `workbench.session_finished` | `workbench` | non-null session; exact props `renderer`, `duration_ms_bucket` |
| `rt.callback_stats` | `rt` | exact bounded scalar props `buffer_size`, callback mean/p95, `xrun_count` |
| `process.failure` | `eng` | status `error`; stable reason; allowlisted component |

Their fail-soft emitters are contract surfaces only. Issue #1242 adds no new
runtime call sites.

## Diagnostic Bundle V1

The document identity is:

```text
document_type = sample_brain.diagnostic_bundle
schema_version = 1.0.0
```

The top-level object contains exactly these required fields:

| Field | V1 contract |
| --- | --- |
| `document_type` | Exact value above |
| `schema_version` | Exact value above |
| `run_id` | Canonical UUID v4 |
| `session_id` | Canonical UUID v4 or `null` |
| `app` | Exact safe provenance object |
| `outcome` | Exact typed outcome object |
| `last_events` | Ordered list of at most 128 sanitized events |
| `qt_summary` | Counts and stable codes only; `{}` is valid |
| `native_summary` | Safe scalar counters only; `{}` is valid |
| `measurement_events` | Revalidated `export_safe` Measurement mappings |

### `app`

The object contains exactly `app_version`, `git_sha`, `python_version`,
`qt_version`, `renderer`, and `platform`. Versions are bounded safe tokens;
`git_sha` is `null` or 7-40 hexadecimal characters; `qt_version` may be `null`;
renderer is `qml` or `tk`; platform is `windows`, `macos`, or `linux`.

### `outcome`

The object contains exactly integer `exit_code`, nullable stable machine code
`failure_class`, and nullable stable machine code `reason_code`. Boolean exit
codes and free text are invalid.

### `last_events`

Each entry contains exactly `seq`, `occurred_at`, `monotonic_ns`, `component`,
`event`, `status`, and nullable `reason_code`.

- `seq` and `monotonic_ns` are non-negative integers; booleans are invalid.
- Sequence numbers strictly increase; monotonic clocks do not decrease.
- `occurred_at` is a real UTC timestamp with exactly millisecond precision and
  a `Z` suffix, matching Measurement semantics.
- Components, statuses, event names, and reasons use bounded machine
  vocabularies rather than free text.
- The frozen V1 maximum is **128 entries**. Empty is valid.

### `qt_summary`

The only permitted fields are `debug_count`, `info_count`, `warning_count`,
`critical_count`, `fatal_count`, and `codes`. Counts are non-negative integers.
`codes` is a list of at most 128 stable machine codes. Individual fields are
optional; arbitrary Qt message text is not permitted.

### `native_summary`

The only permitted fields are `buffer_size`, `callback_mean_us`,
`callback_p95_us`, `xrun_count`, `underflow_count`, `overflow_count`,
`active_voice_count`, `total_voice_count`, and `running`. Counts are
non-negative integers, buffer size is positive, timings are finite and
non-negative, and `running` is boolean. Individual fields are optional. Device
identity and raw native data are not permitted.

### `measurement_events`

Every entry must have exactly the Measurement Event V1 envelope fields. The
mapping is reconstructed as a `MeasurementEvent`, validated through the
hardened ADR-0006 contract, and accepted only when its privacy class is
`export_safe`. Origin in a Measurement store is never sufficient by itself.

## Privacy deny rules

Validation fails closed for forbidden content at any nesting depth, including:

- Windows, UNC, and private Unix absolute paths;
- usernames, hostnames, machine identifiers, and device names/IDs;
- sample/audio names, paths, IDs, library roots, and content identities;
- query or prompt text and DB/index/cache identities;
- secrets, credentials, passwords, API keys, and tokens;
- raw messages, exceptions, tracebacks, and Qt text;
- raw audio, waveform, embedding, dump, or memory content;
- unknown fields, unsupported objects, non-finite numbers, and recursive
  containers.

The validator returns `False` for malformed input and does not raise.

## Future runtime modes

Later runtime work must support these semantics:

- `off`: no runtime diagnostics collection or writer activity.
- `minimal`: bounded safe classifications, counters, correlation, and outcome
  data sufficient to produce the V1 bundle.
- `verbose`: additional bounded private local evidence, still subject to the
  same export boundary before it can enter a bundle.

These modes are requirements for later slices. Their configuration and runtime
implementation are **not part of #1242**.

## Realtime invariant

The hard realtime callback performs no file, database, console, network,
allocation-heavy, lock-contended, or bundle serialization work. Later native
instrumentation may update bounded preallocated atomic/scalar state; collection
and sanitization must happen off the callback thread.

## Deferred ownership

Later scoped slices own:

- bounded local runtime writers and retention;
- Qt message and Python faulthandler integration;
- native audio snapshot collection;
- deterministic bundle construction and diagnostics CLI commands;
- CI-safe artifact generation/upload;
- opt-in deep native crash capture.

This V1 contract does not claim any of those capabilities are implemented.
