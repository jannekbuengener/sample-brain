# Workbench Single Workspace Contract (#905)

**Status:** ACTIVE_SUPPORTING (Owner design freeze; `SPEC_REVIEW_PENDING` until Owner reviews this written record)

**Issues:** [#905](https://github.com/jannekbuengener/sample-brain/issues/905) (epic), [#906](https://github.com/jannekbuengener/sample-brain/issues/906) (canon migration after review)

**Renderer:** `LOCK_PYSIDE6_QML` remains binding for current Workbench UI. This file does not change runtime.

This document freezes Owner Decision **A — Stable Workspace + Progressive Disclosure** as durable product-navigation authority for the Single Workspace model. It is docs/design only: no product code, QML, session, or audio behavior changes here.

## Authority for product navigation

| Surface | Role after this design freeze |
|---|---|
| [#905](https://github.com/jannekbuengener/sample-brain/issues/905) + this contract | Binding authority for **product navigation / workspace geometry** when wording conflicts |
| [`docs/PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md) | Remains a formal `ACTIVE_CANON` index entry until [#906](https://github.com/jannekbuengener/sample-brain/issues/906) migrates it; its multi-screen `Screen 1 → Screen 2 → Screen 3` navigation model is **already superseded** by #905 + this contract |
| [#906](https://github.com/jannekbuengener/sample-brain/issues/906) | Owns physical migration of remaining canon/docs so temporary wording inconsistency is fully resolved after Owner review of this record |
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

Later projection (#908) must rest on the same canonical musical truth.

When a sample is added to the Live Kit:

- reuse existing session / Live Kit / Channel / Pattern state;
- the corresponding Rack / Sequencer row becomes available in the bottom workspace;
- do not introduce a second Live-Kit truth;
- do not introduce QML-owned Pattern state;
- do not copy or mirror Rack state into a parallel structure;
- do not duplicate audio assets — channels reference library samples.

Occupied sample/channel assignments may materialize a visible Rack row. Reuse existing deterministic kit/group provenance (canonical Live Kit groups/slots and seed vs user-channel rules under [`PATTERN_CORE_CONTRACT.md`](PATTERN_CORE_CONTRACT.md) and Live Kit code). Empty or unneeded groups must not permanently claim attention.

Exact remove/hide lifecycle for emptied rows is **not** reinvented here. Existing contracts and live code are evaluated first; any gap becomes a narrow follow-up before #908 implementation.

Do not implement the end state as a copied former Screen-2 page embedded into a former Screen-1 page. The end state is one Workbench projection over shared Python contracts.

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

## 9. One-shot / loop unresolved boundary

This contract does **not** freeze new one-shot vs loop presentation semantics beyond what live Rack / sequencer contracts already state.

Binding limits:

- evaluate existing Rack / step / sequencer semantics first ([`SEQUENCER_PLAYBACK_CONTRACT.md`](SEQUENCER_PLAYBACK_CONTRACT.md), Pattern Core, Channel Rack controller);
- do not assert that a loop must share the same step visualization/trigger UX as a Kick/Hat one-shot;
- if loops need a distinct projection or trigger semantic, create a later narrow contract;
- invent no implicit repeat / retrigger behavior in this freeze.

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

### This design-freeze PR (docs only)

- `git diff --check`
- `python tools/check_canon_drift.py`
- scope check: only this contract and the required [`CANON_INDEX.md`](CANON_INDEX.md) link
- self-review: placeholder scan, internal consistency, scope, ambiguity

### Later gates (not this PR)

| Gate | Owner |
|---|---|
| Owner review of this written record | `SPEC_REVIEW_PENDING` → Owner |
| Physical canon/docs migration | #906 |
| Session/audio-focus audit outcome | #907 |
| Bottom Live Kit / Rack projection + runtime/visual acceptance | #908 after #906/#907 |
| Arrangement interaction design | later explicit Owner decision via #679 |

## 14. Explicit non-goals

This contract does **not** authorize:

- product / QML / runtime implementation
- session or audio behavior changes
- rewriting [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md), README, Bootloader, or knowledge snapshots in the same PR as this freeze (that is #906 after Owner review)
- Arrangement / timeline / mixer / piano-roll design
- generalized docking or window management
- mechanical module renames for historical screen terminology
- reopening closed #675 / #678
- VST3 / host-plugin primary path
- cloud producing or full DAW replacement

## 15. Migration / decomposition

| Issue | Role |
|---|---|
| [#905](https://github.com/jannekbuengener/sample-brain/issues/905) | Epic: Single Workspace — focus-driven progressive disclosure |
| [#906](https://github.com/jannekbuengener/sample-brain/issues/906) | After Owner review of this record: migrate remaining product canon/docs so multi-screen navigation is no longer written as current authority |
| [#907](https://github.com/jannekbuengener/sample-brain/issues/907) | Audit session/audio-focus assumptions; separate navigation-coupled seams from domain audio ownership before Rack embed |
| [#908](https://github.com/jannekbuengener/sample-brain/issues/908) | Bottom Live Kit / Rack / Step-Sequencer projection in the one Workbench; depends on #906 and #907 |
| [#679](https://github.com/jannekbuengener/sample-brain/issues/679) | Future Arrangement inside Single Workspace — **PARKED / UNDESIGNED — requires later explicit Owner design decision** |

Recommended sequence after Owner accepts this written freeze:

```text
Owner SPEC review
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
