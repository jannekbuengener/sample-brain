# Gesture Rack/Session Integration Plan R&D — Slice 7 (#680 / #899)

**Status:** Implemented — `EXPLICIT_RACK_REPLACEMENT_PLAN_VIABLE` (post-`TEST_FREEZE`).

**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680)
**Child:** [#899](https://github.com/jannekbuengener/sample-brain/issues/899)
**Dependencies (DONE):** [#827](https://github.com/jannekbuengener/sample-brain/issues/827), [#882](https://github.com/jannekbuengener/sample-brain/issues/882), [#886](https://github.com/jannekbuengener/sample-brain/issues/886), [#888](https://github.com/jannekbuengener/sample-brain/issues/888), [#891](https://github.com/jannekbuengener/sample-brain/issues/891), [#893](https://github.com/jannekbuengener/sample-brain/issues/893)

## Goal

Freeze and prove the smallest deterministic **Rack/Session integration plan**
contract that places a valid `GesturePatternCoreComposition` into an already
existing Channel Rack context **without mutating that context in this slice**.

```text
ChannelRackState (base)
  + GesturePatternCoreComposition
  + explicit allow_pattern_replacement: bool
  → plan_gesture_rack_integration(...)
  → GestureRackIntegrationPlan
```

The output is an immutable integration plan / target-state intent only.

Hard boundary for this slice:

```text
NO RACK STATE MUTATION IN THIS SLICE
```

No writes to `ChannelRackController`, `WorkbenchSession`, persistence, or QML.

## Dependency on #893

Authoritative composition: `src/gesture_pattern_core_composition.py`.

`GesturePatternCoreComposition` already owns:

- new user `Channel` objects (`live_kit_group=None`, `live_kit_slot=None`)
- one exact `Pattern` with gesture `Trigger`s

It deliberately does **not** mutate `ChannelRackState`, `ChannelRackController`,
`WorkbenchSession`, persistence, QML, or playback state.

See `docs/GESTURE_PATTERN_CORE_COMPOSITION_RND_SLICE6.md`.

Quality claim on `main` after #893:

`PATTERN_CORE_COMPOSITION_ONLY — RACK_SESSION_INTEGRATION_NOT_YET_VALIDATED`

## Live foundation (verified on `origin/main` @ `da895ce0c333c01b5368c057d646120ed7ac5b49`)

| Surface | Fact |
|---------|------|
| Composition `#893` | Frozen `GesturePatternCoreComposition(channels, pattern)` delta only |
| Pattern Core | `Channel` / `Trigger` / `Pattern`; exact `Fraction` quarters; exclusive end |
| Membership helper | `require_triggers_reference_known_channels(triggers, known_channel_ids=...)` |
| Channel Rack | Frozen `ChannelRackState(channels, pattern, step_count)`; one active Pattern |
| DEFAULT_ON | `channel_rack.add_user_channel(sample_path=...)` seeds 16ths — **forbidden** for gesture apply/composition |
| Session ownership | `WorkbenchSession` owns one `ChannelRackController`; controller owns `_state` |
| `restore_state` | Compose/restore helper; intentionally does **not** notify autosave — **forbidden** as live apply shortcut |
| Persistence | Existing `workbench_session.json` snapshot path; no gesture-specific schema |
| Screen-2 projection | Step grid uses `Fraction(step_index, 4)` for `range(step_count)` — off-grid events not fully visualized |
| Concurrent work | `#898` independent Slice-6 test hygiene — not a semantic blocker; do not own those edits |

## Architecture boundary (hard)

| Domain | Authority |
|--------|-----------|
| Binding / selection / length | `#891` — already consumed by `#893` |
| Pattern-Core objects | `#893` composition — preserve exactly |
| Existing Rack channels / step_count | `base_state` — preserve |
| Active Pattern replacement | **explicit** `allow_pattern_replacement is True` |
| Trigger membership (target) | `require_triggers_reference_known_channels` on target channels |
| Controller / session mutation | **out of scope** — plan only |
| Persistence / playback / QML | **out of scope** |

This slice does **not** authorize:

- mutating `ChannelRackController._state`
- calling `restore_state(...)` as a live-product mutation
- calling `add_user_channel(...)` / DEFAULT_ON seeding
- merging incumbent Rack triggers with gesture triggers
- channel-ID reallocation / path-based channel reuse
- Live Kit taxonomy mapping
- quantization / snap / swing / groove
- deriving `step_count` from Pattern length
- persistence writes / autosave / playback / audio focus / PCM / engine / QML
- feature-toggle / Settings activation (no user-accessible behavior yet)

## Ownership decision: dedicated pure planner

**Chosen:** `src/gesture_rack_integration.py` (absent at `TEST_FREEZE`).

**Rejected for this slice:**

- Writing controller private state or using `restore_state` as apply.
- Calling `channel_rack.add_user_channel` (DEFAULT_ON 16ths corrupt exact gesture events).
- Merging incumbent + gesture triggers into one Pattern.
- Editing `channel_rack.py` / `workbench_channel_rack.py` / `workbench_session.py` /
  `workbench_session_store.py` / `workbench_qml.py` merely to express the plan.

If the frozen pure contract cannot be expressed without changing those owners,
stop with:

`INTEGRATION_CONTRACT_BLOCKED_EXISTING_OWNER_MISMATCH`

Current public frozen types already support the plan expression → no owner mismatch.

## Public seam (smallest clear form)

Module: `src/gesture_rack_integration.py` (absent at `TEST_FREEZE`).

```text
plan_gesture_rack_integration(
    base_state: ChannelRackState,
    composition: GesturePatternCoreComposition,
    *,
    allow_pattern_replacement: bool,
) -> GestureRackIntegrationPlan
```

Pure function. Immutable output. No state mutation. No hidden session/controller
lookup.

### Immutable result model

```text
GestureRackIntegrationPlan (frozen)
  expected_base_state: ChannelRackState
  target_channels: tuple[Channel, ...]
  target_pattern: Pattern
  target_step_count: int
  appended_channel_ids: tuple[str, ...]
  replaced_pattern_id: str
  replaced_trigger_count: int
  off_grid_event_count: int
  ready_for_apply: bool
```

## Frozen decisions

### 1. Integration mode — explicit active-Pattern replacement, not merge

The current Rack owns one active `Pattern`; there is no delivered multi-pattern
bank/session collection contract.

Target intent:

- preserve every existing Rack `Channel` exactly and in existing order
- append composition channels in composition order
- replace the active Rack `Pattern` with `composition.pattern` as one explicit
  state transition
- do **not** merge incumbent Rack triggers with gesture triggers
- do **not** derive a new combined Pattern length
- do **not** silently reuse the incumbent Pattern ID
- preserve composition Pattern ID, length, triggers, Fraction positions, and order

Pattern replacement is potentially destructive to incumbent step programming, so
it must never be implicit.

### 2. Replacement authority / readiness

`ready_for_apply=True` exclusively when **all** of:

- inputs are structurally valid
- channel IDs are collision-free (base unique, composition unique, no intersection)
- composition Pattern trigger membership is valid against the **target** channel set
- `allow_pattern_replacement is True` (exact boolean `True`)

When replacement is not explicitly authorized (`allow_pattern_replacement is not True`):

- planner still returns a plan describing the intended target shape
- `ready_for_apply` is `False`
- no fallback merge
- no trigger deletion
- no state mutation

### 3. Existing channels are preserved

```text
target_channels = base_state.channels + composition.channels
```

Rules:

- existing Live Kit seed channels remain unchanged (identity and provenance)
- existing user channels remain unchanged
- no existing channel is removed because its old triggers disappear with Pattern
  replacement
- composition channels remain user channels with `(None, None)` provenance
- no path-based channel reuse
- no Live Kit taxonomy mapping
- no DEFAULT_ON seeding

`appended_channel_ids` is the ordered tuple of composition channel IDs.

### 4. Channel-ID collision must fail closed

Independently of `#891` allocation:

- all `base_state.channels` IDs must be unique (existing state invariant)
- all composition channel IDs must be unique
- no composition channel ID may already exist in the base Rack
- target channel IDs remain globally unique

Do **not** reallocate IDs here.

A collision means the upstream plan/composition is stale/incompatible and must be
rebuilt against the current Rack context → raise / fail closed (no plan with
reallocated IDs).

### 5. Pattern semantics remain upstream-owned

The planner must preserve `composition.pattern` exactly:

- same `pattern_id`
- same `length_quarter_notes`
- same exact `Fraction` trigger positions
- same trigger order
- same channel references

No quantization, snapping, bar rounding, loop normalization, trigger dedupe,
timing recomputation, Pattern ID rewrite, or Pattern length rewrite.

`target_pattern` is that exact Pattern object/value.

`replaced_pattern_id` is `composition.pattern.pattern_id`.
`replaced_trigger_count` is `len(composition.pattern.triggers)`.

### 6. Step-grid metadata is preserved, not reinterpreted

`target_step_count` equals `base_state.step_count`.

Do not derive `step_count` from gesture Pattern length.

### 7. Off-grid evidence (count only)

Current Rack step positions:

```text
Fraction(step_index, 4)
for step_index in range(base_state.step_count)
```

An event is off-grid when its exact quarter position is **not** one of those
positions. Each such composition Pattern trigger increments:

`off_grid_event_count`

Evidence only. Must **not** round, snap, remove, or move events.

This slice makes **no claim** that current Screen-2 QML can fully display or edit
all unquantized events.

### 8. Stale-state / compare-before-apply contract

The plan binds to the exact immutable `base_state` it was computed from via:

`expected_base_state`

A future mutation slice may apply the plan only when the controller's current Rack
state still equals `expected_base_state`.

If the Rack changed between planning and apply:

- fail closed as stale plan
- do not partially append channels
- do not replace Pattern
- caller must recompute the integration plan from the new state

This slice freezes that rule but does **not** implement controller mutation.

### 9. Future controller/session apply ownership (document only)

A later mutation slice must:

- add/use a public `ChannelRackController` mutation seam
- never write `controller._state` directly from gesture code
- never use `restore_state(...)` as a live-product mutation shortcut
- verify the stale-state guard before mutation
- stop/resolve active Rack playback safely under controller ownership before
  swapping musical state
- commit the complete target state atomically in memory
- fire the existing musical-state changed observer exactly once after success
- let existing `WorkbenchSession` autosave/persistence-honesty handle durable write
- on validation/stale failure: zero musical-state mutation and zero autosave notify

No direct `workbench_session_store` write from `#680` feature code.

### 10. Persistence semantics are reused, not duplicated

No new persistence schema in this slice. Future successful apply persists through
the existing coherent session snapshot path.

Do not add a separate gesture project file, second Rack store, DB write, cloud
persistence, or hidden recovery cache.

### 11. Playback / runtime / UI remain out of this slice

The planner must not start/stop playback, claim/release audio focus, warm PCM,
schedule voices, inspect engine frames, mutate loop runtime, or change QML/Tk.

### 12. Immutability / determinism

Must not mutate `base_state` or `composition` (or nested frozen contents). Same
valid inputs twice → equal integration plans.

### 13. Import / ownership boundary

May import: dataclasses, fractions, typing/collections, `channel_rack.ChannelRackState`
(type only / value construction for plan fields), `pattern_core` helpers as needed
for membership validation, `#893` composition types.

Must **not** import/call:

- `workbench_channel_rack` / `ChannelRackController`
- `workbench_session` / `workbench_session_store`
- `workbench_qml`
- `channel_rack.add_user_channel` / `assign_user_channel_sample` /
  `build_channel_rack_state` / playback helpers
- `allocate_user_channel_id` (no reallocation)
- upstream gesture analysis/ranking/catalog/timing/binding recomputation entry points

## Fail-closed validation matrix (summary)

| Condition | Result |
|-----------|--------|
| wrong `base_state` / `composition` types | fail closed |
| duplicate IDs inside base channels | fail closed |
| duplicate IDs inside composition channels | fail closed |
| composition ID intersects base IDs | fail closed |
| composition triggers not subset of target channel IDs | fail closed |
| `allow_pattern_replacement is not True` | plan returned, `ready_for_apply=False` |
| valid + collision-free + membership OK + replacement `True` | `ready_for_apply=True` |

## Feature-toggle boundary

This slice introduces no user-accessible feature behavior and therefore does **not**
activate the feature-delivery toggle path.

The later slice that actually exposes/applies gesture→Rack mutation must satisfy
the repository's mandatory Settings/feature-toggle contract in the same delivery
slice.

## Quality / evidence boundary

| Label | Meaning |
|-------|---------|
| MEASURED | target channels/pattern/step_count/off-grid count computed from frozen inputs |
| HEURISTIC | none introduced |
| NOT YET CLAIMED | actual apply, playback, persistence write, QML editability, producer quality |

## R&D exit (after implementation + checks)

Exactly one of:

- `EXPLICIT_RACK_REPLACEMENT_PLAN_VIABLE`
- `RACK_SESSION_INTEGRATION_CONTRACT_INSUFFICIENT`
- `INSUFFICIENT_EVIDENCE`

**Viable means only:** a `#893` composition can be deterministically planned as an
explicit replacement of the single active Rack Pattern while preserving the
existing channel universe, appending collision-free gesture channels, carrying
stale-state evidence, and reusing the current session ownership/persistence path
— without mutating Rack/session state yet.

It does **not** mean existing Rack state has been changed, playback/persistence
apply are validated, current Screen-2 UI can fully represent unquantized events,
or producer-quality gesture matching is validated.

If viable, the next slice may implement the guarded controller/session apply seam
under this frozen plan contract.

Parent `#680` remains OPEN.

## Acceptance tests

See `tests/test_gesture_rack_session_integration_899.py` (frozen at `TEST_FREEZE`).

## Non-goals

No actual `ChannelRackState` mutation, controller apply, session autosave
execution, playback/loop validation of generated Rack state, current QML
visualization/editing of off-grid events, quantization/swing/groove, automatic
sample choice, confidence calibration, microphone/UI, multi-pattern bank, Pattern
merge policy, Arrangement/Screen 3, DB/schema change, `docs/CANON_INDEX.md` churn,
`#898` test-hygiene edits.

## Concurrent work notice

- `#898` is independent Slice-6 test hygiene and must not be mixed into this PR.
- Do not write existing Rack/session owner files in this slice.
- Avoid concurrent writes to the new Slice-7 planner/doc/test files.

## Post-implementation result

| Field | Value |
|-------|-------|
| Implementation seam | `src/gesture_rack_integration.py` — `plan_gesture_rack_integration(base_state, composition, *, allow_pattern_replacement) -> GestureRackIntegrationPlan` |
| Result model | frozen `GestureRackIntegrationPlan` with `expected_base_state`, target channels/pattern/`step_count`, append/replace evidence, `off_grid_event_count`, `ready_for_apply` |
| Focused validation | `tests/test_gesture_rack_session_integration_899.py` — **40 passed** |
| Protected validation | `#893` / `#891` / Pattern Core / Channel Rack / DEFAULT_ON / session persistence — **301 passed** (includes focused) |
| Static / hygiene | `ruff check` PASS; `git diff --check` PASS; `python tools/check_canon_drift.py` PASS |
| R&D EXIT | `EXPLICIT_RACK_REPLACEMENT_PLAN_VIABLE` |
| Mutation claim | `RACK_SESSION_STATE_NOT_MUTATED` |

Viable here means only: a `#893` composition can be deterministically planned as an
explicit replacement of the single active Rack Pattern while preserving the existing
channel universe, appending collision-free gesture channels, carrying off-grid and
stale-state evidence, and remaining ready only under explicit replacement authority —
without mutating Rack/session/persistence/QML state.

Parent `#680` remains OPEN. Next slice (not this PR): guarded controller/session apply
under this frozen plan contract.
