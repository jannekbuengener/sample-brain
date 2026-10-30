# Browser Column Reorder + Resize Arbitration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver #1292: deterministic Browser header-column reordering while preserving #1211 independent resize behavior, Browser virtualization, and all product/audio intents.

**Architecture:** Keep `browserPane` as the single Browser column-layout authority. Add one runtime-only ordered identity list and project it into both header and ordinary row cells through `GridLayout + Layout.column`; existing per-role width properties remain attached to logical identities. Header body drag uses a bounded threshold and non-overlapping hit regions so the existing separator resize MouseAreas always win.

**Tech Stack:** Python 3.12, PySide6 / Qt Quick QML, QtQuick.Layouts, pytest.

**Spec:** `docs/WORKBENCH_BROWSER_COLUMN_RESIZE_CONTRACT.md` plus live GitHub issue #1292 and MagicPath revision `466430376995328000`.

## Global Constraints

- Work only in `feat/1292-browser-column-reorder`; no direct push to `main`.
- Runtime-only column order; no new persistence schema.
- `browserPane` remains the only column layout authority.
- Width overrides stay bound to logical identities, never visual indices.
- Separator/boundary hit zone always owns resize; body drag owns reorder only after threshold.
- No selection, audition, Favorite, Kit, Harmonic Match, Loop, DB, filesystem, analysis, or audio mutation from reorder/resize.
- Preserve `reuseItems: true`, #1285 Loop projection, #1281 waveform hover, and #1211 resize behavior.
- Default visible identity label is `DATEINAME`.
- No new sorting semantics or misleading sort control.
- Windows 100/125/150% and narrow supported widths remain coherent.

## Review Focus

- Dragging across a hidden TYPE column in narrow mode must not corrupt the canonical full order.
- Delegate reuse after reorder must not restore declaration-order/stale cell positions.
- Resize handles must continue to win at boundaries even after columns move.
- Width overrides must follow their role after repeated reorder/resize cycles.
- Loop-owner inline rows must remain full-width and unaffected while ordinary rows reorder below/above them.

---

### Task 1: Canonical column-order authority and shared projection

**Files:**
- Modify: `src/workbench_qml.py`
- Modify: `tests/test_workbench_qml_browser_chrome.py`
- Create: `tests/test_workbench_qml_browser_column_reorder_1292.py`

**Interfaces:**
- Consumes: existing `browserPane.*UserWidth`, `effectiveBrowser*Width`, `browserNarrowColumns`, #1285 ordinary `rowBody`.
- Produces: `browserPane.browserColumnOrder`, `browserPane.visibleBrowserColumnIndex(role)`, `browserPane.moveBrowserColumn(role, targetRole, after)`.

- [ ] Write structural failing tests proving one canonical order list, default order `waveform, filename, bpm, favorite, key, length, type`, `DATEINAME`, and shared `Layout.column` projection in header + ordinary rows.
- [ ] Run focused tests and observe RED.
- [ ] Add runtime-only order helpers on `browserPane`; replace header and ordinary-row `RowLayout` with `GridLayout` while retaining the existing cell implementations and per-role width bindings.
- [ ] Give header/row cells stable object names needed for runtime geometry tests.
- [ ] Run focused structural + #1211/#1285 regressions and observe GREEN.
- [ ] Commit: `feat(#1292): add canonical Browser column order projection`.

### Task 2: Header drag threshold and resize/reorder arbitration

**Files:**
- Modify: `src/workbench_qml.py`
- Modify: `tests/test_workbench_qml_browser_column_reorder_1292.py`
- Modify: `tests/test_workbench_qml_browser_column_resize_1211.py`

**Interfaces:**
- Consumes: Task 1 order helpers and existing header resize MouseAreas.
- Produces: header-body reorder MouseAreas `browserColumnReorder_<role>` and deterministic scene-X target mapping.

- [ ] Write failing tests for sub-threshold no-op, header-body drag reorder, separator drag resize-only, and zero product/audio intents.
- [ ] Run focused tests and observe RED.
- [ ] Add reorder body hit areas below the existing resize overlays; exclude separator geometry from reorder hit zones and use a bounded 8 DIP threshold.
- [ ] Reorder live by crossing header-cell center points; commit only canonical order changes, no Python/domain round-trip.
- [ ] Run runtime gesture + #1211 resize suites and observe GREEN.
- [ ] Commit: `feat(#1292): arbitrate Browser header reorder and resize gestures`.

### Task 3: Runtime geometry, virtualization, narrow-mode, and interaction regressions

**Files:**
- Modify: `tests/test_workbench_qml_browser_column_reorder_1292.py`
- Modify only if required by failing evidence: `src/workbench_qml.py`

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: exact runtime evidence that header/rows move together and role widths survive reorder.

- [ ] Add runtime tests for header/row geometry after moving BPM/WAVEFORM/TYPE, width identity retention, repeated reorder+resize drift, narrow-mode hidden TYPE behavior, delegate reuse, keyboard navigation, and #1285 Loop-owner coexistence.
- [ ] Run tests and observe any RED before fixes.
- [ ] Make only evidence-required fixes.
- [ ] Run #1292 + #1211 + #1281 + #1285 + Browser chrome/component suites and observe GREEN.
- [ ] Commit: `test(#1292): prove Browser reorder runtime invariants`.

### Task 4: Exact-head acceptance, review, PR, and merge

**Files:**
- Create/update runtime evidence only if repository convention requires it.
- Reconcile: #1292 / #1269 after successful runtime acceptance.

**Interfaces:**
- Consumes: completed implementation branch.
- Produces: `BROWSER_COLUMN_REORDER_RUNTIME_PASS` evidence.

- [ ] Run QML specialist component/test-run/review skills; profile only if evidence shows churn/relayout risk.
- [ ] Run relevant broad pytest, lint/format/types, and `git diff --check`.
- [ ] Run exact-head Windows visual/runtime checks at 100/125/150% and narrow width against MagicPath `466430376995328000`.
- [ ] Perform whole-branch review and repair any Important/Critical finding with RED→GREEN coverage.
- [ ] Push branch, open PR with `Closes #1292`, wait for required checks/review, repair in-scope failures, then squash-merge when green.
- [ ] Verify merged `main`, #1292 closure, and reconcile #1269 with PR/Merge/runtime evidence.

Exit: `BROWSER_COLUMN_REORDER_RUNTIME_PASS`
