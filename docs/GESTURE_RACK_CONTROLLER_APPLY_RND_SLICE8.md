# Gesture Rack Controller/Session Apply R&D — Slice 8 (#680 / #904)

**Status:** SETTINGS_GATE exit — `FEATURE_SETTINGS_OWNER_BLOCKED`  
**No product mutation delivered in this slice.**

**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680) (remains OPEN)  
**Child:** [#904](https://github.com/jannekbuengener/sample-brain/issues/904)  
**Dependencies (DONE):** [#899](https://github.com/jannekbuengener/sample-brain/issues/899) / [#903](https://github.com/jannekbuengener/sample-brain/issues/903) — `EXPLICIT_RACK_REPLACEMENT_PLAN_VIABLE` on `main` at `ef99174dd09b445619dea49b13ac8695a1537e75`

## Goal (intended)

Implement and prove one guarded public `ChannelRackController` apply seam that
takes a ready `GestureRackIntegrationPlan` and applies its complete target
musical state through existing `WorkbenchSession` observer/autosave ownership.

## Hard stop — SETTINGS_GATE

#899 / #904 require that the first slice which actually applies gesture→Rack
mutation satisfy the repository's mandatory Settings/feature-toggle contract in
the same delivery slice:

- one stable setting key for gesture→Rack apply
- explicit documented default (prefer disabled by default for this R&D feature)
- persisted through the canonical Workbench settings architecture unless proven
  intentionally session-only
- user-accessible through the canonical Settings surface
- disabled ⇒ zero hidden apply, zero state mutation, zero playback stop, zero
  autosave/background work
- re-enable restores apply without restart-only hidden state
- enabled and disabled behavior both tested

#904 further forbids silently overloading a view-only owner with a functional
feature flag unless current canon explicitly defines that owner as correct.

If no canonical user-accessible **functional** Settings owner/surface exists,
stop before product mutation and report:

```text
FEATURE_SETTINGS_OWNER_BLOCKED
```

Do not invent a second ad-hoc settings subsystem just to make the slice green.

## LIVE_STATE (verified)

| Fact | Evidence |
|------|----------|
| `origin/main` SHA | `ef99174dd09b445619dea49b13ac8695a1537e75` |
| Open competing PRs for #904 apply/settings | none at gate time |
| #899 plan contract | `src/gesture_rack_integration.py` + `docs/GESTURE_RACK_SESSION_INTEGRATION_RND_SLICE7.md` |
| Apply seam on `ChannelRackController` | absent (`apply_gesture_integration_plan` not present) |

## DOCS_GATE (read, no conflict on apply ownership)

Applicable owners remain:

| Concern | Authority |
|---------|-----------|
| Session / autosave | `docs/SESSION_OWNERSHIP_CONTRACT.md`, `src/workbench_session.py` |
| Pattern types | `docs/PATTERN_CORE_CONTRACT.md`, `src/pattern_core.py` |
| Sequencer / playback | `docs/SEQUENCER_PLAYBACK_CONTRACT.md` |
| Rack controller | `src/workbench_channel_rack.py` |
| Integration plan | #899 / `src/gesture_rack_integration.py` |

Apply ownership intended by #904 (not implemented here):

```text
GestureRackIntegrationPlan
  → ChannelRackController public apply seam
  → controller-owned stop (only after valid preconditions)
  → atomic ChannelRackState swap
  → exactly one on_musical_state_changed
  → existing WorkbenchSession snapshot/autosave
```

`restore_state()` remains compose/restore-oriented and must not be used as a
live-product apply shortcut (does not notify autosave).

## SETTINGS_GATE — live owner inventory

Live Workbench “settings / preferences” surfaces on `main`:

| Owner | Module / surface | Persisted file (user-local) | Scope on live `main` | Functional feature-toggle owner? |
|-------|------------------|-----------------------------|----------------------|----------------------------------|
| `WorkbenchViewSettings` | `src/workbench_controller.py` (+ Tk `WorkbenchApp`) | `workbench_view_settings.json` | View visibility only: `show_view_toolbar`, `show_search`, `show_filters`, `show_library_manage`, `show_waveform_tools` | **No** — display/view preferences |
| `DisplayPreferences` | `src/workbench_display_preferences.py` + Screen-1 header overflow | `screen1_display_preferences.json` | Density + motion only | **No** — Screen-1 display prefs (#696) |
| `WorkspacePreset` / startup | same display-preferences façade | `screen1_workspace_preset.json` (+ startup designation) | Layout ratios/visibility, density, motion, optional startup Source id | **No** — workspace/UI preset, not R&D feature flags |
| Theme preferences | `src/workbench_theme.py` | `screen1_theme_preferences.json` | Appearance / theme tokens | **No** — theme authority (#785) |
| Layout preferences | `src/workbench_layout_solver.py` | `screen1_layout_preferences.json` | Panel ratios | **No** — geometry |

Canonical product surface for Screen-1 preferences is the **header overflow /
popover** owned by #696 (`docs/WORKBENCH_DISPLAY_PREFERENCES.md`). That contract
explicitly owns density, motion, layout reset, and workspace/startup presets.
It lists **“General app-wide Preferences redesign”** as non-scope and does not
authorize functional R&D feature flags.

`docs/CANON_INDEX.md` lists Screen-1 display preferences as
`ACTIVE_SUPPORTING` for density/motion/layout reset/startup presets — not as a
functional feature-toggle registry.

No other tracked Settings owner/surface on live `main` provides:

- a stable functional feature-toggle key store
- a user-accessible Settings control for enabling/disabling gesture→Rack apply
- a documented persistence contract for R&D product feature flags

### Explicit non-owners for this gate

| Candidate | Why rejected |
|-----------|--------------|
| `WorkbenchViewSettings` | View-visibility schema only; #904 forbids silently overloading it with functional flags |
| Display Preferences header overflow | Display/workspace prefs only; app-wide Preferences redesign is non-scope under #696 |
| Theme / layout preference files | Appearance/geometry only |
| New ad-hoc JSON/module invented in #904 | Forbidden by #904 (“do not invent a second ad-hoc settings subsystem”) |
| Config profiles (`config/profiles*.yaml`) | Pipeline/profile indirection — not a Workbench user Settings surface |
| Session-only boolean on controller | Would not satisfy “user-accessible through the canonical Settings surface” + persist/reload cases required by #904 |

## Gate decision

```text
FEATURE_SETTINGS_OWNER_BLOCKED
```

Meaning:

A ready #899 integration plan **cannot** yet be applied through a Settings-gated
controller/session seam because live `main` has no canonical user-accessible
**functional** Settings owner/surface that may host the required gesture→Rack
apply toggle without inventing a parallel settings subsystem or overloading a
view/display-only owner.

### What this does **not** mean

- The #899 plan contract is invalid
- Controller/session apply ownership is unclear
- Parent #680 is parked again
- A settings subsystem should be invented inside #904

### What must happen before apply implementation resumes

A separate scoped issue must establish (or explicitly designate) a canonical
user-accessible **functional** Settings owner/surface that can host R&D feature
toggles with stable key, default, persistence, and UI affordance. Only after
that owner exists may a later #680 slice reopen SETTINGS_GATE and continue
TEST_GATE → TEST_FREEZE → IMPLEMENTATION for the guarded apply seam.

## Product mutation boundary for this slice

**Forbidden while SETTINGS_GATE is blocked:**

- `ChannelRackController.apply_gesture_integration_plan` (or equivalent)
- any write to `controller._state` from gesture code
- using `restore_state()` as live apply
- WorkbenchSession / `workbench_session_store` writes for gesture apply
- Settings UI toggle for gesture apply
- microphone UI, generated-pattern button, gesture workflow, off-grid editor

**Allowed in this slice:**

- this SETTINGS_GATE evidence document
- focused SETTINGS_GATE tests that freeze the owner inventory / blocker
- issue/PR evidence closing #904 with the R&D exit below

## R&D exit

Exactly one:

```text
FEATURE_SETTINGS_OWNER_BLOCKED
```

Parent `#680` remains OPEN.

## Acceptance tests

See `tests/test_gesture_rack_controller_apply_904_settings_gate.py`.

## Non-goals

No controller apply implementation, no Rack musical-state mutation, no Settings
subsystem invention, no Display Preferences / ViewSettings schema expansion for
functional flags, no microphone/UI, no Screen-3 / Arrangement, no CANON_INDEX
authority rewrite in this blocker slice.
