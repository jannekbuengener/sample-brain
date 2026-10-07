# Workbench Single Workspace Contract (#905)

**Status:** ACTIVE_SUPPORTING — Owner-reviewed / approved (2026-10-05). **Reclassified 2026-10-07 (#1076):** exclusive product-navigation authority for Single Workspace is **superseded** where it conflicts with Edit → Arrangement → later Live ([#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076)). This file remains supporting evidence for progressive disclosure, shared Python musical/session truth, QML projection/intent, and Edit-workspace geometry (#954).

**Issues:** [#905](https://github.com/jannekbuengener/sample-brain/issues/905) (historical epic / delivery evidence), [#906](https://github.com/jannekbuengener/sample-brain/issues/906) (completed #905-era canon migration), [#954](https://github.com/jannekbuengener/sample-brain/issues/954) (Edit Live Kit overlay drawer geometry), [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076) (current product-navigation authority)

**Renderer:** `LOCK_PYSIDE6_QML` remains binding for current Workbench UI. This file does not change runtime.

This document freezes Owner Decision **A — Stable Workspace + Progressive Disclosure** as durable **Edit-workspace** geometry and UX evidence from the #905 era. It is docs/design only: no product code, QML, session, or audio behavior changes here.

## Authority for product navigation

| Surface | Role |
|---|---|
| [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076) + [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md) | **Current** product-navigation authority: Edit → Arrangement → later Live |
| [#905](https://github.com/jannekbuengener/sample-brain/issues/905) + this contract | Historical Single Workspace delivery + **supporting** progressive-disclosure / Edit geometry evidence; exclusive nav thesis superseded on conflict |
| [#906](https://github.com/jannekbuengener/sample-brain/issues/906) | Historical canon migration that removed multi-screen product-navigation wording |
| [#907](https://github.com/jannekbuengener/sample-brain/issues/907) | Owns session/audio-focus audit before Rack embed |
| [#908](https://github.com/jannekbuengener/sample-brain/issues/908) | Closed delivery evidence for the original bottom Rack projection; its permanent-band geometry is superseded by #954 |
| [#954](https://github.com/jannekbuengener/sample-brain/issues/954) | Supporting Owner evidence for balanced Browser/Harmony defaults and the Live Kit bottom overlay drawer in Edit |
| [#679](https://github.com/jannekbuengener/sample-brain/issues/679) | **ACTIVE** Arrangement product/domain owner |

## 1. Problem / superseded multi-screen model

The former product and navigation model

```text
Screen 1 → Screen 2 → Screen 3
```

is superseded as a product/UX concept. Sample Brain no longer treats Library, Channel Rack, and Arrangement as sequential product pages that the user must navigate between.

This does **not** invalidate already delivered technical foundations. The following remain reusable domain contracts unless a later scoped issue proves otherwise:

- Live Kit state
- Channel / Pattern / Trigger
- Channel Rack core
- Sequencer playback
- PCM / native audio
- `WorkbenchSession`
- Persistence
- Deterministic kit / group provenance

`Channel Rack`, `Pattern`, `Arrangement`, and related names are **domain capabilities**, not automatic proof of separate product pages.

## 2. Owner intent

Owner Decision **A — Stable Workspace + Progressive Disclosure**:

- Sample Brain has exactly **one persistent Workbench**.
- The Workbench keeps the user focused on the current musical task.
- Progressive disclosure is preferred over mode/page proliferation.
- Python remains musical/state authority; QML remains projection and user intent.
- Offline / local-first and `LOCK_PYSIDE6_QML` remain binding.
- No full-DAW expansion by implication.

## 3. Single Workspace principle

One persistent Workbench is the product surface.

Internal subsystems do not earn their own product pages merely by existing. Domain capabilities project into the same Workbench when relevant.

Do **not** build a general docking or window-manager architecture from this decision. Keep focus/collapse behavior simple and deterministic.

## 4. Progressive disclosure / focus model

Binding focus principle:

- The current musical work step determines which tools are visible.
- Relevant → visible.
- Not relevant → hidden, collapsed, or visually de-emphasized.
- No new page/screen navigation solely because an internal subsystem exists.
- Progressive disclosure before mode/page proliferation.

## 5. Stable vs contextual surfaces

Default materialized Browser geometry:

```text
┌─────────────┬───────────────────────────────┬──────────────┐
│   LIBRARY   │        SAMPLE BROWSER         │   HARMONIC   │
│             │                               │    MATCHES   │
└─────────────┴───────────────────────────────┴──────────────┘
```

| Surface | Role |
|---|---|
| Library / Sources | Stable left rail; remains as orientation |
| Main sample browser / playlist | Dominant upper workspace; central browse and selection context |
| Harmonic Matches | Contextual right Browser extension; it and Library use equal default relative side proportions, but remain independently resizable |
| Classic Live Kit (Edit tool) | Contextual bottom **overlay drawer** scoped exactly to the current Browser/Edit workspace; not a top-level mode, not Arrangement Entry, and never a permanent height reservation. Historical #905/#908 Rack/Step-Sequencer projection into this drawer is delivery evidence — product placement of Step Sequencer is Arrangement (#679), not mandatory Edit Live Kit content. |

## 6. Live Kit ↔ Rack projection

#954 owns the current Single Workspace Live Kit / Rack drawer presentation.

When a sample is added to the Live Kit:

- reuse existing session / Live Kit / Channel / Pattern state;
- `LiveKitState.assign` materializes/reconciles Rack via `ChannelRackController.ensure_state()` without Screen-2 navigation (#916 seam);
- the corresponding Rack / Sequencer row becomes available in the bottom workspace when occupied;
- point-trigger-safe (`one_shot` / `oneshot`) rows expose the Step Grid;
- loop-class / ambiguous rows show identity only — no DEFAULT_ON 16-step grid (binding playback/projection freeze: [`LOOP_ROW_PLAYBACK_CONTRACT.md`](LOOP_ROW_PLAYBACK_CONTRACT.md) / #920);
- do not introduce a second Live-Kit truth;
- do not introduce QML-owned Pattern state;
- do not copy or mirror Rack state into a parallel structure;
- do not duplicate audio assets — channels reference library samples.

Occupied sample/channel assignments may materialize a visible Rack row. Reuse existing deterministic kit/group provenance (canonical Live Kit groups/slots and seed vs user-channel rules under [`PATTERN_CORE_CONTRACT.md`](PATTERN_CORE_CONTRACT.md) and Live Kit code). Empty or unneeded groups must not permanently claim attention.

Cleared / empty slots follow existing domain reconciliation and disappear from the occupied Rack projection. Empty groups and rows reserve no Drawer height.

### 6.1 Bottom overlay drawer contract (#954)

- The Browser remains the dominant workspace. Opening the Drawer overlays the Browser; it must not reflow the Browser into a smaller upper row.
- The Drawer is anchored to the Browser workspace, not to the whole application. Its left and right edges always equal the current Browser edges. It ends at the Harmony divider and never draws under Harmonic Matches.
- Closing Harmony expands Browser and Drawer together; reopening Harmony contracts both together. The Drawer retains no stale right-edge pixel coordinate.
- On every Workbench/app start the Drawer is **CLOSED**, including when the Python-owned Live Kit/Rack state restores from an existing session. Drawer visibility and first-auto-disclosure consumption are transient presentation state and are never persisted as musical state.
- The first successful explicit Add-to-Live-Kit action in each Workbench session auto-opens the Drawer compactly, consumes the one automatic disclosure, and closes an open Harmony pane once through the existing non-destructive Harmony presentation close path. The preserved Harmony anchor/results remain intact.
- A user may reopen Harmony while the Drawer remains open. Later Adds respect that user choice and may neither close manually reopened Harmony nor reopen a manually closed Drawer.
- Initial Drawer height shows its header plus one actual projected Rack/Sequencer row. Each additional occupied row adds one row increment. Growth caps near 35--40% of available workspace height; further rows scroll inside the Drawer.
- Browser scrolling receives a bottom content inset equal to the visible Drawer height, so every Browser row remains reachable beneath the visual overlay.
- Use the existing elastic layout solver, Theme Core tokens, and Python-owned Live Kit/Rack projection. No QML musical state, Pattern/Trigger shadow copy, new persistence store, playback route, docking framework, or theme palette is authorized.

Do not implement the end state as a copied former Screen-2 page embedded into a former Screen-1 page. The end state is one Workbench projection over shared Python contracts. Product UX must not require `enter_screen2()` / `activeScreen == screen2` for the bottom Rack.

## 7. State ownership / data flow

```text
User intent (QML / adapters)
        │
        ▼
WorkbenchSession (Python-owned)
  ├── LiveKitState / LiveKitPresentationState
  ├── ChannelRackController / Channel / Pattern / Trigger
  ├── transport / audition / sequencer playback seams
  └── persistence (existing session store honesty)
        │
        ▼
QML projection (visible surfaces only)
```

Invariants:

- Python is the source of truth for musical and session state.
- QML projects state and emits commands / intent only.
- One `WorkbenchSession` ownership path.
- No second musical/session state owner.
- No QML shadow Pattern / Rack truth.
- Reuse existing Pattern / Channel / Trigger / playback / session / persistence contracts before adding new ones.

## 8. Session / audio ownership boundary

Existing Screen-transition audio-focus mechanics (for example `enter_screen2` / `return_to_screen1` and related wording in [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md)) are **not** automatically Single-Workspace authority.

[#907](https://github.com/jannekbuengener/sample-brain/issues/907) owns the audit that separates:

- true **audio ownership** behavior, from
- **navigation-coupled** behavior that assumed leaving/entering product screens.

Until #907 is resolved:

- invent no new audio ownership model in this design freeze;
- invent no second transport;
- invent no QML-owned stop/play state;
- treat `WorkbenchSession` as the existing ownership starting point;
- distinguish navigation-coupled semantics from domain audio ownership.

#908 must not claim or release cross-screen audio focus as a substitute for that audit.

## 9. One-shot / loop boundary

Point-trigger-safe one-shot rows may render the normal Step Grid in the #908 bottom Rack.

Loop-class / sustained-sample semantics are frozen in [`LOOP_ROW_PLAYBACK_CONTRACT.md`](LOOP_ROW_PLAYBACK_CONTRACT.md) (#920):

- architecture outcome: `LOOP_ROW_DISTINCT_PROJECTION_REQUIRED`;
- loop playback mode for explicit `loop`: `NATURAL_CYCLE_REPEAT` (absolute `play_anchor + i * cycle_duration`; continues across pattern passes until Stop);
- loop / ambiguous rows keep identity projection (no DEFAULT_ON 16-step grid);
- ambiguous / unknown class: identity + audition only; no loop auto-start; no point-trigger Rack playback; do not destroy persisted triggers for missing metadata;
- Pattern Core `Trigger` shapes stay point-fire for oneshots; explicit loop rows must not be seeded as DEFAULT_ON triggers;
- native unavailable → loop Rack playback fail-closed (no preview fallback), SYNC on or off;
- no clip launcher, Arrangement, PCM wrap-loop engine, or new transport owner in this freeze;
- runtime implementation is a separate follow-up slice after Owner/Lead contract review — not part of #908.

## 10. Arrangement — ACTIVE (#679); exclusive Single-Workspace embedding superseded

Arrangement is an **ACTIVE** product mode after Edit / Kit, owned by [#679](https://github.com/jannekbuengener/sample-brain/issues/679) (Owner-reactivated 2026-10-07). It is **not** a historical Screen-3 page and is **not** required to live inside an exclusive Single-Workspace-only navigation model.

The older claim that Arrangement must remain undesigned inside one persistent Workbench is **superseded** by [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076). Concrete Arrangement contracts and domain work proceed through [#1082](https://github.com/jannekbuengener/sample-brain/issues/1082)–[#1084](https://github.com/jannekbuengener/sample-brain/issues/1084) (next contract wave) and follow-on #679 children. Later Live remains parked under [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088).

This #905-era contract does **not** freeze Arrangement timeline/block/mask details; those belong to the Arrangement children under #679. Do not invent them here.

## 11. Historical terminology policy

Closed issues and PRs may continue to use:

- Screen 1
- Screen 2
- Screen 3
- Channel Rack Screen

when that wording is historical delivery evidence (including closed [#675](https://github.com/jannekbuengener/sample-brain/issues/675) / [#678](https://github.com/jannekbuengener/sample-brain/issues/678)).

Rules:

- no history-cleanup rewrite solely for terminology;
- do not reopen closed historical issues for rename theater;
- do not mechanically rename internal modules/classes merely because they contain `channel_rack` or historical screen language;
- current product authority must not derive separate page navigation from historical Screen-1/2/3 names.

## 12. Failure modes / invariants

Fail closed against:

| Failure | Invariant |
|---|---|
| Second Live Kit or Rack truth | One Python-owned musical state |
| QML-owned Pattern / play-stop truth | QML = projection + intent only |
| Copied Screen-2 embed | One Workbench projection, not a mirrored page |
| Duplicated audio assets | Channels reference library samples |
| Inventing Arrangement model in this file | Arrangement contracts owned by #679 children; this file does not freeze them |
| Stale permanent bottom-band geometry | #954 overlay drawer supersedes the historical ~24% band and empty-strip presentation |
| Navigation seams as silent audio authority | #907 separates navigation vs audio ownership |
| Empty-group attention tax | Unneeded empty groups stay de-emphasized |
| Docking / window-manager scope creep | Simple progressive disclosure only |
| Full-DAW implication | No mixer/buses/VST/piano-roll authorization here |

## 13. Validation strategy

### Validation for this contract and its canon companions

- `git diff --check`
- `python tools/check_canon_drift.py`
- self-review: placeholder scan, internal consistency, scope, ambiguity
- after #906: no current-authority product docs may require Screen 1 → Screen 2 → Screen 3 navigation

### Follow-up gates

| Gate | Owner |
|---|---|
| Owner review of this written record | **PASS** (2026-10-05) |
| Physical canon/docs migration | #906 |
| Session/audio-focus audit outcome | #907 |
| Bottom Live Kit overlay drawer + runtime/visual acceptance | #954 |
| Arrangement contracts / domain / UI | #679 ACTIVE + children #1082–#1084 (+ follow-ons); later Live #1088 |

## 14. Explicit non-goals

This contract does **not** authorize:

- product / QML / runtime implementation outside #954's bounded Drawer slice
- session or audio behavior changes
- Arrangement / timeline / mixer / piano-roll design
- generalized docking or window management
- mechanical module renames for historical screen terminology
- reopening closed #675 / #678
- VST3 / host-plugin primary path
- cloud producing or full DAW replacement

Canon/docs alignment of remaining multi-screen product-navigation wording is owned by [#906](https://github.com/jannekbuengener/sample-brain/issues/906) and must not change runtime seams owned by [#907](https://github.com/jannekbuengener/sample-brain/issues/907).
## 15. Migration / decomposition

| Issue | Role |
|---|---|
| [#905](https://github.com/jannekbuengener/sample-brain/issues/905) | Epic: Single Workspace — focus-driven progressive disclosure |
| [#906](https://github.com/jannekbuengener/sample-brain/issues/906) | Canon/docs migration so multi-screen navigation is no longer written as current product authority |
| [#907](https://github.com/jannekbuengener/sample-brain/issues/907) | Audit session/audio-focus assumptions; separate navigation-coupled seams from domain audio ownership before Rack embed |
| [#908](https://github.com/jannekbuengener/sample-brain/issues/908) | Closed historical bottom Rack projection; retain its shared-domain reuse evidence, not its superseded permanent-band geometry |
| [#954](https://github.com/jannekbuengener/sample-brain/issues/954) | Active QML/UX slice: Browser-scoped overlay drawer, first-add disclosure, dynamic height, Browser inset, and visual acceptance |
| [#679](https://github.com/jannekbuengener/sample-brain/issues/679) | **ACTIVE** Arrangement product/domain owner (Edit → Arrangement → later Live) |
| [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076) | Current product-navigation authority |

Recommended historical sequence for the #905-era freeze (completed / evidence):

```text
Owner SPEC review (PASS)
  → #906 canon migration
  → #907 audio/session-focus audit
  → #908 / #954 Edit Live Kit projection evidence
```

Current product sequence after #1076: Edit → Arrangement → later Live (#1075/#1076/#679/#1088).

## Related supporting contracts (reuse, do not redefine)

- [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md)
- [`PATTERN_CORE_CONTRACT.md`](PATTERN_CORE_CONTRACT.md)
- [`SEQUENCER_PLAYBACK_CONTRACT.md`](SEQUENCER_PLAYBACK_CONTRACT.md)
- [`PROGRAM_CHROME_CONTRACT.md`](PROGRAM_CHROME_CONTRACT.md) — chrome frame contract; product modes Edit / Arrangement / Live per #1076
- [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md) — current producing-path authority
- [`REALTIME_WORKBENCH_SCOPE.md`](REALTIME_WORKBENCH_SCOPE.md)
- [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md)
