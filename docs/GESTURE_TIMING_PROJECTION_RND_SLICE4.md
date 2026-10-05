# Gesture Timing Projection R&D — Slice 4 (#680 / #888)

**Status:** R&D contract frozen; implementation delivered. See post-implementation result.

**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680)
**Child:** [#888](https://github.com/jannekbuengener/sample-brain/issues/888)
**Dependencies (DONE):** [#827](https://github.com/jannekbuengener/sample-brain/issues/827), [#882](https://github.com/jannekbuengener/sample-brain/issues/882), [#886](https://github.com/jannekbuengener/sample-brain/issues/886)

## Goal

Freeze and prove the smallest deterministic projection from **source-relative gesture seconds** to **pattern-local quarter-note `Fraction` positions**, without creating `Pattern`, `Channel`, or `Trigger` objects.

```text
GestureAnalysis (onset_time_sec: float)
  + explicit reference_bpm
  → project_gesture_timing(...)
  → GestureTimingProjection
       events: ProjectedGestureEvent(source_onset_sec, quarter_position: Fraction, cluster_id)
       reference_bpm: Fraction
       projected_duration_quarters: Fraction
```

## Live foundation (verified on `origin/main` @ `ed6b93cd`)

| Surface | Fact |
|---------|------|
| Gesture | `src/gesture_analysis.py` — `GestureEvent.onset_time_sec: float` is measured source-relative seconds (`float(sample)/float(sr)`); events strictly increasing; statuses `ok \| empty \| too_short \| unreadable` |
| Pattern Core | `src/pattern_core.py` — `Trigger.position` requires `type(position) is Fraction` and `position >= 0` |
| TempoMap | `src/session_grid.py` — exact rational frame ↔ quarter-note; float→`Fraction` via `Fraction(str(value))`; constant-BPM algebra equals `seconds * bpm / 60` |
| Catalog / ranking | Slices 2–3 own retrieval only; timing authority unchanged |
| Concurrent #884 | MERGED @ `ed6b93cd`; this freeze still does **not** edit `docs/CANON_INDEX.md` |

## Architecture boundary (hard)

| Domain | Time authority |
|--------|----------------|
| Gesture (`onset_time_sec`) | measured source seconds |
| This projection (`quarter_position`) | exact quarter-note `Fraction` under caller `reference_bpm` |
| Pattern Core (`Trigger.position`) | exact quarter-note `Fraction` (consumes projection later) |
| TempoMap | session/engine frame ↔ quarter mapping (not source-clip authority here) |

This slice does **not** authorize:

- BPM inference / beat tracking / catalog or analyzed sample BPM
- hidden global / session / profile tempo reads
- quantization, swing, groove, grid snap, bar rounding
- Pattern / Channel / Trigger creation
- automatic Pattern length / bar-aligned loop length
- tempo changes inside one gesture clip
- session-anchor or absolute engine-frame scheduling
- QML / UI / microphone
- catalog or ranking changes
- a second musical-time representation competing with TempoMap / Pattern Core

## Ownership decision

**Chosen:** dedicated pure seam `src/gesture_timing_projection.py` (absent at `TEST_FREEZE`).

**Rejected for this slice:**

- Reconstructing sample/frame indices from float seconds then routing through `TempoMap` (Strategy B) — public Slice-1 contract exposes seconds, not sample indices; frame reconstruction would invent new rounding ownership without improving measured authority.
- Importing private `session_grid._as_fraction` — reuse the **rule**, not the private API.
- Binding to session transport / Workbench BPM — hidden tempo authority forbidden.

## Public seam (smallest clear form)

Module: `src/gesture_timing_projection.py` (absent at `TEST_FREEZE`).

```text
project_gesture_timing(
    analysis: GestureAnalysis,
    reference_bpm: int | float | str | Fraction,
) -> GestureTimingProjection
```

### Immutable result contract

```text
ProjectedGestureEvent (frozen)
  source_onset_sec: float          # preserved measured evidence
  quarter_position: Fraction       # type(x) is Fraction; unquantized
  cluster_id: int                  # unchanged from GestureEvent

GestureTimingProjection (frozen)
  events: tuple[ProjectedGestureEvent, ...]
  reference_bpm: Fraction          # coerced/validated authority used
  projected_duration_quarters: Fraction
```

- Preserve source event order.
- Preserve `cluster_id` (timing is per **event**, not per cluster).
- Do **not** copy DSP `feature_vector`s.
- Do **not** contain Pattern / Trigger / Channel.

## Frozen decisions

### 1. Reference BPM authority — explicit caller `reference_bpm`

- Preferred parameter name: `reference_bpm`.
- Meaning: the BPM context under which elapsed source seconds are interpreted as musical quarters.
- Allowed public numeric types (aligned with TempoMap): `int | float | str | Fraction`.
- If the gesture was performed to a session click, a **later** orchestration layer may pass session BPM. That orchestration is outside #888.
- The projector must **not** read: global config BPM, active session transport BPM, profile BPM, analyzed sample BPM, or TempoMap singleton/session state.

### 2. Origin — source `t=0` → quarter `0`

- Leading silence is preserved.
- No implicit first-onset normalization.
- Example at 120 BPM: onsets `0.25s, 0.75s` → `Fraction(1, 2), Fraction(3, 2)` — **not** `0, 1`.
- First-onset normalization may be a future **explicit** mode; not a hidden default.

### 3. Exact Fraction conversion — Strategy A (decimal-text rationalization)

Inspected candidates:

| Strategy | Rule | Decision |
|----------|------|----------|
| **A** | `Fraction(str(seconds)) * coerce(reference_bpm) / 60` | **Chosen** |
| B | Reconstruct sample/frame from `onset_time_sec * sample_rate`, then rational frame/`sample_rate` timing | Rejected for this slice |

**Frozen conversion:**

```text
# after validation (finite, in-range, types)
sec_f = Fraction(str(onset_time_sec))
bpm_f = coerce_reference_bpm(reference_bpm)
quarter = sec_f * bpm_f / Fraction(60, 1)
```

**`coerce_reference_bpm` / measured-seconds coercion rules** (public local helper; do not import private `_as_fraction`):

1. Reject `bool` **before** `int` (Python `bool` is an `int` subtype).
2. `Fraction` → keep as-is (then require `> 0`).
3. `int` (non-bool) → `Fraction(value, 1)`.
4. `str` → `Fraction(value)`.
5. `float` → require `math.isfinite(value)` **before** `Fraction(str(value))`; then `Fraction(str(value))`.
6. Else → fail closed (`TypeError`).
7. After coercion: BPM must be `> 0` (`ValueError` otherwise).

Same rule applies to measured seconds / duration floats: reject non-finite before `Fraction(str(...))`.

**Requirements met:**

- no unintentional binary-float bit noise into huge denominators (decimal text path)
- same inputs → identical `Fraction`
- canonical musical examples exact (`0.5s @ 120 → 1`, `0.25s @ 120 → 1/2`, `127.5` BPM exact)
- no cumulative rounding, iterative grid rounding, or hidden quantization

`sample_rate` is **not** an input to the conversion formula. It remains a structural analysis invariant: must be a positive `int` (non-bool) or fail closed. No silent repair.

### 4. Duration projection — evidence, not Pattern length

```text
projected_duration_quarters = convert(analysis.duration_sec, reference_bpm)
```

Uses the **same** conversion rule as event positions.

**Explicit:** `projected_duration_quarters` ≠ automatically approved `Pattern.length_quarter_notes`.

Later Pattern binding must decide among raw duration, bar-aligned duration, explicit user length, or another rule. #888 does not decide that.

### 5. Quantization — NONE

No nearest 1/16, beat, bar; no swing/groove/grid snap/bar rounding. Projected position represents source timing under the explicit BPM context. Quantization is a later product decision.

### 6. Analysis status

| Status / shape | Projection |
|----------------|------------|
| `ok` + events | project each event; project duration |
| `empty` / `too_short` / `unreadable` with no events | `events=()`; still project duration when duration validates |
| invented events | forbidden |
| inconsistent / malformed analysis | fail closed |

### 7. Event order

Slice 1 produces strictly monotonically increasing `onset_time_sec`.

**Freeze:** projector **requires** strictly increasing onsets and fails closed if violated. Do not silently reorder upstream truth.

### 8. Same-cluster events

Timing projection is per event. Three events with the same `cluster_id` remain three timing events. Ranking may be cluster-shared; timing is event-specific.

### 9. Tempo changes

Out of scope. One projection receives one reference tempo context. No in-clip tempo map, session anchor, or absolute engine frame. A later layer may map local quarters through session `TempoMap`.

## Fail-closed validation matrix

| Input | Reject when |
|-------|-------------|
| `reference_bpm` | `bool`; unsupported type; non-finite float; `<= 0` after coercion; NaN/Inf |
| `onset_time_sec` | negative; NaN/Inf; `> analysis.duration_sec` |
| `duration_sec` | negative; NaN/Inf |
| `sample_rate` | not a positive `int` (reject `bool`) |
| event order | not strictly monotonically increasing |
| analysis | malformed inconsistent object that violates the above |

Do not silently repair malformed analysis.

## TempoMap relationship

- Pattern Core / TempoMap remain authorities for their existing domains.
- For **constant** `reference_bpm`, projected quarters correspond to the same elapsed-time relation as `TempoMap.frame_to_quarter_note` when frames represent the same elapsed seconds (`q = t * bpm / 60`).
- Use TempoMap as a **compatibility oracle** in tests; do **not** require a `TempoMap` instance inside the projection path.
- Do not call `quarter_note_to_frame` in the projection path (frame rounding is not musical-quarter authority).

## Compatibility with Pattern Core

Projected `quarter_position` values must be directly passable to `Trigger(position=...)` without reinterpretation. This slice proves that in **TEST-ONLY** assertions; the projector itself must not create `Trigger` / `Pattern` / `Channel`.

## Quality / evidence boundary

| Label | Meaning |
|-------|---------|
| MEASURED | source onsets, coerced BPM, exact `Fraction` quarters, duration evidence |
| HEURISTIC | none introduced in this slice (no quantization / tempo inference) |
| NOT YET CLAIMED | musical quality, loop length, Pattern generation, producer-ready rhythm feel |

## R&D exit (after later implementation)

Exactly one of:

- `EXPLICIT_BPM_UNQUANTIZED_PROJECTION_VIABLE`
- `TIMING_PROJECTION_CONTRACT_INSUFFICIENT`
- `INSUFFICIENT_EVIDENCE`

**Viable means only:** source-relative measured timing can be projected deterministically and compatibly into Pattern-Core quarter-note coordinates under an explicit BPM context.

It does **not** mean BPM inference, quantization, loop length, Pattern generation, or musical quality are solved.

Parent `#680` stays OPEN.

Pattern-binding plan is Slice 5 (#891); see `docs/GESTURE_PATTERN_BINDING_RND_SLICE5.md`.

## Acceptance tests

See `tests/test_gesture_timing_projection_888.py` (frozen at `TEST_FREEZE`).

## Non-goals

No Pattern / Trigger / Channel creation in production; no cluster→channel allocation; no automatic Pattern length; no bar normalization; no BPM detection; no beat tracking; no quantization / swing / groove; no session/engine scheduling; no QML/UI/mic; no catalog/ranking changes; no new runtime dependency; no `docs/CANON_INDEX.md` edit in this freeze.

## Post-implementation result

| Field | Value |
|-------|-------|
| Implementation seam | `src/gesture_timing_projection.py` → `project_gesture_timing(analysis, reference_bpm) -> GestureTimingProjection` |
| Immutable models | `ProjectedGestureEvent`, `GestureTimingProjection` (`frozen=True`) |
| Fraction rule | Strategy A: `Fraction(str(seconds)) * coerce(reference_bpm) / 60` |
| Measured tests | Focused `tests/test_gesture_timing_projection_888.py`: **57 passed**; protected gesture/ranking/catalog/pattern/session_grid: **97 passed**; channel rack + sequencer playback: **52 passed** |
| R&D EXIT | `EXPLICIT_BPM_UNQUANTIZED_PROJECTION_VIABLE` |
| Quality claim | `TIMING_PROJECTION_ONLY — PATTERN_GENERATION_NOT_YET_VALIDATED` |
| Limitation boundary | No BPM inference, no quantization, no Pattern/Channel/Trigger creation, no Pattern length authority; parent `#680` remains OPEN |
