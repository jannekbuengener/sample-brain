# Workbench Single Workspace Contract (#905)

**Status:** ACTIVE_SUPPORTING — Owner-reviewed / approved (2026-10-05). Binding product-navigation authority for Single Workspace.

**Issues:** [#905](https://github.com/jannekbuengener/sample-brain/issues/905) (epic), [#906](https://github.com/jannekbuengener/sample-brain/issues/906) (canon migration)

**Renderer:** `LOCK_PYSIDE6_QML` remains binding for current Workbench UI. This file does not change runtime.

This document freezes Owner Decision **A — Stable Workspace + Progressive Disclosure** as durable product-navigation authority for the Single Workspace model. It is docs/design only: no product code, QML, session, or audio behavior changes here.

## Authority for product navigation

| Surface | Role |
|---|---|
| [#905](https://github.com/jannekbuengener/sample-brain/issues/905) + this contract | Binding authority for **product navigation / workspace geometry** |
| [`docs/PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md) | ACTIVE_CANON producing-flow companion; must align with Single Workspace (migrated under #906) |
| [#906](https://github.com/jannekbuengener/sample-brain/issues/906) | Canon/docs migration that removes superseded multi-screen product-navigation wording from current authority surfaces |
| [#907](https://github.com/jannekbuengener/sample-brain/issues/907) | Owns session/audio-focus audit before Rack embed |
| [#908](https://github.com/jannekbuengener/sample-brain/issues/908) | Owns bottom Live Kit / Rack projection implementation after #906/#907 |
| [#679](https://github.com/jannekbuengener/sample-brain/issues/679) | Arrangement interaction model — parked |

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

Conceptual geometry:

```text
┌─────────────┬──────────────────────────────────────────────┐
│             │                                              │
│  LIBRARY    │  ALL SAMPLES        HARMONIC MATCHES        │
│  / SOURCES  │                                              │
│             │                                              │
│             ├──────────────────────────────────────────────┤
│             │  LIVE KIT / RACK / STEP-SEQUENCER           │
│             │                                              │
└─────────────┴──────────────────────────────────────────────┘
```

| Surface | Role |
|---|---|
| Library / Sources | Stable left rail; remains as orientation |
| Main sample browser / playlist | Dominant upper workspace; central browse and selection context |
| Harmonic Matches | Optional / contextual; visible only when musically relevant |
| Live Kit / Rack / Step-Sequencer | Bottom workspace; starts at the left edge of the main playlist and extends to the right workspace edge; not a separate Rack page |

## 6. Live Kit ↔ Rack projection

#908 owns the Single Workspace bottom Live Kit / Rack projection.

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

Cleared / empty slots follow existing domain reconciliation and disappear from the occupied bottom projection. Empty / no safe rows collapse to a calm minimal bottom strip (~32px). Occupied or Live-Kit-revealed state expands the bottom band (~24% of the right workspace).

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
- loop / ambiguous rows keep identity projection (no DEFAULT_ON 16-step grid);
- explicit `loop` class: one start per Rack Play, natural PCM length to EOF, no pass retrigger, SYNC fail-closed without valid source BPM;
- ambiguous / unknown class: identity + audition only (no Rack loop auto-start);
- Pattern Core `Trigger` shapes stay point-fire for oneshots; loop rows must not be seeded as DEFAULT_ON triggers;
- no clip launcher, Arrangement, PCM wrap-loop engine, or new transport owner in this freeze;
- runtime implementation is a separate follow-up slice after Owner/Lead contract review — not part of #908.

## 10. Arrangement — PARKED / UNDESIGNED

Arrangement remains part of the long-term product idea and is **not** a separate Screen-3 page. When designed later, it must live inside the same Workbench under progressive disclosure.

**PARKED / UNDESIGNED — requires later explicit Owner design decision**

Not decided by this contract (and must not be guessed into Pattern/Channel contracts now):

- timeline model
- tracks / lanes
- clips
- Pattern-vs-Channel clip model
- copy vs reference
- loop / resize
- automation
- mixer / routing
- piano roll
- Arrangement-specific persistence extensions
- exact focus / visibility semantics while arranging

Authority for the parked Arrangement track: [#679](https://github.com/jannekbuengener/sample-brain/issues/679).

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
| Premature Arrangement design | Arrangement stays PARKED / UNDESIGNED |
| #908 before #906/#907 | Canon migration + audio-focus audit first |
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
| Bottom Live Kit / Rack projection + runtime/visual acceptance | #908 after #906/#907 |
| Arrangement interaction design | later explicit Owner decision via #679 |

## 14. Explicit non-goals

This contract does **not** authorize:

- product / QML / runtime implementation
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
| [#908](https://github.com/jannekbuengener/sample-brain/issues/908) | Bottom Live Kit / Rack / Step-Sequencer projection in the one Workbench; depends on #906 and #907 |
| [#679](https://github.com/jannekbuengener/sample-brain/issues/679) | Future Arrangement inside Single Workspace — **PARKED / UNDESIGNED — requires later explicit Owner design decision** |

Recommended sequence after Owner acceptance of this freeze:

```text
Owner SPEC review (PASS)
  → #906 canon migration
  → #907 audio/session-focus audit (and any minimal seam repair slice it names)
  → #908 bottom Rack projection (test-first / runtime / visual acceptance)
  → #679 remains parked until explicit Owner design decision
```

## Related supporting contracts (reuse, do not redefine)

- [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md)
- [`PATTERN_CORE_CONTRACT.md`](PATTERN_CORE_CONTRACT.md)
- [`SEQUENCER_PLAYBACK_CONTRACT.md`](SEQUENCER_PLAYBACK_CONTRACT.md)
- [`PROGRAM_CHROME_CONTRACT.md`](PROGRAM_CHROME_CONTRACT.md) — chrome copy/history may still name former routes; product navigation authority for Single Workspace is this file + #905
- [`REALTIME_WORKBENCH_SCOPE.md`](REALTIME_WORKBENCH_SCOPE.md)
- [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md)
