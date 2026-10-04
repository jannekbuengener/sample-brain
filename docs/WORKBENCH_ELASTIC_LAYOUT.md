# Screen-1 Elastic Coupled Layout (#694)

Parent: [#691](https://github.com/jannekbuengener/sample-brain/issues/691).
Depends on: [#692](https://github.com/jannekbuengener/sample-brain/issues/692) density / minimum geometry (DONE).
Shared states: [#700](https://github.com/jannekbuengener/sample-brain/issues/700) / [`WORKBENCH_VISUAL_ACCEPTANCE.md`](WORKBENCH_VISUAL_ACCEPTANCE.md).
Clean Start visibility: [#693](https://github.com/jannekbuengener/sample-brain/issues/693) / [`WORKBENCH_CLEAN_START.md`](WORKBENCH_CLEAN_START.md).
Presentation collapse / mid-edge handles: [#845](https://github.com/jannekbuengener/sample-brain/issues/845) (parent [#844](https://github.com/jannekbuengener/sample-brain/issues/844)).

## Authority

On Startup / Density / Panel geometry / Persistence conflicts:

`scoped #691 child (#694) > #691 > #700 > historical #503/#564 fixed-width geometry`

On Active-Source **presentation collapse** / mid-edge reopen handles:

`scoped #845 > this elastic layout visibility contract > #694 drag geometry`

#564 remains authoritative for Harmonic Match toggle / anchor / focus / finder.
#694 supersedes #564 **only** for fixed pixel restore-width geometry.
#845 owns OPEN/COLLAPSED presentation for Browser, Harmonic Matches, and Live Kit
pane visibility; it does **not** redesign elastic drag or column resize.

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
| `livekit` | Live Kit geometry only (no redesign) |

Elastic coupled drag applies when the **active workspace** is materialised
(`has_active_source`):

- 3-panel: `library | browser | livekit`
- 4-panel: `library | browser | harmony | livekit`

Clean Start / No-Source presentation does **not** run coupled elastic drag.
Calm Canvas is not a weighted panel in the solver.

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

## Presentation collapse (#845)

Active-Source pane collapse is **presentation state only**. It feeds the same
solver visibility inputs as other disclosure flags; it does not reset domain
data and does not add a second layout authority.

### Ownership

| Pane | Ownership | Collapse semantics |
|------|-----------|--------------------|
| Browser | Main Active-Source surface | OPEN / COLLAPSED |
| Harmonic Matches | Extension of the Browser area (`Matches ⊂ Browser`) | OPEN / COLLAPSED |
| Live Kit | Independent right pane | OPEN / COLLAPSED once materialized |

Library / Clean Start reveal (`#725`) remains a separate No-Source contract.

### Presentation flags (session-transient)

- `browser_collapsed` — Browser presentation; does not clear selection / rows
- `harmonic_match_open` — existing Matches open flag (OPEN when true)
- `live_kit_collapsed` — Live Kit presentation **after** materialization
- `live_kit_materialized` — progressive disclosure (#742); **must not** flip
  false solely because the pane was collapsed

Solver visibility (Active Source):

- `browser_visible = not browser_collapsed`
- `harmony_open` only when Matches are OPEN **and** Browser is OPEN
- `live_kit_visible = live_kit_materialized and not live_kit_collapsed`

Collapse is never persisted by #845. Existing ratio persistence stays ratios-only.
Display-preference `panel_visibility` (#696) is an adjacent seam and is **not**
extended by this slice.

### State preservation

| Surface | On collapse / reopen |
|---------|----------------------|
| Browser | Selection preserved; scroll/view only as existing contracts already keep |
| Harmonic Matches | Reference + results preserved; no rematch solely due to collapse |
| Live Kit | Slots / content preserved; materialization flag unchanged |

### Fachlich gültige Kombinationen

Not every boolean tuple is valid. Ownership forbids Matches OPEN while Browser
is COLLAPSED.

| Browser | Matches | Live Kit (materialized) | Valid? |
|---------|---------|-------------------------|--------|
| OPEN | OPEN | OPEN | yes |
| OPEN | COLLAPSED | OPEN | yes |
| OPEN | OPEN | COLLAPSED | yes |
| OPEN | COLLAPSED | COLLAPSED | yes |
| COLLAPSED | COLLAPSED | OPEN | yes |
| COLLAPSED | COLLAPSED | COLLAPSED | yes |
| COLLAPSED | OPEN | * | **invalid** — force Matches COLLAPSED |

Rules:

- Collapsing Browser **must** force Matches presentation COLLAPSED.
- Reopening Browser does **not** auto-reopen Matches; Matches reopen only via
  their own handle / existing toggle.
- Live Kit may OPEN/COLLAPSE independently of Browser once materialized.
- Unmaterialized Live Kit has no collapse UX (no pane → no residual handle).
- Every valid COLLAPSED pane keeps a reachable reopen path (visible residual
  mid-edge handle + keyboard focus/activation). Hover may emphasize the handle
  but must not be the only operable path.

### Mid-edge handles vs resize intents

Collapse handles are **click/activate** controls centered on the relevant pane
edge (`PointingHandCursor`). Elastic panel dividers (`elasticHandleAfter*`) and
Browser column resize (#780) remain **drag** controls (`SizeHorCursor`).

- Distinct `objectName`s and hit areas; no shared MouseArea that both drags and
  collapses.
- #845 does not redesign divider/column-resize chrome.
- [#846](https://github.com/jannekbuengener/sample-brain/issues/846) owns calming
  permanent column dividers / ephemeral resize styling afterward.
- [#843](https://github.com/jannekbuengener/sample-brain/issues/843) uses the
  **existing** Harmonic Matches pane as a Browser extension
  (Browser → Matches → Live Kit). It owns context-menu **open/retarget** of that
  pane and removes the header `harmonicMatchButton` producer entry. It does
  **not** add a second Matches surface, docking model, or close/X/ON/OFF chrome.
  Close/reopen presentation remains sole #845 handle ownership; collapsing
  Matches must preserve the current harmony anchor/results for later reopen.

### Non-goals (#845)

- New docking / reordering / free-canvas architecture
- New persistence architecture for collapse flags
- Matching algorithm / Browser column data projection changes
- Audio, BPM/Key, Step Sequencer, Arrangement
- Implementing #846 or #843 in the same slice

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
2. Sum(visible widths) + handles = available content width
3. Direct neighbour reacts stronger than farther same-side panel
4. Min saturation redistributes residual delta
5. ≥1000 deterministic drag steps: no relevant ratio drift
6. Window resize preserves ratios
7. 3↔4 panel toggle stable
8. Harmony open/close without drift
9. Drag-end persist + restart restore (ratios only)
10. Corrupt / NaN / Inf / unknown IDs fail closed
11. Browser keyboard / Search focus / Esc remain intact
12. #845: valid OPEN/COLLAPSED combinations only; Browser COLLAPSED ⇒ Matches COLLAPSED
13. #845: collapse preserves Browser selection, Matches reference/results, Live Kit content
14. #845: `live_kit_materialized` unchanged by Live Kit collapse/reopen
15. #845: mid-edge collapse handles keyboard-activatable; residual reopen reachable
16. #845: collapse hit-areas do not share drag intent with elastic/column resize

Runtime acceptance sizes: 1600×900, 1280×720, 1120×640; Harmony open/closed;
panel collapse combinations from the #845 table; 100% / 125% / 150% DPI.
Agent visual/runtime acceptance required before merge
(see `WORKBENCH_VISUAL_ACCEPTANCE.md` operative rule).
