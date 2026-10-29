# Workbench Prepared Browsing Contract

**Status:** ACTIVE_SUPPORTING

**Issue:** #1202

**Scope:** Prepared Sample-Browser rows and regenerable waveform envelopes

## Ownership and identity

- The Workbench library database owns the optional `sample_waveform_artifacts`
  cache. Each artifact belongs to one `samples.id` row and is removed by the
  existing sample cascade.
- A hit requires the cached sample identity (`size_bytes`, `mtime_ns`), the
  renderer version, and the 96-point budget to match. Invalid JSON, non-finite
  values, values outside `0..1`, and oversized payloads are misses.
- A completed decode may be persisted only while the current library row still
  has the identity captured when the work was queued.
- Waveform artifacts are regenerable local metadata. They are not samples,
  recordings, analysis authority, or portable track-package content.

## Prepared navigation

- Library navigation reads existing database rows. It does not scan the source
  filesystem.
- A visible viewport is hydrated in one model projection from the touched
  memory cache and one bounded database lookup. Hits require no audio decode;
  misses keep the placeholder and enter asynchronous work.
- An empty Favorites set performs no per-row path resolution. A non-empty set
  is normalized once before row projection.
- Search, selection, and the existing virtualized QML list remain the owners of
  visible-row membership and interaction.

## Decode scheduling

- One decode worker owns a finite queue. `CURRENT_VISIBLE` work precedes
  `BACKGROUND_ENRICHMENT`; a queued background identity is promoted when it
  becomes visible.
- Each browser projection generation invalidates queued visible work from older
  generations. An in-flight decode may finish, but its captured sample identity
  controls cache use and persistence.
- Background enrichment begins only after the workspace browser is materialized,
  reads small ID-ordered database pages, and stops admitting new work while
  visible requests or native audition are active.
- The existing Tk path-based loader remains compatible. Streaming decode stays
  outside this slice unless measured memory or interaction pressure requires it.

## Lifecycle

- **Wave 1** materializes a usable Library/Browser from essential analysis and
  cached metadata. First usability must not wait on optional waveform
  enrichment.
- **Wave 2** is a separate bounded background enrichment phase that writes
  versioned `sample_waveform_artifacts` after Wave 1. Active Browser
  interaction, search/navigation, and native audition outrank Wave 2; the
  loader pauses new background admission while preview is active.

## Acceptance boundary

- Prepared publication is measured at 500, 2,200, and 5,000 rows; the 2,200-row
  p95 gate is 250 ms.
- Valid visible artifacts hydrate in at most 100 ms with zero decodes.
- At least 20 rapid scope changes must produce no starvation or wrong-row
  mutation. Browser and native-audition dispatch p95 remains at most 25 ms while
  enrichment is active.
- Intentional native Stop→Start under Wave-2 pressure must remain
  `SB_DEVICE_OK` (see closed #1267). Physical/audible device proof stays a
  separate runtime gate and is not claimed from snapshot evidence alone.
- #1206 (aggregate registered-source root) and #1209 (native Screen-1 audio
  baseline) are delivered acceptance dependencies. They do not authorize
  scanner, analyzer, audio-engine, or Browser redesign work inside this
  contract.
