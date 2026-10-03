# Workbench Browser Column Resize Contract (#780 / #846)

**Status:** ACTIVE_SUPPORTING (Screen-1 child of #691)
**Issues:** [#780](https://github.com/jannekbuengener/sample-brain/issues/780) (width authority),
[#846](https://github.com/jannekbuengener/sample-brain/issues/846) (presentation supersession)
**Parent UX meta:** [#844](https://github.com/jannekbuengener/sample-brain/issues/844)
**Builds on:** [#767](WORKBENCH_BROWSER_COLUMN_ARRANGEMENT_CONTRACT.md) column
order, [#692] compact density, [#781] alternating row shading.
**Adjacent (do not restructure):** [#845](WORKBENCH_ELASTIC_LAYOUT.md) panel
presentation collapse / mid-edge handles.
**Renderer:** `LOCK_PYSIDE6_QML` — all work lives in `src/workbench_qml.py`
(`QML_SOURCE`). Tkinter remains legacy/fallback only.

## Authority / supersession

| Layer | Owner |
|-------|--------|
| Width math, mins/maxes, narrow/wide, Name absorber | **#780** (unchanged) |
| Visual presentation of column dividers / resize chrome | **#846** supersedes #780 presentation |

Same contract file. No parallel authority document.

**#846 supersedes** the #780 presentation that required:

- permanent ~1-DIP vertical column dividers in Browser row delegates;
- resize `MouseArea`s inside each virtualized row;
- validation that assumed permanent row dividers.

**#846 preserves** the #780 width authority and role table below.

## Product goal (#846)

Quiet Sample-Browser surface — not a spreadsheet grid:

```text
calm surface -> header -> on demand ephemeral resize handle
```

instead of:

```text
permanent vertical column dividers through every row
```

- Normal state: **no** permanent vertical column dividers (header or rows).
- Horizontal row dividers and alternating row shading (#781 / density) stay.
- Column resize remains fully functional via header-owned ephemeral surfaces.
- Header titles and content alone provide orientation in the quiet state.

## One owner for column width state (#780 — preserved)

`browserPane` is the single owner of Browser column geometry. Shared
`effectiveBrowser*` widths are consumed by **both** the header row and the list
delegate.

- Runtime overrides live on `browserPane`: `waveformUserWidth`, `metaUserWidth`,
  `favoriteUserWidth`, `lengthUserWidth` (sentinel `-1` = responsive default).
- `browserPane.resizeColumn(role, deltaPx)` is the **only** writer; it clamps to
  deterministic `[min, max]` and writes exactly one override.
- QML header resize surfaces only **forward pointer intent** to `resizeColumn`;
  they never compute a second width truth.
- Header and delegate keep reading `browserPane.effectiveBrowser*` unchanged.

Browser-column resize is **independent** of panel resize (`layoutModel`) and of
#845 panel presentation collapse.

## Resizable roles (unchanged)

| Right edge of | Resizes width role | Interactive? |
|---------------|--------------------|--------------|
| Waveform | `waveform` | yes |
| BPM | `meta` (BPM **and** Key) | **sole** interactive meta writer |
| Favorite | `favorite` | yes |
| Key | *(follows meta)* | **no** resize surface / no second `meta` writer |
| Length | `length` | yes |
| Type / Add-to-Kit | — | not resizable |

BPM and Key share `effectiveBrowserMetaColumnWidth`. A second Key handle calling
`resizeColumn("meta", Δ)` would double-apply Δ onto Name. `type` and Add-to-Kit
are not resizable. The elastic Name column (`Layout.fillWidth`) absorbs deltas.

While `browserNarrowColumns` (`width < 700`), `_resolveColumn` **ignores**
runtime `*UserWidth` overrides and keeps the #692 narrow responsive defaults.

## Presentation (#846) — header-owned ephemeral overlays

### Geometry ownership (critical)

Resize surfaces are **Overlay / edge children of the respective header cell**,
not additional `RowLayout` siblings that consume layout width.

Frozen geometry rules:

- Each surface sits on the **right edge** of its header cell.
- It must **not** affect `Layout.preferredWidth`, `Layout.minimumWidth`, or
  `RowLayout` spacing of the header.
- Visible handle and pointer hit-area are **overlay geometry** only.
- After resize, Waveform / BPM / Favorite / Length header edges remain exactly
  aligned with the corresponding data-row columns (same `effectiveBrowser*`).

### Ephemeral visibility

For each interactive role (`waveform`, `meta`, `favorite`, `length`):

- Quiet default: handle invisible / extremely discreet.
- **Hover**: visible resize handle on the header cell’s right edge.
- **Focus-visible** (Tab): visible resize handle (not hover-only).
- **Active drag**: handle stays visible; continuous resize via `resizeColumn`.
- After leave / blur / drag end: return to quiet default.

Visible handle may be slim; hit-area stays comfortably larger
(`browserColumnHandlePadding` style padding). Cursor: `Qt.SizeHorCursor`.
Pointer surfaces use `preventStealing` so resize never triggers row selection,
audition, favorite, or add-to-kit.

Stable `objectName`s (header overlays):

- `browserColumnResize_waveform`
- `browserColumnResize_meta` (BPM cell; sole meta writer)
- `browserColumnResize_favorite`
- `browserColumnResize_length`

Row delegates must **not** declare `browserColumnDivider_*` vertical column
dividers or column-resize `MouseArea`s / `SizeHorCursor` for these roles.

### Theme tokens

Handle chrome uses existing Theme Core semantics only:

- Hover / quiet elevated affordance: existing surface/divider semantic tokens
  (not a new local palette).
- Focus-visible ring: `theme.focusRing` (or the existing equivalent focus
  semantic already owned by Theme Authority).
- No new HEX literals in #846 handle chrome.
- `theme.dividerDefault` may still appear for **horizontal** row chrome; it is
  **not** proof of column-resize presentation under #846.

## Accessibility / keyboard (#846)

- Resize surfaces are Tab-focusable and show the handle under focus-visible.
- They must **not** hijack Browser ↑/↓, Esc, or selection key flows.
- Do **not** intercept Arrow / Space / Enter on these surfaces unless a defined
  resize action exists — #846 does **not** implement keyboard pixel-resize.
- Do **not** advertise Accessible Splitter / Slider roles while keyboard resize
  is unimplemented (no faux operable keyboard resize).
- #845 collapse keyboard activation remains separate (`PointingHandCursor`,
  Return/Space on collapse handles only).

## Minimum / maximum widths (deterministic — preserved)

Named, centralized on `browserPane`; no new inline magic numbers:

| Role     | Min | Max | Default (normal) |
|----------|-----|-----|------------------|
| Waveform | `window.browserWaveformMin` (140) | 360 | 180 |
| Meta     | 40  | 96  | 48 |
| Favorite | 24  | 48  | 28 |
| Length   | 52  | 120 | 62 |

`1120×640` and `1600×900` must stay usable.

## Persistence seam (V1 = runtime-only — preserved)

Deterministic runtime resize only. Column widths reset to responsive defaults on
relaunch. No new settings/persistence subsystem. Future persistence may use the
display-preference seam ([#696](WORKBENCH_DISPLAY_PREFERENCES.md)); this contract
does not implement it.

## Non-scope

- #845 panel collapse / reopen affordances / presentation flags
- #843 Harmonic Match embed / context menu
- #850 Length/Type/BPM/Key data projection or header field reordering
- Column reordering, sorting/filter redesign, spreadsheet grid
- Panel docking/reordering (#697), DnD, Screen 2/3, packaging
- Theme-Core redesign; Browser column geometry must not move into Theme Authority
- Width persistence (documented seam only)
- Full keyboard column-resize (arrow-key pixel mutation) — Owner decision required
  before any future slice invents it

## Validation

- Structural QML invariants in `tests/test_workbench_qml_browser_chrome.py`
  (#846 header overlays, no permanent vertical row column dividers, ownership,
  mins, shared geometry, intents, `reuseItems: true`).
- Theme wiring: `tests/test_workbench_qml_theme_runtime.py` asserts width
  authority + semantic handle/focus tokens (not permanent divider presence).
- Protected: #845 panel collapse suite; elastic / progressive disclosure /
  compact density as applicable.
- Real PySide6/QML runtime evidence at `1600×900` and `1120×640` (quiet /
  hover / focus / drag), captured **outside** the repository.
- Agent visual/runtime acceptance owns closure; see
  `WORKBENCH_VISUAL_ACCEPTANCE.md` operative rule.
