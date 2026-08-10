# StructureV1 Boundary Backend

StructureV1 detects neutral, bar-synchronous section boundaries for Track Map
v1. It consumes canonical mono working audio, the authoritative
`AudioTimebase`, and the #236 `BeatGridResult`. It does not classify
arrangement roles and does not emit role or boundary-event labels.

## Input and bar grid

Sample indices are authoritative. Seconds are derived only through
`AudioTimebase`. A normal run requires at least two valid downbeats and makes
half-open bar ranges from their sample indices. The final track tail is kept
inside the final section but is not presented as an invented downbeat.

`bar_grid_policy="require_downbeats"` is the default and returns
`no_result/DOWNBEATS_UNAVAILABLE` when downbeats are absent. The explicit
`infer_4_4_from_beats` policy may group valid beats in fours from the first
beat; its result is always marked partial and records the assumption in
provenance.

## Signals and normalization

For every bar the backend computes RMS energy, low-end share, onset density,
rhythm stability, MFCC-like timbre descriptors, and spectral descriptors.
It derives self-similarity, recurrence, novelty, neighboring-bar deltas, and
4/8/16-bar trends from those bar features.

All scoring is deterministic and relative to the current track: robust
median/MAD z-scores, per-track percentiles, relative shares, and local
deltas. Constant or unavailable signals are marked non-informative rather
than converted into a fabricated confidence.

## Output and Track Map wiring

`StructureV1Result` retains sample-accurate `StructureBoundary` and
`StructureSection` values with bar assignment. `to_track_map_sections()`
exports the compatible neutral `analysis.timeline.sections` block using
derived seconds. `StructureV1Source.as_track_map_component()` is inserted as
`provenance.components.structure_v1` by a future Track Map assembler (#233).

The output status is `ok`, `partial`, `no_result`, or `failed`. Missing
optional feature groups create an explicit partial note; an invalid BeatGrid
fails closed and emits no boundaries. A run without any supported candidate
is a successful `no_result`, not an invented boundary.

## Boundary combination

The backend combines local novelty, normalized energy/low-end/onset/timbre/
spectral deltas, similarity/recurrence change, neighbor deltas, and multi-bar
trends. A candidate must be a local maximum above the configured per-track
score percentile, meet the configured bar spacing, and have at least two
independent contributing signal groups.

## Scope boundary

StructureV1 never decides `intro`, `groove`, `build`, `drop`, `breakdown`,
`outro`, `unknown`, `transition`, or `drop_onset`. Those terms and any
arrangement-role scoring remain exclusively in #240.
