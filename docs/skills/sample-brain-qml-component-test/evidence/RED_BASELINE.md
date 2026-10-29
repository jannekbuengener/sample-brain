# RED baseline — `sample-brain-qml-component-test` (#1305)

**Status:** recorded before the skill existed  
**Capability set used:** generic test-design habits + existing Python adapter /
static QML string patterns only (no `sample-brain-qml-component-test`)  
**Repo head at capture:** `origin/main` =
`c5c5877eb899303fde0bbed84f2502fbf81d094d`  
**Live architecture anchors (not fabricated):**

- `src/workbench_qml.py` embedded `QML_SOURCE` — Browser `ListView` with
  `reuseItems: true`, right-click `MouseArea` →
  `browserPane.openSampleContextMenu(index, …)`, Menu/Shift+F10 key path uses
  `window.screenData.selectedBrowserIndex`, Popup `sampleContextMenu` activates
  via MouseArea / Keys / Accessible into `contextAddToKit()` /
  `contextHarmonicMatches()`, `ListView.onPooled` clears presentation hover
  owners only.
- Python authority: `Screen1QmlInteractionAdapter.sample_context_target` +
  `docs/WORKBENCH_SAMPLE_CONTEXT_MENU_CONTRACT.md`.
- Existing coverage that *looks* sufficient without a QML component layer:
  - `tests/test_workbench_qml_sample_context_menu_839.py` — adapter unit /
    contract (open keeps selection; exactly-once Add-to-Kit via Python API;
    stable row object vs reshuffled indices).
  - Static `QML_SOURCE` string asserts for `Qt.RightButton`, `Key_Menu`,
    `objectName: "sampleContextMenu"`.
  - `tests/test_workbench_qml_interactions.py` smoke calls
    `bridge.openSampleContext` / `bridge.contextAddToKit` — **not** a real
    pointer/keyboard path through QML gesture arbitration.
  - `tests/test_workbench_context_hint_770.py` opens context via bridge and
    mutates hint state in Python — does not QTest right-click a delegate.

## Prompt given to the unskilled agent

> Design the smallest useful automated coverage for this Screen-1 regression
> risk: right-click an **unselected** browser row, choose **Add to Kit**, and
> require exactly one Add-to-Kit intent for that row while selection stays on
> the previously selected row. Also cover Menu / Shift+F10 opening context for
> the **selected** index. Reuse the live PySide6 / QTest harness if needed.

## Inadequate design produced without the skill

| Field | Unskilled answer |
|-------|------------------|
| Layer choice | **Python unit / adapter only** (+ optional static QML substring asserts) |
| Fixture | `build_screen1_visual_fixture_v1` + `Screen1QmlInteractionAdapter` |
| Inputs/events | `adapter.select_row(0)`; `adapter.open_sample_context(1)`; `adapter.request_context_add_to_kit()` |
| Assertions | `added == [row_b]`; `selected_browser_index == 0`; `QML_SOURCE` contains `RightButton` / `Key_Menu` |
| Async/wait | none (synchronous Python) |
| Lifecycle/virtualization | ignored (`reuseItems` / pooled hover / deferred UI paths not mentioned) |
| Companion | none |
| Non-goals | none stated |

This design **already passes today** on main via
`test_context_add_to_kit_dispatches_exactly_once_for_target_while_selection_stays`
and the static QML presence asserts. It therefore falsely signals coverage.

## What was missed (the real gap)

1. **Wrong layer for QML gesture arbitration.** Adapter calls skip the QML
   `MouseArea` right-click path that must open context for `index` **without**
   calling `selectRow`, the Popup focus hand-off, and the menu item
   MouseArea/Keys/Accessible activation that ends in `contextAddToKit()`.
2. **Exactly-once intent at the QML boundary.** Python
   `request_context_add_to_kit()` once ≠ proving one QML activation path does
   not double-fire (mouse + Accessible, or Return after click) into the bridge.
3. **Selection vs context-target under real pointer input.** Contract requires
   right-click on row B while selection stays on A. Only a QML component /
   runtime interaction test can show the right-click handler returns early
   without `selectRow(index)`.
4. **Keyboard vs pointer index source.** Menu/Shift+F10 uses
   `selectedBrowserIndex`; right-click uses delegate `index`. Unskilled design
   never distinguishes those entry points.
5. **Virtualization / presentation hygiene omitted.** Browser ListView uses
   `reuseItems: true` and `ListView.onPooled` clears hover owners. Unskilled
   design does not require any pooled-reuse / presentation-only assertion, so
   stale hover or identity mistakes remain unguarded at the component layer.
6. **Brittle / unnecessary alternatives not rejected.** Pixel screenshots or
   full e2e audio were not proposed here, but static string presence of
   `RightButton` was treated as behavioral proof — it is not.

## Rationalization observed

“The adapter already owns `sample_context_target` and has exactly-once tests;
QML only forwards bridge slots, so Python unit tests are enough.” That
rationalization is exactly what the specialist skill must interrupt: QML owns
gesture arbitration, focus, Popup lifecycle, and virtualized delegate identity
at the moment of intent.

## Verdict of RED pass

`GENERIC_TEST_DESIGN_INCOMPLETE` — Python/static coverage green while a
realistic QML component regression (pointer/focus/exactly-once bridge intent)
remains untested.

## Same inputs required for GREEN

GREEN must redesign coverage for the **same** regression prompt without
renaming the defect, and must select a **QML component / mixed** layer that
drives real QML pointer (and distinguishes keyboard Menu) events with
observable exactly-once intent + selection invariance.
