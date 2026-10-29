---
name: sample-brain-qml-component-test
description: >
  Use when designing focused component-level tests for Sample Brain PySide6 /
  Qt Quick / QML behavior — signals, focus, pointer arbitration, Loader
  lifecycle, async Python→QML projection, or ListView reuseItems virtualization
  — instead of relying only on Python adapter or static QML string checks.
---
<!--
Canonical Skill Source: docs/skills/sample-brain-qml-component-test/SKILL.md
Surface: cursor
Sync Status: mirrored-from-canon
Last Verified: 2026-10-29
Drift Policy: Cursor mirrors must match the canonical skill body.
-->

# Sample Brain QML Component-Test Skill

## Purpose

Teach agents to design the **smallest useful QML component-level test** for real
Sample Brain QML behavior. Close the recurring gap where Python adapter unit
tests and `QML_SOURCE` substring asserts are green while a QML regression in
gesture arbitration, focus, Popup/Loader lifecycle, async projection, or
virtualized delegates remains unguarded.

Architecture contract (never dilute):

```text
Python/Core/Controller/Audio/Catalog = authoritative product/session/musical state
QML                                 = projection + presentation + typed user intent
```

Do not bless duplicated QML product authority. Route to Python tests when the
behavior belongs to Python.

## When To Activate

Activate when the task is to **design or write tests** for a surface that
materially includes any of:

- embedded `QML_SOURCE` / `.qml` / Qt Quick interaction behavior
- QML signals / bridge intents that must fire exactly once
- pointer gesture arbitration or hit zones
- keyboard / focus navigation involving QML items
- async authoritative-state projection from Python into QML
- Loader / component lifecycle
- `ListView` / `reuseItems` / pooled delegate reuse
- selection vs `sample_context_target` (or equivalent presentation target)
- presentation-only interactions that must **not** mutate product state

Do **not** activate for pure:

- Python domain / BPM / catalog filter / SQLite / music theory / DSP
- controller logic with no QML-specific gesture, focus, lifecycle, or projection
- screenshot-primary visual acceptance (use the Screen-1 visual-acceptance path)
- native audio hard-real-time validation

If activation is unclear, prefer a short non-activation note over inventing a
QML test.

## Method

```text
CLASSIFY AUTHORITY + LAYER
→ NAME THE QML FAILURE MODE
→ COMPACT TEST DESIGN (output contract)
→ REUSE EXISTING HARNESS
→ COMPANION LAYERS + NON-GOALS
```

### 1. Classify authority + layer

Explicitly choose **one** primary layer (or `mixed` with a named split):

| Layer | Owns |
|-------|------|
| `qml_component` | QML gesture, focus, signal, Popup/Loader, virtualized delegate behavior |
| `python_unit` | Pure Python domain / adapter API with no QML event path |
| `python_contract` | Frozen Python/JSON/SQLite/schema contracts |
| `integration` | Multi-module Python seams without requiring QML input |
| `runtime_smoke` | Coarse window smoke; not a substitute for focused component coverage |
| `mixed` | Python authority assertion **plus** QML event path (common for Screen-1) |

**Decision rule:** if a green Python adapter call or a `QML_SOURCE` string
presence assert would still miss the QML failure mode, the primary layer is
`qml_component` or `mixed` — not `python_unit` alone.

### 2. Name the QML failure mode

Pick the smallest relevant family (examples from live Screen-1):

| Family | Typical miss without this skill |
|--------|----------------------------------|
| Signal exactly-once intent | Adapter invoked once in Python; QML MouseArea/Keys/Accessible double-fire untested |
| Pointer arbitration | Right-click / drag threshold / hit-zone; static `RightButton` substring treated as proof |
| Keyboard / focus | Focus hand-off to Popup; restore on close; Menu vs pointer index source |
| Async projection | Model/property update asserted before QML frame settle; sleeps instead of condition waits |
| Loader lifecycle | Source/component swap; stale handlers after unload |
| Virtualized reuse | `reuseItems` + pooled/stale delegate state; assuming persistent delegate identity |
| Selection vs context target | Python `sample_context_target` covered; QML right-click without `selectRow` not covered |
| Relational geometry | Magic absolute `x/y`; prefer invariants vs siblings/anchors |
| Presentation-only | Hover/hint chrome mutates selection, kit, BPM, or other product state |

### 3. Compact test design (required output)

Return this block for the target behavior:

```text
Behavior/authority:
Why QML component coverage required:
Layer decision: qml_component | python_unit | python_contract | integration | runtime_smoke | mixed
Fixture/boundary:
Inputs/events:
Observable assertions:
Async/wait strategy:
Lifecycle/virtualization:
Companion tests:
Non-goals:
```

Rules for each field:

- **Behavior/authority** — name the user-visible behavior and which side owns
  product state (almost always Python).
- **Why QML component coverage required** — one concrete failure the Python-only
  path would miss.
- **Fixture/boundary** — prefer existing harness:
  `build_screen1_visual_fixture_v1` /
  `build_qml_view_model_from_fixture` /
  `Screen1QmlInteractionAdapter` /
  `_qml_engine` / `_settle_qml_frame` /
  `PySide6.QtTest.QTest` (`mouseClick`, `keyClick`, `qWaitForWindowExposed`).
  Do **not** invent a parallel QML test framework.
- **Inputs/events** — real QML events (right-click at mapped scene point, Menu
  key, Escape) rather than only bridge method calls, when the defect lives in
  QML arbitration.
