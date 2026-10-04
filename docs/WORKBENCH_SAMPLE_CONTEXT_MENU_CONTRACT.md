# Workbench Sample Context Menu Contract (#839 / #840 / #843)

**Status:** ACTIVE_SUPPORTING (Screen-1 child of #838)  
**Issues:** [#839](https://github.com/jannekbuengener/sample-brain/issues/839)
(menu + stable target — delivered),
[#840](https://github.com/jannekbuengener/sample-brain/issues/840)
(Browser Add-to-Kit via context menu only — delivered),
[#843](https://github.com/jannekbuengener/sample-brain/issues/843)
(context Harmonic Matches open/retarget + header producer-entry removal)  
**Parent UX meta:** [#838](https://github.com/jannekbuengener/sample-brain/issues/838)  
**Matching authority (delivered):**
[#842](https://github.com/jannekbuengener/sample-brain/issues/842)  
**Collapse/reopen presentation (delivered):**
[#845](https://github.com/jannekbuengener/sample-brain/issues/845)  
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
| Harmonic matching domain | #842 — `HarmonicMatchLibraryController` / `find_harmony_matches` |
| Harmonic panel open/retarget | #843 — adapter `open_harmonic_matches_for_row` |
| Harmonic collapse/reopen chrome | #845 — panel handles; not context menu |
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
open_harmonic_matches_for_row(row: WorkbenchRow) -> bool
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

### #840 — Context menu is the sole visible Browser Add-to-Kit route

Supersedes the temporary #839 coexistence clause
(“#839 keeps the visible per-row Add-to-Kit chrome. Removal belongs to #840.”).

After #840:

- The Sample Context Menu is the **only** visible Browser Add-to-Kit route.
- Visible per-row Browser Add-to-Kit chrome is removed
  (`addButton` / `addButtonMouse`, `"+ Add"` / `"+ Add to Kit"` labels,
  and any row call to `window.interaction.addToKit(index)`).
- Trailing Browser Add-column presentation geometry is removed with the action:
  no `browserAddColumnWidth`, no `effectiveBrowserAddColumnWidth`, no header
  Add-column spacer, and no empty reserved Add column in rows. Freed width is
  absorbed by the existing fill-width Sample Name / Browser layout.
- Stable Python `sample_context_target` remains target authority.
- Existing Add-to-Kit domain seam
  (`_request_add_to_kit_row` / Live Kit pending / assign / replace / cancel)
  remains reused — #840 builds no second kit domain.
- Index-based `request_add_to_kit(index)` / bridge `addToKit(index)` may remain
  as non-visible harness/API seams when tests need them; they must not form a
  competing visible Browser row route.
- Harmonic Matches **result-row** `addHarmonyToKit(index)` is a separate surface
  and remains unchanged.

## Harmonic Matches — context open/retarget (#843)

Central producer entry for Harmonic Matches is the Sample Context Menu action
`Harmonic Matches`. The header producer-zone control `harmonicMatchButton` is
**removed** structurally (not `visible: false`); its slot must not remain as an
empty phantom. Internal presentation helpers such as
`activateHarmonicMatchToggle()` / `toggleHarmonicMatch()` /
`toggle_harmonic_match()` may remain when #845 collapse/reopen or internal
tests still need them — #843 removes the visible header entry point, not every
method containing the word toggle.

### Authoritative Python seam (single open/retarget authority)

```text
open_harmonic_matches_for_row(row: WorkbenchRow) -> bool
```

Owned by `Screen1QmlInteractionAdapter`. It:

1. accepts a concrete stable `WorkbenchRow` (context target B, not selection)
2. reuses the existing `HarmonicMatchLibraryController` (one controller)
3. calls `set_anchor(row, browser candidates)` so prior results invalidate
4. projects anchor / results / status into the existing Matches presentation
5. opens the existing Harmonic Matches pane (Browser → Matches → Live Kit)
6. does **not** change Browser selection
7. does **not** start preview / audition
8. contains no new matching domain (still #842 authority)
9. respects `Matches ⊂ Browser` (#845): fail-closed while Browser is collapsed

Semantics are **OPEN / RETARGET**, never panel toggle:

| Prior panel state | Context action for B | Result |
|-------------------|----------------------|--------|
| closed | context B | OPEN for B |
| open for A | context B | stays OPEN; atomic RETARGET to B |
| open for B | context B | stays OPEN; no accidental close |

Closing / reopening Matches presentation remains sole ownership of #845 panel
handles. Context action must not invent a second X / ON/OFF / close control.

### Context intent routing

```text
request_context_harmonic_matches()
  → require sample_context_target B
  → if on_context_harmonic_match_requested is set:
        callback(B)                            # harness/injection override
     else:
        open_harmonic_matches_for_row(B)       # default production authority
  → close_sample_context()
  → return B
```

Production session composition (`compose_workbench_session`) constructs the
adapter with `HarmonicMatchLibraryController` and leaves
`on_context_harmonic_match_requested` unbound (`None`). The adapter default
seam is the production bind — no fragile constructor-order closure required.

`request_context_harmonic_matches()` must **not** call `toggle_harmonic_match()`.
Legacy `toggle_harmonic_match()` may internally reuse
`open_harmonic_matches_for_row` for its selection-based open path when tests or
#845 still need toggle close/open, but context never routes through toggle.

### Lifecycle separation

| Identity | Lifecycle |
|----------|-----------|
| `sample_context_target` | Cleared after the Harmonic context action (#839) |
| Harmony controller anchor | Remains B after the action; independent of context clear |

### Focus

Context action originates from a Popup. After activation:

- Popup closes
- Browser selection stays A
- Browser context receives a sensible focus return
- Opening/retargeting Matches must **not** auto-`forceActiveFocus()` onto the
  results list solely because the panel opened
- Matches remains normally reachable later via Tab / explicit focus
- ↑/↓ Browser navigation and Esc Preview Stop stay protected

### Matching boundary (#842)

Root-only visible keys (for example Browser `"G"`) remain fail-closed for
Harmonic Match when no modeful authoritative key exists; display text must not
be fabricated into `Gmaj`/`Gmin`. Ineligible/empty/error still open the panel
for the concrete reference with truthful status and stable geometry. See
`docs/product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md` §9.1 and §9.2.

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

## Non-goals

### Owned by #840 (this contract slice)

- Remove visible Browser row Add-to-Kit chrome and Add-column geometry
- Keep Context Popup `Add to Kit` + `contextAddToKit()` as the Browser route
- Preserve Live Kit domain semantics via the shared seam

### Still out of scope here

- Matching relation/scoring / eligibility algorithm changes → #842 / #847/#848
- New Matches close/X/ON/OFF chrome → forbidden; #845 owns collapse
- New docking / reordering / tabs / modal / second Matches window
- Harmonic result-row Add-to-Kit redesign
- Live Kit domain redesign / slot UX redesign
- Browser column reordering or #846 resize seam changes
- Extra menu commands (Rename/Delete/Favorite/…)
- Persistenz, audio engine, Step Sequencer, Arrangement

## Validation

Automated interaction/source contracts freeze target identity, lifecycle,
intent dispatch, keyboard/focus, theme semantics, and #845/#846 non-regression
markers. Agent-owned visual acceptance
([`WORKBENCH_VISUAL_ACCEPTANCE.md`](WORKBENCH_VISUAL_ACCEPTANCE.md)) applies
after product implementation — not as a substitute for this freeze.
