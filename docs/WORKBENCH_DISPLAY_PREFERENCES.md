# Screen-1 Display Preferences — Density, Motion, Layout Reset, Startup Presets (#696)

**Status:** ACTIVE_SUPPORTING (product contract under #691)  
**Parent:** [#691](https://github.com/jannekbuengener/sample-brain/issues/691)  
**Issue:** [#696](https://github.com/jannekbuengener/sample-brain/issues/696)  
**Shared visual states:** [#700](https://github.com/jannekbuengener/sample-brain/issues/700) / [`WORKBENCH_VISUAL_ACCEPTANCE.md`](WORKBENCH_VISUAL_ACCEPTANCE.md)  
**Depends on:** [#692](https://github.com/jannekbuengener/sample-brain/issues/692) density, [#693](https://github.com/jannekbuengener/sample-brain/issues/693) Clean Start, [#694](https://github.com/jannekbuengener/sample-brain/issues/694) elastic layout, [#695](https://github.com/jannekbuengener/sample-brain/issues/695)/[#738](https://github.com/jannekbuengener/sample-brain/issues/738) motion/playhead seams

## Product goal

Bundle Screen-1 display/workspace preferences in **one small, secondary
affordance**. Settings must not dominate the Calm Adaptive Workspace.

This issue owns the **product Preferences surface and persistence writers** for:

- Density;
- Motion;
- Reset Layout;
- Save Workspace Preset;
- Set Preset as Startup;
- Return to Clean Start.

It does **not** recreate historical last-session restore under the name Preset.

## Frozen owner decisions (2026-09-30)

| Topic | Decision |
|-------|----------|
| Motion vocabulary | Canonical stored/API values: `on` \| `reduced` \| `off`. Legacy acceptance token `full` is **not** continued. If persisted `full` is read, normalize to `on` on load; never write `full` again. |
| Density (first slice) | **Compact-only.** No Comfortable option until runtime/Owner evidence shows real need. No dropdown with a fake second entry. |
| Preferences surface | Small **header overflow / popover** affordance. No permanent settings bar. No Tools panel. Reachable in Calm Start **and** Active Source without putting settings on the Calm Canvas. |

## UI principle

- Settings are secondary.
- One small header overflow control opens a compact popover/menu.
- No permanently visible Screen-1 settings strip.
- Affordance stays available in Clean Start and Active Source.

## Density

- Product default and sole first-slice mode: **Compact**
  (`compact_target_30dip` / #692 contract).
- Round-trip persistence must preserve Compact.
- Comfortable is explicitly **out of first-slice product UI**. Reserved for a
  later evidence-gated follow-up; do not invent a second selectable mode now.

## Motion

Canonical modes:

| Value | Meaning |
|-------|---------|
| `on` | Full feature motion (e.g. playhead presentation driver allowed). |
| `reduced` | Same authoritative progress; reduced motion presentation. |
| `off` | No feature motion: no playhead, no FrameAnimation work for motion features, no timers/repaints for this concern. |

Rules:

- User setting may explicitly override a system/accessibility preference when
  Qt/platform exposes one robustly.
- If no robust system preference is available, default to `on` and persist the
  user choice.
- Consumers (#738 playhead and later motion features) **consume** this mode;
  they do not own Settings UI.
- Visual-acceptance fixtures migrate from historical `full` → `on`. Historical
  evidence that recorded `full` remains historical; new writes use `on`.

## Layout actions

### Reset Layout

- Restores canonical default panel **ratios** from
  [`WORKBENCH_ELASTIC_LAYOUT.md`](WORKBENCH_ELASTIC_LAYOUT.md).
- Does **not** mutate library Sources, sample catalog rows, or audio files.
- Does **not** clear Workspace Presets or the Startup designation.
- Does **not** by itself change active Source / selection / preview / harmony.

### Return to Clean Start

- Returns the working surface to Clean Start semantics
  ([`WORKBENCH_CLEAN_START.md`](WORKBENCH_CLEAN_START.md)): no active Source,
  no browser selection, no preview, harmony closed, reveal collapsed.
- Does **not** delete registered Sources.
- Does **not** delete saved Workspace Presets or the Startup designation file
  unless the user explicitly clears Startup separately.

## Workspace Preset / Startup Preset

### What a preset may contain

Stable workspace/UI state only:

- `version` (schema version, integer);
- `panel_ratios` (relative weights; #694 authority);
- `panel_visibility` (known panel ids only);
- `density_mode` (first slice: Compact only);
- `motion_mode` (`on` \| `reduced` \| `off`);
- optional `startup_source_node_id` (registered local Source identity only).

### What a preset must never contain

- active Sample selection;
- Preview / Transport / playhead progress;
- Harmonic Match results / transient anchor;
- scroll position;
- transient `library_revealed`;
- private absolute filesystem paths;
- private sample/audio payloads.

Source references use already-registered local Source **identity**, never
exportable absolute private paths.

### Startup semantics

- Without registered Sources → Clean Start (unchanged First-use path).
- With ≥1 available persisted Source → Returning Workspace (#762) even without
  an explicit Startup designation. `startup_source_node_id` is an optional
  preference override, not a required gate for Source reactivation.
- A Startup Preset Source is valid only after an explicit user action
  (`Set Preset as Startup` / equivalent) when the user wants a specific Source
  over the library default order.
- Absence, corruption, or deletion of that designation does **not** force Clean
  Start when persisted Sources remain available (#762).
- Layout preference persistence may retain ratios / density / motion. Source
  reactivation on launch is owned by the library Source authority + optional
  Startup designation, not by a general session snapshot.
- Hard rule: do **not** recreate full “last session restore” (selection /
  preview / harmony / scroll) under the name Preset.

### Product actions

| Action | Effect |
|--------|--------|
| Save Workspace Preset | Persist current stable UI preference snapshot (no transient session). |
| Set Preset as Startup | Explicitly designate the saved Startup Preset file used at next launch. |
| Clear Startup (if exposed) | Remove designation → next launch Clean Start. |

Module seams (extend, do not fork):

- `src/workbench_qml_startup.py` — Startup Preset load/resolve/write;
- `src/workbench_layout_solver.py` / `src/workbench_qml_elastic.py` — ratios;
- `src/workbench_qml.py` — header overflow affordance + preference bindings;
- playhead / motion consumers read motion mode only.

## Failure behavior

| Condition | Behavior |
|-----------|----------|
| Unknown schema version | Controlled fail-closed (Clean Start for startup resolve; defaults for prefs). |
| Malformed JSON | Clean Start / defaults; no crash. |
| Missing/offline startup Source | Skip that designation; fall to next available persisted library Source (#762); if none → Clean Start. Do not delete registration. |
| Invalid ratios | Canonical default ratios. |
| Unknown panel IDs | Ignore / fail-closed per elastic contract. |
| Legacy motion `full` | Normalize to `on` on read; never re-persist as `full`. |

## RED contracts (minimum)

1. Empty library → Clean Start; persisted available Sources → Returning
   Workspace without requiring Startup designation (#762).
2. Density round-trip (Compact).
3. Motion round-trip (`on` / `reduced` / `off`); `full` loads as `on`.
4. Ratio/visibility preset round-trip.
5. Explicit Startup designation, when available, prefers that Source (no
   selection / no preview / harmony closed / Live Kit undisclosed).
6. Reset Layout does not change library/sample data.
7. Return to Clean Start does not delete presets/Sources.
8. Corrupt state does not crash.
9. Preset never serializes preview / match / selection / scroll / absolute
   private paths.
10. Motion Off disables #738 playhead presentation work.
11. Preferences affordance is header overflow/popover only (no permanent bar).

## Non-scope

- Comfortable density UI (evidence-gated follow-up);
- Cloud sync / accounts;
- General app-wide Preferences redesign;
- Live-Kit musical preset / session snapshot;
- Panel reordering (#697);
- Waveform renderer rewrite;
- Screen 2 / Screen 3;
- Permanent settings bar / Tools panel;
- Last-session auto-resume.

## Authority

On conflicts for Screen-1 display preferences / startup designation:

```text
scoped #696 > #691 > #693 Clean Start / #694 elastic / #738 motion consume > historical #503
```

Geometry ratios remain owned by #694. Clean Start visibility remains owned by
#693. Motion **presentation** remains owned by feature consumers; Motion
**preference value and UI** are owned by #696.

## Validation notes

- Synthetic fixtures only; evidence outside the repository.
- Prefer #700 v2 state IDs; do not invent a parallel fixture family.
- Owner Visual Acceptance remains separate from agent self-attestation.