- **Observable assertions** — intent lists / bridge signal counts, selection
  index, `sample_context_target`, focus properties, model projections. Prefer
  relational geometry over pixel-perfect screenshots.
- **Async/wait strategy** — prefer condition / signal waits
  (`processEvents` loops, property predicates, short `qWait` only as last
  resort polish). Prefer settling one frame over fixed long sleeps.
- **Lifecycle/virtualization** — if `reuseItems` / Loader / pooling is in play,
  state what must clear on pool/reuse and forbid persistent delegate identity.
- **Companion tests** — Python unit/contract that still own adapter/domain
  authority (do not delete them).
- **Non-goals** — screenshot-primary acceptance, audio clock tests, product
  feature work inside this skill, QML product-authority duplication.

### 4. Working example (prefer one excellent case)

**Behavior:** right-click unselected Browser row B → Add to Kit → exactly one
Add-to-Kit intent for B; selection stays on A. Menu/Shift+F10 opens context for
the **selected** index. Contract:
`docs/WORKBENCH_SAMPLE_CONTEXT_MENU_CONTRACT.md`.

**Why QML component required:** adapter
`open_sample_context` / `request_context_add_to_kit` and static `RightButton`
asserts stay green while the QML `MouseArea` / Popup / Keys path is wrong.

**Layer:** `mixed` — QML events + Python/bridge intent observation.

**Fixture:** Screen-1 visual fixture → view model → interaction adapter →
`_qml_engine`; show window; settle frame.

**Events:** `QTest.mouseClick(..., Qt.RightButton, ...)` on row B scene point;
click `contextAddToKitItem` (or activate focused action via Return after focus);
separately `QTest.keyClick(..., Qt.Key_Menu)` with focus on `browserList`.

**Assertions:** `addToKitIntent` / callback length == 1; path/row identity is B;
`selected_browser_index` unchanged on right-click open; Menu path uses selected
index; Escape / close restores browser focus without product mutation from hover.

**Wait:** `_settle_qml_frame` / `processEvents` until Popup visible / intent
observed — not a multi-second sleep.

**Virtualization:** do not cache a QQuickItem delegate pointer across scroll as
row identity; re-find by `objectName` / scene mapping after reuse.

**Companions:** keep
`tests/test_workbench_qml_sample_context_menu_839.py` adapter contracts.

**Non-goals:** screenshot diffs; audition audio; rewriting context-menu product
features.

See committed validation evidence under
`docs/skills/sample-brain-qml-component-test/evidence/` and the focused pattern
test `tests/test_qml_component_context_menu_pattern_1305.py`.

### 5. Counterexample routing

When the behavior is pure Python domain (BPM normalization, catalog filter,
SQLite schema, music-theory ranking, DSP, controller math with no QML event
path), output:

```text
Layer decision: python_unit | python_contract | integration
Why QML component coverage NOT required: <one sentence>
Route: existing Python tests / sample-brain-test-first
```

Do not force a QML component test for authority that QML must only project.

## Reuse Before Build

Verify live PySide6 / Qt versions in the active environment. Reuse
`src/workbench_qml.py` helpers (`_qml_engine`, `_settle_qml_frame`,
`qml_runtime_available`) and existing pytest + `QTest` patterns under `tests/`.
Do not assume Qt APIs newer than the installed stack. Add a new helper only when
an existing stack cannot express the case, the gap is demonstrated, and the
helper is a thin wait/find utility — never a second test framework.

## Stop Conditions

- Behavior belongs entirely to Python → do not activate; route to Python tests.
- Cause of a symptom is unknown → `sample-brain-root-cause` first.
- Known defect needs a guard plan → `sample-brain-regression-gap`, then
  `sample-brain-test-first` for implementation order.
- Request demands screenshot-only acceptance → Screen-1 visual-acceptance path;
  this skill may still design non-screenshot component companions.
- Evidence would require private samples, DBs, caches, credentials, or
  machine-local paths → stop; use synthetic fixtures only.

## Relationships

**Standalone Guarantee:** `standalone: true`

This skill does **not** require `sample-brain-qml-review` or
`sample-brain-skill-effectiveness` at runtime.

### Can Receive From

- `sample-brain-test-first` — when TEST_GATE needs a QML component layer choice
- `sample-brain-regression-gap` — when the missing guard is QML-interaction shaped
- `sample-brain-qml-review` — optional; findings may motivate a component test
- issue / defect note naming a QML interaction failure

### Route If

| Condition | Target | Required | Notes |
|-----------|--------|----------|-------|
| `pure_python_domain` | Python unit/contract tests | Yes | Explicit non-activation |
| `guard_missing_after_design` | `sample-brain-regression-gap` | No | When only the gap is known |
| `approved_product_impl` | `sample-brain-test-first` | Yes | This skill designs tests; freeze/implement elsewhere |
| `qml_authority_smell` | `sample-brain-qml-review` | No | Review, do not silently move authority into QML |
| `visual_accept_needed` | `workflow-screen1-visual-acceptance` | No | After automated component coverage |

### When to STOP

- Non-QML surface (`NOT_ACTIVATED`)
- Private runtime data required
- Scope expands into product feature work or a new test framework

### Cycle Rules

No loop that rewrites the same design after `sample-brain-test-first` without a
new failure mode. Re-enter only when the QML interaction surface or contract
materially changed.
