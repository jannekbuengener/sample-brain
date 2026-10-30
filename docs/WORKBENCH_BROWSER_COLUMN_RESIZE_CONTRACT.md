# Workbench Browser Column Layout Contract (#1211 / #1292)

**Status:** ACTIVE_SUPPORTING (Screen-1 child of #691)
**Issues:** [#1211](https://github.com/jannekbuengener/sample-brain/issues/1211) (resize authority),
[#1292](https://github.com/jannekbuengener/sample-brain/issues/1292) (runtime column-order / gesture-arbitration authority),
[#780](https://github.com/jannekbuengener/sample-brain/issues/780) / [#846](https://github.com/jannekbuengener/sample-brain/issues/846) (historical evidence)
**Parent UX meta:** [#844](https://github.com/jannekbuengener/sample-brain/issues/844)
**Builds on:** [#767](WORKBENCH_BROWSER_COLUMN_ARRANGEMENT_CONTRACT.md) column
order, [#692] compact density, [#781] alternating row shading.
**Adjacent (do not restructure):** [#1204](WORKBENCH_ELASTIC_LAYOUT.md) panel
disclosure seams / residual workspace geometry (supersedes historical #845 chrome
assumptions for panel collapse ownership).
**Renderer:** `LOCK_PYSIDE6_QML` — all work lives in `src/workbench_qml.py`
(`QML_SOURCE`). Tkinter remains legacy/fallback only.

## Authority / supersession

| Layer | Owner |
|-------|--------|
| Independent per-column width overrides + pointer-direction invariant | **#1211** |
| Canonical runtime column order + reorder/resize pointer arbitration | **#1292** |
| Width math shell, mins/maxes, narrow/wide, Name absorber | #780 foundation, reconciled by #1211 |
| Visual presentation of column dividers / resize chrome | #846 presentation, preserved by #1211 |

Same contract file. No parallel authority document.

**#1211 supersedes** the historical #780/#846 width-role freeze where it
conflicts:

- BPM + KEY no longer share a single mutable `meta` width;
- KEY is independently resizable;
- TYPE is independently resizable;
- interactive resize roles are no longer capped at the historical four-role
  `meta` table.

Historical #780/#846 evidence remains valid for ephemeral header-owned handles,
`browserPane` single geometry authority, narrow-mode override ignore, and
interaction isolation — but not for coupled `meta` / non-resizable KEY/TYPE.

**#846 presentation preserved:** quiet default → hover/focus reveals subtle
handle → active drag keeps handle visible → leave/blur/end returns quiet. No
permanent spreadsheet vertical grid.

## Product goal

Quiet Sample-Browser surface — not a spreadsheet grid:

```text
calm surface -> header -> on demand ephemeral resize handle
```

- Normal state: **no** permanent vertical column dividers (header or rows).
- Horizontal row dividers and alternating row shading (#781 / density) stay.
- Column resize remains fully functional via header-owned ephemeral surfaces.
- Each visible data column that is user-resizable owns an independent override.

## One owner for column layout state

`browserPane` is the **only** Browser column geometry/order authority.

```text
one user override per resizable column
        ↓
one effective width per column
        ↓
header + all row delegates consume exact same effective width
```

- Runtime overrides on `browserPane` (sentinel `-1` = responsive default):
  `waveformUserWidth`, `bpmUserWidth`, `favoriteUserWidth`, `keyUserWidth`,
  `lengthUserWidth`, `typeUserWidth`.
- Matching effective widths: `effectiveBrowserWaveformWidth`,
  `effectiveBrowserBpmColumnWidth`, `effectiveBrowserFavoriteColumnWidth`,
  `effectiveBrowserKeyColumnWidth`, `effectiveBrowserLengthColumnWidth`,
  `effectiveBrowserTypeColumnWidth`.
- `browserPane.resizeColumn(role, deltaPx)` is the **only** writer; it clamps to
  deterministic `[min, max]` and mutates **exactly one** override.
- Resize of column A must not rewrite unrelated user overrides.
- No Python-side width map and no second parallel QML width authority.
- Header and virtualized delegates read the same `browserPane.effectiveBrowser*`.
- `browserColumnOrder` is the one runtime-only ordered list of logical identities:
  `waveform`, `filename`, `bpm`, `favorite`, `key`, `length`, `type`.
- Header + ordinary row cells project that same list through
  `visibleBrowserColumnIndex(role)` / `Layout.column`; widths remain attached to
  the logical role, never the visual index.
- `moveBrowserColumn(role, targetRole, after)` is the only reorder writer.

Browser-column resize/reorder is **inner** Browser geometry. Panel resize / disclosure
(`layoutModel`, `PanelDisclosureSeam`, #1204) is **outer** workspace geometry.
No shared MouseArea and no shared state authority.

## Resizable roles (#1211)

| Right edge of | Resizes width role | Interactive? | objectName |
|---------------|--------------------|--------------|------------|
| Waveform | `waveform` | yes | `browserColumnResize_waveform` |
| BPM | `bpm` | yes | `browserColumnResize_bpm` |
| Favorite | `favorite` | yes | `browserColumnResize_favorite` |
| Key | `key` | yes | `browserColumnResize_key` |
| Length | `length` | yes | `browserColumnResize_length` |
| Type | `type` | yes (hidden in narrow mode) | `browserColumnResize_type` |

The historical `browserColumnResize_meta` name is **retired** after BPM/KEY
decoupling — it must not remain as a misleading meta authority.

Sample Name (`Layout.fillWidth`) absorbs residual free space. It must not
silently rewrite other columns' user overrides. When the pane cannot honor a
drag, clamp the **grabbed** column only.

While `browserNarrowColumns` (`width < 700`), `_resolveColumn` **ignores**
runtime `*UserWidth` overrides and keeps the #692 narrow responsive defaults.
Stored/runtime overrides must survive window resize (no wipe on narrow entry).

## Pointer direction invariant

Horizontal pointer X is the resize intent authority:

```text
pointer +X  →  positive width delta for the grabbed role
pointer -X  →  negative width delta for the grabbed role
```

Coordinate handling uses one stable space per drag (global/scene X via
`mapToItem(null, …)`):

```text
pressX / currentX / delta = currentX - previousX
```

Do not mix shifting local coordinate systems across GridLayout reflow mid-drag.

### Boundary geometry (Name absorber)

Column order: Waveform → Sample Name (flex) → BPM → FAV → KEY → LENGTH → TYPE.

- **Waveform** (left of Name): growing moves the grabbed right edge **+X** with
  pointer +X (Name shrinks from the left).
- **Columns right of Name:** with a single left-side flex absorber, growing only
  that column keeps its grabbed right edge **stable** while Name shrinks; the
  width still follows the pointer sign. The grabbed boundary must **never** move
  opposite the pointer.

The historical mirrored BPM drag was caused by BPM+KEY sharing one `meta`
override: `+Δ` grew two columns, Name absorbed `2Δ`, and the BPM right edge moved
by `−Δ`. Independent `bpm` / `key` overrides remove that inversion.

## Presentation — header-owned ephemeral overlays (#846 preserved)

Resize surfaces are **overlay / edge children** of the header cell, not
additional `GridLayout` siblings that consume layout width.

- Anchored to the **right edge** of the header cell.
- Must **not** declare `Layout.preferredWidth` / `Layout.minimumWidth` on the
  resize surface itself.
- Quiet default; visible on hover / focus-visible / active drag.
- Hit-area wider than the visible hairline (`browserColumnHandlePadding`).
- Cursor: `Qt.SizeHorCursor`. `preventStealing: true`.
- Row delegates must **not** host resize `MouseArea`s / `SizeHorCursor` /
  permanent vertical column dividers for these roles.

### Theme tokens

Handle chrome uses existing Theme Core semantics only (`theme.surfaceElevated`,
`theme.focusRing`, …). No new HEX literals in handle chrome.

## Reorder + resize gesture arbitration (#1292)

Header pointer ownership is deterministic:

- separator/right-edge hit zone -> resize;
- header body/label -> reorder only after the `8 DIP` drag threshold;
- resize overlays (`z: 8`) outrank reorder body surfaces (`z: 4`);
- sub-threshold press/release is a reorder no-op;
- reorder uses stable scene X and header-cell centers, not delegate indices;
- WAVEFORM participates in reorder/resize and exposes the visible `WAVEFORM`
  label but no invented sort-arrow semantics;
- the sample identity label is `DATEINAME`;
- moving columns changes presentation only: no selection, audition, Favorite,
  Add-to-Kit, Harmonic Match, Loop, analysis, DB, filesystem, or audio mutation.

## Accessibility / keyboard

- Resize surfaces are Tab-focusable and show the handle under focus-visible.
- They must **not** hijack Browser ↑/↓, Esc, or selection key flows.
- No faux Accessible Splitter / Slider keyboard resize in this slice.
- #1204 disclosure keyboard activation remains separate (`PointingHandCursor`).

## Minimum / maximum widths (deterministic)

Named, centralized on `browserPane`; no new inline magic numbers in delegates:

| Role     | Min | Max | Default (normal) |
|----------|-----|-----|------------------|
| Waveform | `window.browserWaveformMin` (140) | 360 | 180 |
| BPM      | 40  | 96  | `window.browserMetaColumnWidth` (48) |
| Favorite | 24  | 48  | 28 |
| Key      | 40  | 96  | `window.browserMetaColumnWidth` (48) |
| Length   | 52  | 120 | 62 |
| Type     | 48  | 88  | `window.browserTypeColumnWidth` (72) |

`1120×640` and `1600×900` must stay usable. Clamp never mutates foreign
`*UserWidth` values.

## Interaction isolation

Resize/reorder must not trigger: selection, audition, Favorite, Add-to-Kit,
Harmonic Matches intent, Loop intent, Browser panel resize, or #1204 disclosure.

## Persistence seam (V1 = runtime-only)

Deterministic runtime resize + reorder only. Column widths and column order reset
to responsive/default order on relaunch. No new settings/persistence subsystem. Future persistence may use the
display-preference seam ([#696](WORKBENCH_DISPLAY_PREFERENCES.md)); this contract
does not implement it.

## Non-scope

- #1210 context hints
- #1204 panel disclosure redesign
- #843 Harmonic Match embed / context menu product changes
- sorting/filter redesign, spreadsheet grid
- Panel docking/reordering, DnD, Screen 2/3, packaging
- Theme-Core redesign; width persistence; full keyboard column-resize

## Validation

- Structural QML invariants in `tests/test_workbench_qml_browser_chrome.py`
  (#1211 independent roles, ephemeral overlays, shared geometry, intents,
  `reuseItems: true`).
- Runtime geometry probe (PySide6/QML) for pointer-sign / boundary direction
  and independence (BPM/KEY/TYPE at minimum).
- #1292 pointer/geometry/identity coverage in
  `tests/test_workbench_qml_browser_column_reorder_1292.py`, including real
  `QTest` body/edge drags, shared header/row order, repeated reorder+resize
  cycles, and narrow projection.
- Exact-head Windows 100/125/150% evidence via
  `tools/screen1_browser_column_reorder_1292_evidence.py`.
- Theme wiring: `tests/test_workbench_qml_theme_runtime.py`.
- Protected: #1204 panel disclosure suite; elastic / progressive disclosure /
  compact density as applicable.
- Agent visual/runtime acceptance owns closure; see
  `WORKBENCH_VISUAL_ACCEPTANCE.md` operative rule.
