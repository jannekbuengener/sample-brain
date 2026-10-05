# Gesture Rack Controller/Session Apply R&D — Slice 9 (#680 / #921)

**Status:** Implemented — `GUARDED_CONTROLLER_SESSION_APPLY_VIABLE`

**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680) (remains OPEN)

**Child:** [#921](https://github.com/jannekbuengener/sample-brain/issues/921)

## Delivered dependencies

| Issue | Role | Exit |
|-------|------|------|
| [#899](https://github.com/jannekbuengener/sample-brain/issues/899) / [#903](https://github.com/jannekbuengener/sample-brain/issues/903) | Pure `GestureRackIntegrationPlan` | `EXPLICIT_RACK_REPLACEMENT_PLAN_VIABLE` |
| [#904](https://github.com/jannekbuengener/sample-brain/issues/904) | Historical SETTINGS_GATE | `FEATURE_SETTINGS_OWNER_BLOCKED` — **do not rewrite** |
| [#910](https://github.com/jannekbuengener/sample-brain/issues/910) | Canonical functional settings owner | `CANONICAL_FUNCTIONAL_SETTINGS_OWNER_VIABLE` |

Live `main` baseline for this freeze:

`f14bcc5b6c9a533d9c11747ece0bbc235d872007`

## Goal

Prove one guarded public controller apply seam that takes a **ready**
`GestureRackIntegrationPlan` and applies its complete target musical state
through the existing `ChannelRackController` / `WorkbenchSession` ownership
path.

```text
GestureRackIntegrationPlan
  + feature_enabled: bool  (injected; controller does not read settings I/O)
  → ChannelRackController.apply_gesture_integration_plan(...)
  → VALIDATE (fail-closed, zero side effects)
  → CONSTRUCT TARGET ChannelRackState
  → STOP via existing controller.stop()
  → ATOMIC _state replace
  → exactly one on_musical_state_changed
  → existing WorkbenchSession snapshot/autosave
```

## Public signature (frozen)

```python
ChannelRackController.apply_gesture_integration_plan(
    plan: GestureRackIntegrationPlan,
    *,
    feature_enabled: bool,
) -> ChannelRackState
```

- Controller must **not** call `load_workbench_feature_settings` or open JSON.
- Caller injects `feature_enabled` from `#910` (`gesture_rack_apply_enabled`).
- Prefer `feature_enabled is True` (strict) for the enabled gate.

## Settings gate (satisfied by #910)

Canonical owner: `WorkbenchFeatureSettings.gesture_rack_apply_enabled`
(default `False`, persisted, user-accessible Functional toggle).

This slice **consumes** that flag via injection. It does **not**:

- redesign settings architecture
- store the flag in musical session / plan / rack state
- invent a second persistence owner

Historical `#904` evidence
(`docs/GESTURE_RACK_CONTROLLER_APPLY_RND_SLICE8.md`,
`FEATURE_SETTINGS_OWNER_BLOCKED`) remains frozen narrative.

## Fail-closed preconditions (before any side effect)

All of the following must pass **before** `stop()`, `_state` mutation,
observer notification, or autosave:

1. `feature_enabled is True`
2. `isinstance(plan, GestureRackIntegrationPlan)`
3. `plan.ready_for_apply is True`
4. Controller has materialized rack state (`_state is not None`) —
   **no** implicit `ensure_state()` / screen enter
5. `self._state == plan.expected_base_state` (structural equality; stale guard)
6. Target constructs a valid `ChannelRackState(channels=plan.target_channels,
   pattern=plan.target_pattern, step_count=plan.target_step_count)`
   (unique IDs + trigger/channel membership via `__post_init__`)
7. Grid-span invariant:
   `plan.target_pattern.length_quarter_notes >= Fraction(plan.target_step_count, 4)`

On any failure: zero stop, zero `_state` change, zero observer, zero autosave,
zero audio-focus claim/release.

## Side-effect order (success only)

```text
VALIDATE → CONSTRUCT TARGET → STOP → ATOMIC STATE REPLACE → OBSERVER ONCE
```

1. Build and validate complete target state first.
2. Call existing `ChannelRackController.stop()` (idle-safe; clears loop runtime).
3. Assign `self._state = target` in one transition (no partial append/replace).
4. Fire `_notify_musical_state_changed()` **exactly once**.
5. Return the new state.

## Anti-patterns (forbidden)

- `restore_state(...)` as live apply (compose/restore; no autosave notify)
- External writes to `controller._state`
- `add_user_channel` / DEFAULT_ON seeding
- Direct `workbench_session_store` writes from gesture/apply code
- Channel ID reallocation / path-based reuse / timing quantization
- Audio-focus claim/release as part of apply
- Mutating the input plan
- Session mutation facade / QML gesture workflow UI / microphone UI

## Observer / autosave

Reuse the existing session wiring:

```text
set_on_musical_state_changed → _autosave_musical_session → snapshot save
```

- Success: exactly one observer fire → one autosave attempt.
- Failure paths: observer count = 0, autosave attempts = 0.
- Save IO failure after valid in-memory mutation follows existing persistence
  honesty (`note_autosave_failed`); memory remains authoritative.

## Non-goals

- Microphone / gesture capture UI
- Automatic sample selection / ranking / timing / composition rebuild
- Arrangement / Screen-3 / #905 navigation work
- New settings architecture or second persistence
- QML musical-state ownership
- Engine rewrite
- Closing parent `#680`

## R&D exit (exactly one)

- `GUARDED_CONTROLLER_SESSION_APPLY_VIABLE`
- `CONTROLLER_APPLY_CONTRACT_INSUFFICIENT`
- `INSUFFICIENT_EVIDENCE`
- `FEATURE_SETTINGS_OWNER_BLOCKED` — only if live proof shows `#910` unusable

`GUARDED_CONTROLLER_SESSION_APPLY_VIABLE` means only: a ready `#899` plan can be
applied atomically through the controller/session ownership path with
fail-closed gates, controller-owned stop, one successful observer notify,
existing autosave reuse, and injected enabled/disabled behavior.

## Acceptance

See `tests/test_gesture_rack_controller_apply_921.py`.
