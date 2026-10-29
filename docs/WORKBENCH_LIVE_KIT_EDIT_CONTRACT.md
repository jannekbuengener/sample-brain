# Workbench Live Kit Edit Contract (#1077 / #1123 / #1207)

**Status:** ACTIVE_SUPPORTING  
**Issue:** [#1077](https://github.com/jannekbuengener/sample-brain/issues/1077) (Edit tool baseline); [#1123](https://github.com/jannekbuengener/sample-brain/issues/1123) (always-closed start + horizontal group cards); [#1207](https://github.com/jannekbuengener/sample-brain/issues/1207) (default-hidden Kit HUD + transient Add feedback)  
**Parent:** [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075)  
**Depends on:** [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076) product boundary; [#1070](https://github.com/jannekbuengener/sample-brain/issues/1070) Edit docking topology; [#1072](https://github.com/jannekbuengener/sample-brain/issues/1072) internal Sample DnD targets  
**Related:** [#728](https://github.com/jannekbuengener/sample-brain/issues/728) Export Kit; [#1071](https://github.com/jannekbuengener/sample-brain/issues/1071) docking visuals; [#1073](https://github.com/jannekbuengener/sample-brain/issues/1073) Sample drag visuals; [#1078](https://github.com/jannekbuengener/sample-brain/issues/1078) Arrangement entry; [#1220](https://github.com/jannekbuengener/sample-brain/issues/1220) Browser→Kit handoff; [#1221](https://github.com/jannekbuengener/sample-brain/issues/1221) full Live-Kit product

## Goal

Deliver the **classic Live Kit as an Edit/Kit-workspace tool**: reveal / hide /
collapse / resize inside Edit without a permanent empty bottom Rack/Sequencer
cavity, without a mandatory Step Grid, and without a second musical state owner.

## Ownership

| Concern | Owner |
|---------|-------|
| Musical kit assignments | Python (`LiveKitState` / `assign` / `clear_slot`) |
| Visibility / collapse preference | Python workspace/display preference owner |
| #1070 materialization of `live_kit` | Python, driven by visible Live Kit state |
| #1072 visible assignment targets | Python (`list_visible_live_kit_targets` + `visible_slot_keys`) |
| Projection + typed reveal/hide/resize intents | QML (read-only for kit truth) |
| Export Kit | Existing export seam (#728) |
| Drag ghosts / drop highlights | Out of scope (#1073) |
| Magnetic docking chrome | Out of scope (#1071) |
| Arrangement entry CTA | Out of scope (#1078); never aliased to Export |

## Product boundary

Live Kit is **not** an upper product mode, not Arrangement, not a Step-Sequencer
container, and not a generic docking widget platform.

| In module | Out of module |
|-----------|---------------|
| Canonical kit groups / slots | Step Grid / Pattern editor |
| Add / Replace / Remove | Arrangement timeline |
| Export Kit (distinct action) | Arrangement Entry (owned by #1078) |
| Reveal / hide / collapse / resize | Mixer / Piano Roll / automation / Later Live |

### Rack / Step-Grid decoupling (verified)

Historical #908 co-hosted Channel Rack / step UI inside the same bottom overlay
as Live Kit. Valid **Edit** flows (Browser, Harmony, Add/Replace/Remove, Export,
audition, Esc, Live Kit reveal/hide) do **not** depend on that co-hosting.

- Domain `ChannelRackController.ensure_state` may still exist for Arrangement /
  historical seams.
- The Live Kit Edit module must **not** project Rack / step-grid UI or reserve
  height for it.
- Step Sequencer product placement remains Arrangement (#1076 / #1078 / #1080).

## Visibility rules

```text
visible  <=>  live_kit_materialized AND drawer/presentation open (not collapsed)
hidden   <=>  not visible
```

| State | Projection | Geometry | #1070 `live_kit` | #1072 targets |
|-------|------------|----------|------------------|---------------|
| Hidden / collapsed | none | height 0; no phantom min-height | `False` | empty |
| Visible / materialized | exactly one Live Kit projection | compact upper-right Kit HUD overlay (#1207) | `True` | slots of **expanded** groups only (headers-only / all collapsed → empty) |

### Kit HUD presentation ownership (#1207)

Live Kit is **not** a permanent Screen-1 pane. Musical kit state stays Python-owned
(`LiveKitState` / `assign` / `clear_slot`). HUD open/close is presentation only.

```text
Live Kit musical state → Python authority
Kit HUD → presentation only
default → hidden / zero footprint
successful Add → transient feedback (~9s; generation-token timer)
manual open → persistent until explicit close
```

| Mode | Open trigger | Auto-dismiss | Preference / restore |
|------|--------------|--------------|----------------------|
| `hidden` | cold start / explicit close / transient expiry | — | closed |
| `transient` | successful Add/Replace (or accepted internal drop) | yes; generation-token timer | does **not** set `_live_kit_visibility_desired` |
| `manual` | reveal control / Hide toggle open | no; timer cannot close | may persist UI preference (existing contract) |

Failed Add must not show success HUD. Explicit close / Esc never clears musical
assignments. Transient HUD must not steal Browser keyboard focus; pending-add
chooser may focus for Esc cancel. Reopen affordance is the Edit-scoped
`editLiveKitRevealControl` (`Kit N/M`), gated behind Browser-ready chrome
(`browserMaterialized`) so #1213 onboarding stays zero-chrome. Live Kit remains
excluded from #1204 generic panel disclosure.

“Always-on kit projection” applies **only** while visible. Hidden/collapsed must
retain no hidden projection, target surface, or phantom geometry. Hide never
clears musical assignments or active-track kit state. A pending Add-to-Kit
chooser counts as presentation-open for `#1070` / `#1072` even when the drawer
preference remains closed (QML `kitHudExpanded` / compat `bottomExpanded` via
`liveKitPendingAdd`).

Default clean Edit startup (#1123): Live Kit **always** starts hidden/collapsed.
`apply_live_kit_visibility_preference` forces closed on workspace/app start and
must **not** rematerialize from a persisted `live_kit_visible=true`. Musical kit
assignments remain fully persisted; only chrome visibility defaults closed.
Session writes may still update the preference file (best-effort), but restart
and cold apply ignore an open disk value. In-session desired visibility
(`_live_kit_visibility_desired`) drives hide→reveal within the same session and
post-analysis restore via `restore_live_kit_after_active_source` after the user
has **manually** opened the tool. Transient Add feedback does not claim that
reopen authority. Without an active Source, materialization fails closed. During
analysis, presentation stays closed/unmaterialized (no QML/Python desync).
Visibility preference writes are best-effort UI persistence and must fail-soft
(`OSError` must not abort reveal/hide or bridge refresh).

User-controlled Live Kit height is session UI authority on the interaction
adapter (`live_kit_user_height_px`, `0` = auto row-derived height), clamped to
compact minimum and the existing workspace cap. Resize intents are separate
from collapse/hide, panel-move, and sample-drag; resize is manual-mode only.

### Group card projection (#1123)

Top-level kit **groups** project as compact horizontal cards (responsive wrap on
narrow width; never unreadably narrow; no horizontal overflow as the default).
Domain taxonomy keys stay authoritative (`Kick + Bass`, `Drums`, `Melodic`,
`Atmos / FX`). Display-only labels may remap presentation without renaming
domain IDs:

| Domain group | Display label | Domain slots → display |
|--------------|---------------|------------------------|
| `Kick + Bass` | `Bassline` | `Kick` → `Kick Drum`; `Bass` → `Bass` |
| `Drums` | `Drums` | unchanged |
| `Melodic` | `Melodic` | unchanged |
| `Atmos / FX` | `Atmos / FX` | unchanged (single domain group → one card; do not invent dual domain in QML) |

Clicking a group card toggles expand/collapse of that group's slots. Collapsed
groups keep musical assignments. Add / Replace / Remove / Export Kit seams are
unchanged and remain Python-owned.

### Edit-scoped reveal (`editLiveKitRevealControl`)

“Live Kit” must **not** appear in upper mode navigation (`headerNavRow`) beside
Browser / Step Sequencer / Arrangement (Owner visual gate — see
`PROGRAM_CHROME_CONTRACT.md`). Reveal/hide is an **Edit workspace tool control**
(`editLiveKitRevealControl`): Screen-1 only, uses the #1077 visibility owner
(`toggle_live_kit_drawer` / preference / reveal seam), and must not invent a
second loader. While unmaterialized and empty it stays hidden; once the tool can
be shown and is currently closed, the workspace control reveals it. Collapse
while open stays on the pane-local handle.

## Mutation seams

Reuse one Python-owned kit truth:

| Action | Seam |
|--------|------|
| Add / Replace | `LiveKitState.assign` via existing adapter / `live_kits_registry` |
| Remove | `LiveKitState.clear_slot` (same validate + notify guarantees as assign) |
| Export | `export_live_kit` (#728) — distinct from Arrangement Entry |

`clear_slot` must not invent a second mutation path: same group/slot validation,
same `on_assignment_changed` notify contract, and fail-closed invalid targets.

## #1072 integration depth (this slice)

Provision visible Live-Kit assignment target identities when the kit is visible;
treat hidden kit as no targets. Do **not** implement QML drag visuals, ghosts,
drop highlights, or full Browser/Harmony drag interaction (#1073).

## Docking (#1070)

| Feature / lock | Live Kit behavior |
|----------------|-------------------|
| Docking OFF | Canonical placement; reveal/hide/resize still work |
| ON + LOCKED | Reveal/hide/resize work; no reorder |
| ON + UNLOCKED | Moves only through valid #1070 Edit slots |

## Non-goals

Arrangement sequencer/timeline, track-package save invention, Later Live, 3D,
plugin/widget registry, Mixer/Piano Roll/automation, new audio engine, full
#1071 docking chrome, full #1073 drag UX.
