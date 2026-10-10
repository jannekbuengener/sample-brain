# Workbench Live Kit Edit Contract (#1077)

**Status:** ACTIVE_SUPPORTING  
**Issue:** [#1077](https://github.com/jannekbuengener/sample-brain/issues/1077)  
**Parent:** [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075)  
**Depends on:** [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076) product boundary; [#1070](https://github.com/jannekbuengener/sample-brain/issues/1070) Edit docking topology; [#1072](https://github.com/jannekbuengener/sample-brain/issues/1072) internal Sample DnD targets  
**Related:** [#728](https://github.com/jannekbuengener/sample-brain/issues/728) Export Kit; [#1071](https://github.com/jannekbuengener/sample-brain/issues/1071) docking visuals; [#1073](https://github.com/jannekbuengener/sample-brain/issues/1073) Sample drag visuals; [#1078](https://github.com/jannekbuengener/sample-brain/issues/1078) Arrangement entry

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
| Visible / materialized | exactly one Live Kit projection | compact elastic/drawer bounds | `True` | slots of **expanded** groups only (headers-only / all collapsed → empty) |

“Always-on kit projection” applies **only** while visible. Hidden/collapsed must
retain no hidden projection, target surface, or phantom geometry. Hide never
clears musical assignments or active-track kit state. A pending Add-to-Kit
chooser counts as presentation-open for `#1070` / `#1072` even when the drawer
preference remains closed (QML `bottomExpanded` via `liveKitPendingAdd`).

Default clean Edit startup: Live Kit hidden/collapsed (preference default
`live_kit_visible=False`). Restart respects the persisted visibility preference
and must not auto-open when the preference says hidden. When the preference is
`true` under an active Source, restore must rematerialize Live Kit through the
existing runtime disclosure seam (`reveal_live_kit` / `_reveal_live_kit_pane`);
drawer flags alone are not sufficient. Without an active Source, materialization
fails closed (preference may stage open flags, but `live_kit_is_visible()` stays
false until progressive disclosure can succeed). After Source analysis completes
and an active Source is restored, re-apply the visibility preference through the
same reveal seam so staged preference is not lost to `#742` analysis disclosure
clears. During analysis, presentation stays closed/unmaterialized (no QML/Python
desync). Visibility preference writes are best-effort UI persistence and must
fail-soft (`OSError` must not abort reveal/hide or bridge refresh).

User-controlled Live Kit height is session UI authority on the interaction
adapter (`live_kit_user_height_px`, `0` = auto row-derived height), clamped to
compact minimum and the existing 40% workspace cap. Resize intents are separate
from collapse/hide, panel-move, and sample-drag.

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
