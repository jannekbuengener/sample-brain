# Gesture Pattern Core Composition R&D — Slice 6 (#680 / #893)

**Status:** Implemented — `READY_BINDING_PLAN_TO_PATTERN_CORE_VIABLE` (post-`TEST_FREEZE`).

**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680)
**Child:** [#893](https://github.com/jannekbuengener/sample-brain/issues/893)
**Dependencies (DONE):** [#827](https://github.com/jannekbuengener/sample-brain/issues/827), [#882](https://github.com/jannekbuengener/sample-brain/issues/882), [#886](https://github.com/jannekbuengener/sample-brain/issues/886), [#888](https://github.com/jannekbuengener/sample-brain/issues/888), [#891](https://github.com/jannekbuengener/sample-brain/issues/891)

## Goal

Freeze and prove the smallest pure **composition** seam that consumes a **ready**
`GesturePatternBindingPlan` plus an explicit caller `pattern_id` and creates the
existing Pattern-Core objects:

- `Channel`
- `Trigger`
- `Pattern`

without changing ranking, selection, timing, channel allocation, or Pattern-length
semantics, and without mutating a `ChannelRackState`.

```text
ready GesturePatternBindingPlan
  + explicit pattern_id: str
  → compose_gesture_pattern_core(...)
  → GesturePatternCoreComposition
       channels: tuple[Channel, ...]
       pattern: Pattern
```

## Dependency on #891

Authoritative planner: `src/gesture_pattern_binding.py`.

`GesturePatternBindingPlan` already owns:

- selected sample / planned user-channel ID / sample path (`PlannedGestureChannelBinding`)
- exact event quarter positions (`PlannedGestureEventBinding.quarter_position: Fraction`)
- explicit Pattern length (`pattern_length_quarters`)
- unresolved cluster IDs and `ready_for_pattern`

This slice **translates** a ready plan. It must not redo selection, ranking, timing
projection, channel allocation, or Pattern-length inference.

See `docs/GESTURE_PATTERN_BINDING_RND_SLICE5.md`.

## Live foundation (verified on `origin/main` @ `8a47fd22183fa54fa04189efbc41cfb314d60570`)

| Surface | Fact |
|---------|------|
| Binding plan `#891` | Frozen dataclasses; `ready_for_pattern = not unresolved_cluster_ids`; clusters come only from timing events |
| Pattern Core | `Channel` / `Trigger` / `Pattern`; Pattern sorts triggers by `(position, channel_id)`; exclusive-end bounds |
| Membership helper | `require_triggers_reference_known_channels(triggers, known_channel_ids=...)` |
| Channel Rack | `add_user_channel(sample_path=...)` seeds DEFAULT_ON 16th triggers — **forbidden** as composition seam |
| Concurrent PR | [#889](https://github.com/jannekbuengener/sample-brain/pull/889) Theme/QML only — do not touch those paths |

## Architecture boundary (hard)

| Domain | Authority |
|--------|-----------|
| Ranking / Top-N / selection | `#891` plan — consume only |
| Timing quarters / Pattern length | `#891` plan — preserve exactly |
| Channel IDs / sample paths | `#891` planned bindings — preserve exactly |
| Pattern identity | **explicit caller** `pattern_id: str` |
| Channel / Trigger / Pattern objects | existing `src/pattern_core.py` |
| Trigger membership | `require_triggers_reference_known_channels` |
| Channel Rack / DEFAULT_ON | out of scope; must not call |

This slice does **not** authorize:

- auto rank-1 / resolving unresolved clusters / partial Patterns
- reallocation via `allocate_user_channel_id`
- `channel_rack.add_user_channel` / DEFAULT_ON seeding
- Live Kit Kick/Snare/Hat / slot mapping
- Pattern-length derivation, quantization, swing, groove
- ChannelRackState merge / session persistence
- ranking, timing, catalog, or analysis recomputation
- QML / UI / microphone

## Ownership decision: dedicated pure composer

**Chosen:** `src/gesture_pattern_core_composition.py` (absent at `TEST_FREEZE`).

**Rejected for this slice:**

- Calling `channel_rack.add_user_channel` (DEFAULT_ON 16ths corrupt exact `#888`/`#891` events).
- Re-calling `plan_gesture_pattern_binding` / ranking / timing / catalog loaders.
- Inventing Pattern IDs (`screen2-main`, UUID, rack lookup).
- Building or mutating `ChannelRackState`.

## Public seam (smallest clear form)

Module: `src/gesture_pattern_core_composition.py` (absent at `TEST_FREEZE`).

```text
compose_gesture_pattern_core(
    plan: GesturePatternBindingPlan,
    *,
    pattern_id: str,
) -> GesturePatternCoreComposition
```

### Immutable result model

```text
GesturePatternCoreComposition (frozen)
  channels: tuple[Channel, ...]   # actual pattern_core.Channel
  pattern: Pattern                # actual pattern_core.Pattern
```

Composition result is a **delta**: only gesture-created Channels plus the gesture
Pattern. No existing rack channels are copied. Rack/session integration is a later
slice.

## Frozen decisions

### 1. Ready-plan gate

Composition is allowed only when:

- `plan` is a `GesturePatternBindingPlan`
- `plan.ready_for_pattern is True`
- `plan.unresolved_cluster_ids == ()`

Non-ready or unresolved plans fail closed. Spoofed `ready_for_pattern=True` with
non-empty unresolved IDs also fails closed.

`ready_for_pattern=True` is **not** a blind trust bypass: the composer must still
validate structural fields it consumes (plans are frozen dataclasses and can be
manually constructed).

Do not auto-select rank 1, resolve missing samples, discard unresolved clusters, or
create a partial Pattern.

### 2. Pattern ID authority

`pattern_id` is explicit caller input:

- must be a non-empty `str`
- no default `screen2-main`
- no random/UUID generation
- no rack/session lookup or hidden state

Existing `Pattern` constructor remains final authority for Pattern validation.

### 3. Channel construction

For each `PlannedGestureChannelBinding`, in plan order:

```text
Channel(
  channel_id = binding.channel_id,
  live_kit_group = None,
  live_kit_slot = None,
  sample_path = binding.sample_path,
)
```

Rules:

- preserve planned `channel_id` and `sample_path` exactly
- provenance stays `(None, None)`
- preserve `#891` channel-binding order (already deterministic by cluster ID)
- same path across clusters → separate Channels
- no drum-role / Live Kit mapping
- **must not** call `allocate_user_channel_id`

### 4. Trigger construction

For every `PlannedGestureEventBinding`, in plan event order:

```text
Trigger(
  channel_id = event.channel_id,
  position = event.quarter_position,
)
```

Rules:

- one plan event → one Trigger
- exact `Fraction` only; no quantization / snap / swing / groove
- no DEFAULT_ON, no extra/seed triggers, no dedupe
- no timing recomputation

### 5. Pattern construction

```text
Pattern(
  pattern_id = pattern_id,
  length_quarter_notes = plan.pattern_length_quarters,
  triggers = tuple(composed_triggers),
)
```

Preserve exact `#891` length. No source-duration / last-onset / next-beat / next-bar /
4-quarter / ChannelRack defaults. Pattern Core exclusive-end validation remains
authoritative (`0 <= position < length`).

### 6. Event order vs Pattern normalization

Composer must **not** reorder the plan.

Pattern Core normalizes trigger storage by `(position, channel_id)`.

For a **valid** `#891` ready plan whose event positions are **strictly increasing**,
Pattern normalization is semantically identical to plan event order. Composer
verifies that Pattern trigger order equals that valid plan order.

Fail closed on malformed ready plans whose event positions are not strictly
increasing — do not silently accept a reordered Pattern as success. Do not modify
Pattern Core.

Live evidence: `#888` requires strictly increasing source onsets, so projected
quarters from the real pipeline are strictly increasing. Artificial non-monotonic
`GestureTimingProjection` fixtures can still reach `#891`; the composer rejects those
as structurally unsafe for lossless Pattern translation.

### 7. Plan-integrity / graph validation (composer-side)

Channel bindings:

- each entry is `PlannedGestureChannelBinding`
- unique `cluster_id`, unique `channel_id`
- non-empty `channel_id` / `sample_path` strings

Event bindings:

- each entry is `PlannedGestureEventBinding`
- `cluster_id` exists among planned channels
- `channel_id` exists among planned channels
- event cluster maps to **that exact** planned `channel_id` (no cross-cluster pointing)
- `quarter_position` is exact `Fraction`
- position satisfies `0 <= position < plan.pattern_length_quarters`

Do **not** revalidate ranking evidence (`selected_rank`, distance, MFCC) unless needed
for object integrity. No re-ranking / confidence.

#### Orphan planned channels (DOCS_GATE decision)

**Fail closed.**

Live `#891` derives `timing_clusters` only from timing events and emits event
bindings for every event whose cluster is selected. Therefore a non-empty ready plan
produced by `#891` cannot contain a selected channel with zero events.

A manually constructed ready plan with an orphan planned channel must be rejected.
This is structural integrity, not a new musical rule.

#### Empty ready plan (DOCS_GATE decision)

**Preserve.**

Live `#891` permits `ready_for_pattern=True` with empty `channel_bindings` and
`event_bindings` when timing has zero events (no unresolved clusters). Pattern Core
permits an empty-trigger `Pattern` with positive length.

Composer behavior: zero Channels, empty Pattern triggers, explicit positive Pattern
length from the plan, and the caller `pattern_id`. This slice translates `#891`
readiness; it does not change it.

### 8. Trigger membership

After composition, call:

```text
require_triggers_reference_known_channels(
    composition.pattern.triggers,
    known_channel_ids=[c.channel_id for c in composition.channels],
)
```

Every Trigger must reference a Channel in the returned composition.

### 9. Composition delta boundary / Channel Rack hard boundary

Result contains **only** gesture-created Channels + the gesture Pattern.

Must **not**:

- import/call `add_user_channel`, `assign_user_channel_sample`,
  `reconcile_live_kit_sample_assignments`, `build_channel_rack_state`
- construct or mutate `ChannelRackState`
- seed DEFAULT_ON

For valid ready plans: `len(pattern.triggers) == len(plan.event_bindings)`.

### 10. No upstream recomputation

Composer must not call:

- `analyze_gesture_audio`
- `rank_gesture_library_candidates` / `rank_gesture_against_catalog`
- `load_gesture_library_candidates`
- `project_gesture_timing`
- `plan_gesture_pattern_binding`
- `allocate_user_channel_id`

It consumes the frozen plan only.

### 11. Immutability / determinism

Must not mutate the plan or nested bindings. Same valid plan + same `pattern_id` →
equal composition.

### 12. Import / ownership boundary

May import: dataclasses, fractions, typing/collections, `#891` plan types,
`pattern_core` (`Channel`, `Trigger`, `Pattern`, `require_triggers_reference_known_channels`).

Must **not** import/call Channel Rack mutation helpers or upstream ranking/timing/
catalog/analysis composition entry points listed above.

## Fail-closed validation matrix (summary)

| Condition | Result |
|-----------|--------|
| non-ready / unresolved / spoofed ready+unresolved | fail closed |
| empty / non-string `pattern_id` | fail closed |
| duplicate planned channel or cluster IDs | fail closed |
| empty sample_path / empty channel_id | fail closed |
| event unknown channel / cluster↔channel mismatch | fail closed |
| event non-Fraction position | fail closed |
| event `position >= length` (incl. `== length`) | fail closed |
| non-strictly-increasing event positions | fail closed |
| orphan planned channel (channel with zero events) | fail closed |
| empty ready plan (zero events/channels, ready) | compose empty delta |

## Quality / evidence boundary

| Label | Meaning |
|-------|---------|
| MEASURED | exact planned IDs/paths/Fractions/length copied into Pattern-Core objects |
| HEURISTIC | none introduced |
| NOT YET CLAIMED | Channel Rack/session integration, automatic sample choice, producer-quality matching, UI |

## R&D exit (after later implementation)

Exactly one of:

- `READY_BINDING_PLAN_TO_PATTERN_CORE_VIABLE`
- `PATTERN_CORE_COMPOSITION_CONTRACT_INSUFFICIENT`
- `INSUFFICIENT_EVIDENCE`

**Viable means only:** a ready `#891` binding plan can be translated deterministically
and losslessly into existing `Channel` / `Trigger` / `Pattern` objects without adding
new musical semantics.

It does **not** mean Channel Rack/session integration, automatic sample choice,
producer-quality matching, or UI are validated.

If viable, the next slice may define **explicit integration of this pure composition
into a target ChannelRack/session state** without changing the frozen R&D semantics.

Parent `#680` remains OPEN.

## Acceptance tests

See `tests/test_gesture_pattern_core_composition_893.py` (frozen at `TEST_FREEZE`).

## Non-goals

No auto sample choice, confidence calibration, selection UI, Pattern-length inference,
quantization/swing/groove, BPM inference, channel reallocation, Live Kit taxonomy,
ChannelRackState merge/replacement, Screen-2 mutation, session persistence, playback
scheduling, QML/UI/mic, Arrangement/Screen 3, DB/schema changes, `docs/CANON_INDEX.md`
churn, PR `#889` theme/QML paths.

## Concurrent work notice

PR `#889` (Theme/QML) was merged on `main` after `TEST_FREEZE` and integrated via
normal merge into this branch during `DRIFT_GATE`. This slice still must not own
Theme/QML paths:

- `docs/WORKBENCH_VISUAL_ACCEPTANCE.md`
- `docs/assets/themes/*`
- `src/workbench_qml.py`
- `src/workbench_theme.py`
- related Theme/QML tests

## Post-implementation result

| Field | Value |
|-------|-------|
| Implementation seam | `src/gesture_pattern_core_composition.py` — `compose_gesture_pattern_core(plan, *, pattern_id) -> GesturePatternCoreComposition` |
| Result model | frozen `GesturePatternCoreComposition(channels: tuple[Channel, ...], pattern: Pattern)` using real Pattern-Core types |
| Order invariant | explicit `ValueError` if `Pattern` normalization would change composed trigger order (no Python `assert`) |
| Focused validation | `tests/test_gesture_pattern_core_composition_893.py` — **52 passed** |
| Protected validation | `#891`/`#888`/`#882`/`#886`, Pattern Core, Channel Rack / DEFAULT_ON, sequencer playback/PCM — **319 passed** |
| Static / hygiene | `ruff check` PASS; `git diff --check` PASS; `python tools/check_canon_drift.py` PASS |
| R&D EXIT | `READY_BINDING_PLAN_TO_PATTERN_CORE_VIABLE` |
| Quality claim | `PATTERN_CORE_COMPOSITION_ONLY — RACK_SESSION_INTEGRATION_NOT_YET_VALIDATED` |

Viable here means only: a ready `#891` plan plus explicit `pattern_id` translates
deterministically and losslessly into existing `Channel` / `Trigger` / `Pattern`
objects with fail-closed structural validation, empty-ready preserved, orphan
planned channels rejected, and no Channel Rack mutation / DEFAULT_ON /
upstream recomputation.

Parent `#680` remains OPEN. Next contract slice (not this PR): explicit integration
of `GesturePatternCoreComposition` into a target ChannelRack/session.
