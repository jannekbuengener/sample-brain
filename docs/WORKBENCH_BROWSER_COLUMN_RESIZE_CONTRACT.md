# Workbench Browser Column Resize Contract (#780)

**Status:** ACTIVE_SUPPORTING (Screen-1 child of #691)
**Issue:** [#780](https://github.com/jannekbuengener/sample-brain/issues/780)
**Builds on:** [#767](WORKBENCH_BROWSER_COLUMN_ARRANGEMENT_CONTRACT.md) column
order, [#692] compact density, [#781] alternating row shading.
**Renderer:** `LOCK_PYSIDE6_QML` — all work lives in `src/workbench_qml.py`
(`QML_SOURCE`). Tkinter remains legacy/fallback only.

## Product goal

Give the Screen-1 Browser **very subtle vertical column separators** with a
**directly draggable resize handle** per resizable column:

- visible divider line ~1 DIP, low contrast (reuses `theme.dividerDefault`);
- a **wider invisible hit target** than the visible line;
- horizontal resize cursor (`Qt.SizeHorCursor`) on hover;
- dragging updates only the dragged column + the elastic Name column;
- no accidental Row Selection, Audition, Favorite toggle, or Add-to-Kit while
  resizing.

Default column order is unchanged (owned by #767):
`Waveform → Sample Name → BPM → Favorite → Key → Length`.

## One owner for column width state

`browserPane` is the single owner of Browser column geometry. It already
computed the shared `effectiveBrowser*` widths consumed by **both** the header
row and the list delegate; #780 keeps that single source of truth and only adds
mutable runtime overrides folded into the same `effectiveBrowser*` bindings.

- Runtime overrides live on `browserPane`: `waveformUserWidth`, `metaUserWidth`,
  `favoriteUserWidth`, `lengthUserWidth` (sentinel `-1` = responsive default).
- `browserPane.resizeColumn(role, deltaPx)` is the **only** writer; it clamps to
  deterministic `[min, max]` and writes exactly one override.
- QML handles only **forward pointer intent** to `resizeColumn`; they never
  compute a second width truth.
- Header and delegate keep reading `browserPane.effectiveBrowser*` unchanged, so
  column geometry stays shared (no competing truth).

Browser-column resize is **independent** of panel resize (`layoutModel`). The
two never share state.

## Resizable columns and dividers

Dividers/handles are rendered **inside the row delegate** (not the header). All
rows share one delegate, so the vertical separators align perfectly down the
list and stay virtualization-safe (`reuseItems: true`, no per-row model growth).
The header label row keeps its existing layout: the header and the data rows use
different trailing column structures (the delegate carries an optional `type`
column the header never had under #767/#776), so painting header dividers would
not line up with the data grid. Dividers therefore live where alignment is
guaranteed: the data rows.

Each resizable column paints a 1-DIP line at its right edge with a wider
`MouseArea` hit target that owns the pointer (`preventStealing`, accepted press)
and shows `Qt.SizeHorCursor`:

| Divider (right edge of) | Resizes width role        | Effect |
|-------------------------|---------------------------|--------|
| Waveform                | `waveform`                | Name absorbs |
| BPM                     | `meta` (BPM **and** Key)  | Name absorbs; **sole interactive meta handle** |
| Favorite                | `favorite`                | Name absorbs |
| Key                     | *(visual-only)*           | No `MouseArea`; geometry follows BPM via shared `meta` |
| Length                  | `length`                  | Name absorbs |

BPM and Key share the existing `effectiveBrowserMetaColumnWidth` role (#767) and
stay a matched meta pair. **Only the BPM divider is interactive** for `meta`: a
second Key handle calling `resizeColumn("meta", Δ)` would double-apply Δ onto
Name and desync handle tracking. The Key divider remains a subtle visual
separator only. `type` and `Add-to-Kit` are not resizable. The elastic Name
column (`Layout.fillWidth`) absorbs every change, so only adjacent geometry
moves.

While `browserNarrowColumns` (`width < 700`), `_resolveColumn` **ignores**
runtime `*UserWidth` overrides and keeps the #692 narrow responsive defaults.
Overrides apply again when the pane returns to wide mode.

## Minimum / maximum widths (deterministic)

Named, centralized on `browserPane`; no new inline magic numbers:

| Role     | Min | Max | Default (normal) |
|----------|-----|-----|------------------|
| Waveform | `window.browserWaveformMin` (140) | 360 | 180 |
| Meta     | 40  | 96  | 48 |
| Favorite | 24  | 48  | 28 |
| Length   | 52  | 120 | 62 |

Mins equal the existing narrow-mode fallback widths, so narrow layouts
(`width < 700`) keep working. Waveform keeps a usable minimum; Name stays the
most flexible text column; BPM/Favorite/Key/Length keep readable minimums.
`1120×640` and `1600×900` must stay usable.

## Interaction safety

The resize `MouseArea` sits above the row/waveform/favorite/add surfaces
(`z` above them), uses `preventStealing: true`, and accepts press/release so a
resize drag can never trigger Row Selection, Waveform Audition, Favorite toggle,
Add-to-Kit, or Harmonic Match.

## Persistence seam (V1 = runtime-only)

#780 ships **deterministic runtime resize only**. Column widths reset to
responsive defaults on relaunch. No new settings/persistence subsystem is added.
A future small follow-up may persist the four `*UserWidth` overrides through the
existing display-preference contract
([#696](WORKBENCH_DISPLAY_PREFERENCES.md)); `WORKBENCH_DISPLAY_PREFERENCES.md`
is the intended seam. This slice does not implement it.

## Non-scope

- Column reordering, sorting/filter redesign, spreadsheet grid.
- Header-cell drag handles or header/row column-structure realignment
  (pre-existing #767/#776 concern).
- Panel docking/reordering (#697), DnD (#768), Theme (#785), Brand/Motion
  (#786), Screen 2/3, packaging, general Settings redesign.
- Width persistence (documented seam only).

## Validation

- Structural QML invariants in `tests/test_workbench_qml_browser_chrome.py`
  (dividers present, theme token, wider hit target, resize cursor, one owner,
  deterministic mins, shared header/row geometry, preserved intents,
  `reuseItems: true`).
- Real PySide6/QML runtime evidence at `1600×900` and `1120×640`, including a
  synthetic divider drag, captured **outside** the repository.
- Owner Visual Acceptance remains separate from agent self-attestation.
