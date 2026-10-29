# Screen-1 Elastic Coupled Layout (#694)

Parent: [#691](https://github.com/jannekbuengener/sample-brain/issues/691).
Depends on: [#692](https://github.com/jannekbuengener/sample-brain/issues/692) density / minimum geometry (DONE).
Shared states: [#700](https://github.com/jannekbuengener/sample-brain/issues/700) / [`WORKBENCH_VISUAL_ACCEPTANCE.md`](WORKBENCH_VISUAL_ACCEPTANCE.md).
Clean Start visibility: [#693](https://github.com/jannekbuengener/sample-brain/issues/693) / [`WORKBENCH_CLEAN_START.md`](WORKBENCH_CLEAN_START.md).
Panel disclosure / collapse geometry: [#1204](https://github.com/jannekbuengener/sample-brain/issues/1204)
(historical origin [#845](https://github.com/jannekbuengener/sample-brain/issues/845), parent [#844](https://github.com/jannekbuengener/sample-brain/issues/844)).

## Authority

On Startup / Density / Panel geometry / Persistence conflicts:

`scoped #691 child (#694) > #691 > #700 > historical #503/#564 fixed-width geometry`

On Active-Source **panel disclosure** / collapse geometry / residual workspace:

`scoped #1204 > this elastic layout visibility contract > #694 drag geometry`

#564 remains authoritative for Harmonic Match toggle / anchor / focus / finder.
#694 supersedes #564 **only** for fixed pixel restore-width geometry.
#1204 owns the unified hairline disclosure primitive and collapse projection for
true horizontal Edit/Screen-1 panels (Library / Browser / Harmonic Matches).
Live Kit is **not** a horizontal collapsible panel peer; drawer/HUD authority
(`toggleLiveKitDrawer`, #1077/#1207) owns its open/close presentation.
Historical #845 remains origin/evidence for presentation flags and
Matches ⊂ Browser rules; it is not current chrome/geometry authority.

## Product goal

Visible Screen-1 panes form one **coupled elastic workspace**. Dragging a
divider redistributes width across panels on both sides. Direct neighbours
move most; farther panels compensate weaker. The surface must feel continuous,
not like independent splitters.

## Scope of the solver

Panels with stable IDs (fixed order — no reordering in this slice):

| ID | Role |
|----|------|
| `library` | Source navigation |
| `browser` | Sample Browser (highest crush protection) |
| `harmony` | Harmonic Match (optional / toggle) |

Live Kit is vertical drawer/HUD geometry (#908/#1077), not a horizontal elastic
panel. Legacy `livekit` ratio keys migrate away on load.

Elastic coupled drag applies when the **active workspace** is materialised
(`has_active_source`):

- 2-panel: `library | browser` (+ residual when Browser collapsed — #1204)
- 3-panel: `library | browser | harmony`

Clean Start / No-Source presentation does **not** run coupled elastic drag.
Calm Canvas / residual workspace is not a weighted persisted panel.

No-Source presentation (#693 / #725):

- Collapsed Clean Start: Library width `0` (not materialised); Calm Canvas fills.
- Opened-no-source (`library_revealed=True`): fixed Library preferred width
  (presentation only); still **no** elastic drag and **no** ratio writes.
- `#725` `library_revealed` is No-Source presentation only. When
  `has_active_source=True`, this solver alone owns geometry.

## Canonical state

Persisted truth = **relative panel weights (ratios)**, never pixel widths.

Canonical default (sums to 1.0):

```text
library  0.18
browser  0.50
harmony  0.18
livekit  0.14
```

Rules:

- Ratios must be finite and strictly positive.
- Visible panels are normalised against the available content width after
  subtracting handle widths.
- Window resize recomputes pixel widths from the same ratios; it does **not**
  rewrite stored ratios.
- Hidden Harmony may keep its last valid ratio internally; it does not occupy
  width while closed.
- Open/Close Harmony renormalises visible panels deterministically with **no
  ratio drift** across repeated toggles.

## Drag semantics

Divider between left panel set L and right panel set R:

- Drag `+delta` (rightward): L gains `+delta`, R loses `delta` (or vice versa).
- Within each side, allocation weight decays with distance from the divider.
- Default decay feel-factor: `0.55` (not a user setting; Owner runtime may retune).
- Direct neighbour weight > farther same-side panel weight.
- Resulting ratios stay finite, positive, and renormalisable.

## Constraints and Browser priority

Each panel has: id, ratio, min width, optional max width, visibility,
resize priority / elasticity.

Saturation loop:

1. Clamp panels that hit min/max.
2. Redistribute remaining delta only onto still-flexible panels.
3. Iterate until absorbed or no flexible receiver remains.
4. Never emit negative width, overlap, NaN, or Inf.

**Browser** has the highest protection priority. Optional panels may reach their
compact minima before Browser is forced below its usable minimum.

Hard minima (logical px / DIP, first baseline; density-aware):

| Panel | Min width |
|-------|-----------|
| library | 230 |
| browser | 480 |
| harmony | 280 |
| livekit | 220 |

Handle strip: visual thin divider; hit target wider. Default handle width charged
against content width: `6` DIP per visible handle.

## Responsive fallback

If `available_width < sum(visible minima) + handle_budget`:

- enter explicit fallback mode `proportional_min_overflow`;
- assign widths proportional to each visible panel's min width, scaled to fit;
- never rely on accidental QML compression.

## Persistence (ratios only)

New Screen-1 layout preference file (not Tk view-settings):

- filename: `screen1_layout_preferences.json` under the Workbench state dir;
- schema version: `1`;
- fields: `schema_version`, `panel_ratios`.

Write policy: persist on drag-end (or debounced commit), not every mouse move.

Corrupt / NaN / Inf / unknown panel IDs → fail closed to canonical defaults.

Persistence **must not** restore by itself:

- active Source, Browser selection, Harmonic open/anchor/results;
- Live Kit visibility under Clean Start;
- Preview / Transport / scroll.

Those remain #693 Clean Start / #696 Display Preferences Startup Preset
territory ([`WORKBENCH_DISPLAY_PREFERENCES.md`](WORKBENCH_DISPLAY_PREFERENCES.md)).
**Reset Layout** (restore canonical ratios without mutating library data) is a
#696 product action that writes through this solver's preference path.

## Architecture

- Pure-Python layout solver owns ratios, drag, clamp, fallback, persistence IO.
- QML is a thin projection + pointer intent layer (preferred widths, handles).
- QML must not become a second layout authority.
- No domain / audio work on the drag path.

## Panel disclosure + collapse geometry (#1204)

Active-Source pane collapse is **presentation state only**. It feeds the same
solver visibility inputs as other disclosure flags; it does not reset domain
data and does not add a second layout authority.

Historical #845 established presentation flags and Matches ⊂ Browser validity.
#1204 is the current owner for disclosure chrome and collapse **projection**.

### Ownership

| Pane | Ownership | Collapse semantics |
|------|-----------|--------------------|
| Browser | Main Active-Source surface | OPEN / COLLAPSED |
| Harmonic Matches | Extension of the Browser area (`Matches ⊂ Browser`) | OPEN / COLLAPSED |
| Library | Source navigation; Clean Start reveal `#725` | reveal / hide (same hairline disclosure style) |
| Live Kit | Drawer / HUD (#1077); **not** a horizontal panel peer | drawer open/close via `toggleLiveKitDrawer` |

### Residual workspace (Browser COLLAPSED)

When Browser is collapsed:

- Browser width = 0 and Harmony is closed / not visible
- Library keeps a **bounded** width from stored absolute panel ratios
- Freed space becomes **residual workspace** (canvas remainder) — not a new
  persisted panel and not a fourth layout authority
- Stored `panel_ratios` are **not** rewritten by collapse or reopen
- Reopen restores Browser from the same stored ratio truth (no drift)

Collapse must not renormalize Library to ~100% of available width merely
because Browser is hidden.

### Unified hairline disclosure

True horizontal collapsible panels share one quiet disclosure primitive:

- visible seam ≈ 1 DIP (`theme.dividerDefault`)
- pointer hit area ≈ 6–10 DIP
- chevron / indication only on hover, focus, or active state
- `PointingHandCursor`; keyboard Enter/Space + Accessible name/role
- no permanent chunky reopen tab
- no stacked/double/triple borders from pane border + handle + separator

### Presentation flags (session-transient)

- `browser_collapsed` — Browser presentation; does not clear selection / rows
- `harmonic_match_open` — existing Matches open flag (OPEN when true)
- `live_kit_drawer_open` / drawer shims — Live Kit drawer presentation
- `live_kit_materialized` — progressive disclosure (#742); **must not** flip
  false solely because the drawer was closed

Solver visibility (Active Source):

- `browser_visible = not browser_collapsed`
- `harmony_open` only when Matches are OPEN **and** Browser is OPEN
- Live Kit does **not** allocate horizontal elastic width (#908)

Collapse is never persisted by #1204. Existing ratio persistence stays ratios-only.
Display-preference `panel_visibility` (#696) is an adjacent seam and is **not**
extended by this slice.

### State preservation

| Surface | On collapse / reopen |
|---------|----------------------|
| Browser | Selection preserved; scroll/view only as existing contracts already keep |
| Harmonic Matches | Reference + results preserved; no rematch solely due to collapse |
| Live Kit | Slots / content preserved; materialization flag unchanged |

Disclosure activation must not mutate sample selection, audition, favorite,
kit slot, or harmony product state.

### Fachlich gültige Kombinationen

Not every boolean tuple is valid. Ownership forbids Matches OPEN while Browser
is COLLAPSED.

| Browser | Matches | Valid? |
|---------|---------|--------|
| OPEN | OPEN | yes |
| OPEN | COLLAPSED | yes |
| COLLAPSED | COLLAPSED | yes |
| COLLAPSED | OPEN | **invalid** — force Matches COLLAPSED |

Rules:

- Collapsing Browser **must** force Matches presentation COLLAPSED.
- Reopening Browser does **not** auto-reopen Matches; Matches reopen only via
  their own disclosure / existing toggle.
- Live Kit drawer open/close is independent of horizontal panel disclosure.
- Every valid COLLAPSED horizontal panel keeps a reachable reopen path
  (quiet edge disclosure + keyboard). Hover may emphasize the affordance
  but must not be the only operable path.

### Disclosure vs resize intents

Disclosure seams are **click/activate** controls (`PointingHandCursor`).
Elastic panel dividers (`elasticHandleAfter*`) and Browser column resize (#780)
remain **drag** controls (`SizeHorCursor` / `layoutModel.applyDrag`).

- Distinct `objectName`s and hit areas; no shared MouseArea that both drags and
  collapses.
- No modifier-key as a hidden intent split.
- #1204 does not redesign divider/column-resize chrome (#1211 is separate).
- [#846](https://github.com/jannekbuengener/sample-brain/issues/846) owns calming
  permanent column dividers / ephemeral resize styling afterward.
- [#843](https://github.com/jannekbuengener/sample-brain/issues/843) uses the
  **existing** Harmonic Matches pane as a Browser extension.
  Close/reopen presentation for Matches uses the #1204 disclosure primitive;
  collapsing Matches must preserve the current harmony anchor/results.

### Non-goals (#1204)

- New docking / reordering / free-canvas architecture
- New persistence architecture for collapse flags
- #1211 Browser column geometry / #1210 hover-hint sweep
- #1207 Live Kit HUD product redesign (beyond removing false panel chrome)
- Matching algorithm / Browser column data projection changes
- Audio, BPM/Key, Step Sequencer, Arrangement

## Non-scope

- Panel reordering / docking / free canvas
- Live Kit visual redesign
- Screen 2
- Audio / matching / catalog domain changes
- #725 collapsed First View / reveal affordance (No-Source presentation only;
  does not invent a second ratio model)
- #846 divider / resize visual calming (follow-up)
- #843 Harmonic Matches context open/retarget + header entry removal (separate;
  reuses this elastic Matches pane; does not redefine collapse)

## Validation contracts (minimum)

1. Ratios finite, positive, normalisable
2. Sum(visible panel widths) + handles + residual workspace = available content width
3. Direct neighbour reacts stronger than farther same-side panel
4. Min saturation redistributes residual delta among **open elastic** panels
5. ≥1000 deterministic drag steps: no relevant ratio drift
6. Window resize preserves ratios
7. 3↔4 panel toggle stable
8. Harmony open/close without drift
9. Drag-end persist + restart restore (ratios only)
10. Corrupt / NaN / Inf / unknown IDs fail closed
11. Browser keyboard / Search focus / Esc remain intact
12. #1204 / #845: valid OPEN/COLLAPSED combinations only; Browser COLLAPSED ⇒ Matches COLLAPSED
13. Collapse preserves Browser selection, Matches reference/results, Live Kit content
14. Live Kit materialization unchanged by drawer open/close
15. Disclosure keyboard-activatable; quiet reopen affordance reachable
16. Disclosure hit-areas do not share drag intent with elastic/column resize
17. #1204: Browser collapse keeps Library bounded; residual workspace absorbs freed width
18. #1204: collapse/reopen does not mutate stored panel ratios; reopen is drift-free
19. #1204: no generic Live Kit horizontal panel-disclosure chrome

Runtime acceptance sizes: 1600×900, 1280×720, 1120×640; Harmony open/closed;
Browser collapse/reopen; 100% / 125% / 150% DPI.
Agent visual/runtime acceptance required before merge
(see `WORKBENCH_VISUAL_ACCEPTANCE.md` operative rule).
