# Workbench Sample Context Menu Contract (#839)

**Status:** ACTIVE_SUPPORTING (Screen-1 child of #838)  
**Issue:** [#839](https://github.com/jannekbuengener/sample-brain/issues/839)  
**Parent UX meta:** [#838](https://github.com/jannekbuengener/sample-brain/issues/838)  
**Downstream (do not implement here):**
[#840](https://github.com/jannekbuengener/sample-brain/issues/840) (row Add-to-Kit removal),
[#843](https://github.com/jannekbuengener/sample-brain/issues/843) (Harmonic panel bind),
[#842](https://github.com/jannekbuengener/sample-brain/issues/842) (matching/eligibility repair)  
**Renderer:** `LOCK_PYSIDE6_QML` — presentation lives in `src/workbench_qml.py`
(`QML_SOURCE`). Python Core/Controller/Audio/Catalog remain authoritative.
Tkinter remains legacy/fallback only.

## Product goal

Right-click (or keyboard context-open) on a Browser sample row opens a compact
wine-red context surface with exactly two actions for **the opened sample**:

- `Add to Kit`
- `Harmonic Matches`

Central invariant:

```text
Browser selection = Sample A
User opens context on Sample B
→ menu target = B
→ selection remains A
→ no preview / audition / select_row(B)
→ menu actions dispatch for B
```

## Authority

| Layer | Owner |
|-------|--------|
| Stable context target identity | Python `Screen1QmlInteractionAdapter` |
| Browser selection | Existing selection seams (unchanged by open) |
| Add-to-Kit domain / slot assign | Existing Live Kit seams (reuse; no new kit domain) |
| Harmonic matching / panel open | #842 / #843 — not #839 |
| Theme tokens | Theme Core / QML semantic facade |
| QML presentation | Thin intent + themed Popup chrome only |

QML must not hold authoritative target identity in a virtualized delegate.
`browserList` keeps `reuseItems: true`.

## Frozen Python API (single authority — no aliases)

```text
sample_context_target: WorkbenchRow | None
open_sample_context(index: int) -> WorkbenchRow
close_sample_context() -> None
request_context_add_to_kit() -> WorkbenchRow
request_context_harmonic_matches() -> WorkbenchRow
```

Rules:

- No second property alias such as `context_sample`.
- `open_sample_context(index)` resolves the visible row at `index` to a concrete
  `WorkbenchRow` **exactly once** and stores that object in
  `sample_context_target`.
- After open, actions use `sample_context_target` only. They must **not**
  re-resolve through a stored or reconstructed browser index.
- State is session-/presentation-transient. No persistence.

### QML bridge (presentation only)

```text
openSampleContext(index)
closeSampleContext()
contextAddToKit()
contextHarmonicMatches()
```

Bridge slots forward intents to the adapter. Do not expose a second QML-owned
copy of the domain `WorkbenchRow`. Presentation-only properties may exist when
needed (for example open/focus flags), but target identity remains Python-owned.

## Add to Kit

`request_context_add_to_kit()` dispatches exactly one Add-to-Kit intent for
`sample_context_target`.

Shared internal seam (implementation direction after freeze):

```text
_request_add_to_kit_row(row: WorkbenchRow) -> WorkbenchRow
```

Then:

```text
request_add_to_kit(index)
  → resolve current visible row at index
  → _request_add_to_kit_row(row)

request_context_add_to_kit()
  → require sample_context_target
  → _request_add_to_kit_row(sample_context_target)
```

One Add-to-Kit domain/intent semantics path. Context must never call
`request_add_to_kit(old_index)` after open, because filter/reload/virtualization
can change which sample occupies that index.

#839 keeps the visible per-row Add-to-Kit chrome. Removal belongs to #840.

## Harmonic Matches intent

`request_context_harmonic_matches()` dispatches exactly one target-bound intent
for `sample_context_target` through:

```text
on_context_harmonic_match_requested: Callable[[WorkbenchRow], object] | None
```

(or an equivalent registered adapter intent seam).

#839:

- dispatches B
- does not change Browser selection
- does **not** call `toggle_harmonic_match()`
- does not compute matches
- does not open/fix the Matches panel
- does not mutate key/eligibility/matching domain

#843 binds this intent to the authoritative matching/panel path.
#839 keeps the header `harmonicMatchButton`. Removal/replacement belongs to #843.

## Lifecycle and invalidation

Clear `sample_context_target` (and close the presentation) when:

- an action completes
- Escape closes the menu
- click/press outside closes the menu
- a different row is opened (previous target must not remain)
- Browser projection changes before the next open:
  - scope replacement
  - rows replacement
  - search/filter projection (`set_browser_search_query` / `setBrowserSearch`)
  - Clean Start / fail-closed workspace reset

No context target may silently survive a visible Browser re-projection.
Do not keep a hidden/stale menu target valid across search changes.

## Opening semantics

| Input | Target | Selection | Preview / audition |
|-------|--------|-----------|--------------------|
| Right-click row B | B | unchanged | none |
| Context-Menu key / Shift+F10 | currently selected row | unchanged | none |

Opening is non-selecting and non-previewing.
Keyboard open must give the menu sensible focus and a visible focus state.
↑/↓ inside the open menu navigate menu entries only.
Escape closes and returns focus to the Browser / triggering context.
Do not permanently hijack global Browser key flows.

## Visual / theme

Prefer a fully Theme-driven Qt Quick Controls `Popup` / custom popup surface.
Do **not** rely on native platform `Menu` chrome if that yields light default
styling or non-deterministic platform appearance.

Frozen presentation behaviour (not a mandate for native `MenuItem` types):

- wine-red semantic surface via Theme Authority only
- no HEX literals in new context-menu chrome
- compact, lightly rounded, two actions, fine divider
- focus-visible state
- keyboard navigation
- Escape close
- click-outside close
- focus return after close

Preferred semantic bindings:

| Role | Token |
|------|--------|
| Background | `theme.selectionSurface` |
| Text | `theme.textPrimary` / `theme.textSecondary` |
| Accent / selected entry | `theme.selectionBorder` or `theme.actionActive` |
| Focus | `theme.focusRing` |
| Divider | existing semantic divider token |
| Hover | existing hover/elevated token if compatible with the red surface |

No new local palette. Portfolio mockups deleted on `main` (#863/#864) are
**not** dependencies and must not be restored for this contract.

## #839 non-goals

- Removing visible row Add-to-Kit chrome → #840
- Removing header Harmonic Match button → #843
- Matching/eligibility repair → #842
- Harmony panel layout/embed → #843
- Extra menu commands (Rename/Delete/Favorite/…)
- Persistenz, audio engine, Step Sequencer, Arrangement, docking/reordering

## Validation

Automated interaction/source contracts freeze target identity, lifecycle,
intent dispatch, keyboard/focus, theme semantics, and #845/#846 non-regression
markers. Agent-owned visual acceptance
([`WORKBENCH_VISUAL_ACCEPTANCE.md`](WORKBENCH_VISUAL_ACCEPTANCE.md)) applies
after product implementation — not as a substitute for this freeze.
