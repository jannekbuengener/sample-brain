# Workbench Edit Docking Topology (#1070)

**Status:** ACTIVE_SUPPORTING  
**Issue:** [#1070](https://github.com/jannekbuengener/sample-brain/issues/1070)  
**Parent:** [#1069](https://github.com/jannekbuengener/sample-brain/issues/1069)  
**Product boundary:** [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076)  
**Follow-up QML:** [#1071](https://github.com/jannekbuengener/sample-brain/issues/1071)  
**Related:** [#1077](https://github.com/jannekbuengener/sample-brain/issues/1077) Live Kit materialization; [#694](https://github.com/jannekbuengener/sample-brain/issues/694) elastic layout; [#910](https://github.com/jannekbuengener/sample-brain/issues/910) feature settings

## Goal

Freeze the deterministic **Python-owned** contract for bounded Edit/Kit workspace
panel topology: stable panel/slot identities, move/swap/reflow validation,
Layout Lock, feature gate, persistence/migration, and typed intents for later
QML. This issue does **not** implement QML docking visuals.

## Ownership

| Concern | Owner |
|---------|-------|
| Topology / validation / lock / persistence | Python (`src/workbench_edit_docking.py`) |
| Feature availability | `WorkbenchFeatureSettings.workspace_panel_docking_enabled` (#910) |
| Horizontal ratios / resize | Existing elastic layout solver (#694) |
| Collapse / visibility materialization | Existing elastic / #845 / #1077 seams |
| Musical Kit / Pattern / session | Unchanged; docking never mutates them |
| Drag ghosts / drop highlights | Out of scope (#1071) |

QML (#1071) may send typed intents and project state only. No second layout owner.

## Product boundary

Applies to **Edit/Kit tools only**.

| Allowed when materialized | Forbidden docking targets |
|---------------------------|---------------------------|
| `library` | `arrangement` |
| `browser` | `live` (later Live surface) |
| `harmony` | `channel_rack` / `rack` / `step_sequencer` (no mandatory phantom) |
| `live_kit` (classic Live Kit when visible) | unknown IDs (fail closed) |

Hidden or absent panels consume **no** phantom slot or minimum geometry.
Arrangement and later Live are separate product surfaces, not docking slots.

## Feature gate + lock

Feature key (functional settings owner):

`workspace_panel_docking_enabled` — default `False`

| Mode | Docking mutation |
|------|------------------|
| Feature OFF | No move/swap/reflow; no hidden reorder |
| ON + `LOCKED` (default) | Docking capability present; moves rejected / no-op |
| ON + `UNLOCKED` | Valid bounded moves/swaps/reflows accepted |

Lock is independent of resize, collapse/reveal, focus, audition, and sample
interaction. Re-lock preserves the committed topology.

## Bounded topology

Persisted preferred order is a tuple of technical panel IDs (not display copy).

Active order = preferred order filtered to currently materialized panels.
Slots are derived contiguously as `edit_slot_0` … `edit_slot_n-1` for the
active order only (no reserved empty cavities).

Canonical preferred order:

```text
library, browser, harmony, live_kit
```

Move / swap / reflow:

- Same starting topology + intent → deterministic result
- Invalid panel/slot IDs → reject / no-op
- Arrangement / Live / unknown targets → reject
- Repeated identical accepted moves → no ratio/geometry drift (ratios stay in #694 owner)

## Intent boundary (for #1071 / #1073)

Python exposes distinct intent kinds so QML can separate:

| Kind | Meaning |
|------|---------|
| `panel_move` | Docking relocation of a materialized Edit panel |
| `panel_swap` | Explicit swap of two materialized panels |
| `panel_reflow` | Compact reflow after materialization change |
| `resize` | Elastic divider / size (not docking) |
| `collapse` / `reveal` | Visibility presentation (not docking) |
| `sample_drag` | Internal sample DnD (#1072/#1073); Python contract in `WORKBENCH_INTERNAL_SAMPLE_DND_CONTRACT.md` |
| `waveform_click` | Audition / selection |
| `focus` | Keyboard / focus navigation |

This slice ships the typed command/state underlay only.

## Persistence / migration

- Document: `edit_docking_topology.json` under `workbench_state_dir()`
- Schema: integer `schema_version` + `lock_state` + `panel_order`
- Fail closed to canonical Edit layout on corrupt / duplicate / NaN / unknown IDs
- Legacy `livekit` → `live_kit`; legacy rack/sequencer IDs dropped (no empty cavity)
- Migration never changes musical Kit/Pattern/session state
- Arrangement/Live layout is not stored in this schema

## Non-goals

QML docking UI (#1071), sample DnD (#1072/#1073), Arrangement QML (#1080),
later Live UI, floating windows, widget/plugin systems, audio/Pattern engine
changes, final default visual layout redesign.
