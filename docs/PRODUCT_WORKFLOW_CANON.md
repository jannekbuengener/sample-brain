# Product Workflow Canon — Sample Brain

Status: **canonical product-path decision** (updated 2026-10-07 for Edit → Arrangement → later Live / [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076)).

Supersedes, where they conflict with this file:

- older “VST3-first as primary producing path”;
- blanket “no patterns / no arrangement” wording;
- the former multi-screen product-navigation model `Screen 1 → Screen 2 → Screen 3`;
- the exclusive Single-Workspace-only navigation thesis from [#905](https://github.com/jannekbuengener/sample-brain/issues/905) that forbids separate product modes;
- earlier Build → Performance wording.

Closed [#905](https://github.com/jannekbuengener/sample-brain/issues/905) / [#908](https://github.com/jannekbuengener/sample-brain/issues/908) / [#675](https://github.com/jannekbuengener/sample-brain/issues/675) / [#678](https://github.com/jannekbuengener/sample-brain/issues/678) remain historical delivery evidence and are not cosmetically rewritten.

Product-navigation authority for the current sequence is this file together with [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076). [`WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md`](WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md) remains supporting evidence for progressive disclosure and Edit-workspace geometry; its exclusive navigation thesis is superseded where it conflicts (see that file’s status banner).

## 1. Internal producing workflow

The core producer path is **local Workbench-first**, not an external DAW and not a VST host. Current product modes:

```text
Edit
  ↓
Arrangement
  ↓
Live                  (later; parked under #1088)
```

### Edit (mode)

- Library / Sources (stable left rail)
- Main sample playlist / Browser
- Harmonic Matches (contextual / optional)
- Classic Live Kit as an **Edit tool** (not a top-level mode) — [#1077](https://github.com/jannekbuengener/sample-brain/issues/1077)
- Optional Edit docking / sample-drag tools — [#1069](https://github.com/jannekbuengener/sample-brain/issues/1069)–[#1073](https://github.com/jannekbuengener/sample-brain/issues/1073)

### Arrangement (mode)

Owned by [#679](https://github.com/jannekbuengener/sample-brain/issues/679) (**ACTIVE** Arrangement owner):

- Step Sequencer / Pattern programming as Arrangement capabilities (not top-level modes)
- Song structure (blocks / groups / masks / end marker) via [#1082](https://github.com/jannekbuengener/sample-brain/issues/1082)–[#1087](https://github.com/jannekbuengener/sample-brain/issues/1087)
- Explicit Edit → Arrangement transition — [#1078](https://github.com/jannekbuengener/sample-brain/issues/1078)

### Live (future mode)

Later performance perspective after Arrangement. Design/layout/MIDI/multi-track remain parked under [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088).

### Binding principles (retained)

- Progressive disclosure inside Edit and within modes as appropriate.
- One Python-owned musical / session / audio / persistence authority; QML = projection + intent.
- Offline / local-first; no external DAW in the core workflow.
- FL Browser export remains a **legacy/fallback CLI** integration.
- VST3 / host-plugin work remains **parked** (see [#469](https://github.com/jannekbuengener/sample-brain/issues/469)) and is **not** the primary product path.
- Demo `Export Kit` is a distinct action from full-version Arrangement Entry.

## 2. Workbench surfaces and domain capabilities

| Surface / capability | Intent | Status on `main` |
|--------|--------|------------------|
| Library / Sources + Browser + Harmonic Matches | Browse, select, and match samples in Edit | Partial/shipped QML Workbench shell; Tk remains default/fallback; `LOCK_PYSIDE6_QML` for new visuals |
| Live Kit | Assign samples into canonical kit slots (Edit tool) | Shipped domain capability; classic Edit-module path [#1077](https://github.com/jannekbuengener/sample-brain/issues/1077); historical bottom-projection delivery [#908](https://github.com/jannekbuengener/sample-brain/issues/908) |
| Channel Rack / Pattern / Step-Sequencer | Program patterns/triggers over kit-referenced and user channels | Domain foundations **DONE** — historical delivery [#675](https://github.com/jannekbuengener/sample-brain/issues/675)/[#678](https://github.com/jannekbuengener/sample-brain/issues/678). Product placement: Arrangement workflow (not a top-level mode; not mandatory Edit Live Kit content) |
| Arrangement | Song-structure mode after Edit / Kit | **ACTIVE** owner [#679](https://github.com/jannekbuengener/sample-brain/issues/679); next contracts [#1082](https://github.com/jannekbuengener/sample-brain/issues/1082)–[#1084](https://github.com/jannekbuengener/sample-brain/issues/1084); broader children [#1082](https://github.com/jannekbuengener/sample-brain/issues/1082)–[#1087](https://github.com/jannekbuengener/sample-brain/issues/1087) |
| Live | Later performance perspective | **PARKED** under [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088) until Arrangement delivery + Owner gates |

Historical issues/PRs may still say “Screen 1 / Screen 2 / Screen 3” as delivery evidence. That wording is not current product-navigation authority.

## 3. Channel Rack product rules (domain capability)

These are product constraints for the Channel Rack / Pattern domain. They are **not** a claim that a separate Channel Rack product page or top-level mode remains current authority.

- Live Kit assignments can be taken into the Channel Rack (kit → channels) as the **initial seed**.
- The Channel Rack is **not** limited to the fixed Live Kit slot universe; user-added channels with opaque IDs (no fake Live Kit slot) are in scope for the Python core (#681).
- A sample remains the unchanged library asset; channels **reference** samples and do not duplicate audio files.
- Channel Rack is **pattern/trigger first** (grid programming).
- **Initial step semantics (v1, #677):** New sample-bearing Channel Rack channels initialize with every v1 step active. Empty channels initialize without triggers. The Rack domain uses DEFAULT_ON / subtractive programming: click removes an active step trigger; click again restores it. Pattern storage remains an explicit trigger list (no inverted / off-mask). There is no additive/subtractive mode selector or preference in v1.
- A later piano / event editor may share the same pattern substrate; it is **not** required for Channel Rack v1.
- Mixer, sends, inserts, buses, and complex routing are **out of Channel Rack v1 scope**.
- Architecture must not unnecessarily block those later extensions.
- A future vocal / beatbox → pattern feature should reuse the same pattern/channel substrate.
- Pitching, time-stretching, and resynthesis are **not** prerequisites for Channel Rack v1.

## 4. What “no generative” still means

Still **out of scope**:

- Generative songwriting / AI melody or chord invention
- Automatic full-track arrangement authorship
- Mastering
- Marketplace / cloud producing
- Full DAW replacement (arbitrary track counts, plugin racks, mix engineering as product core)

**In scope** as user-authored local Workbench tools (when built):

- Pattern / trigger programming in the Channel Rack / Sequencer domain (Arrangement workflow)
- Arrangement mode under [#679](https://github.com/jannekbuengener/sample-brain/issues/679)
- Analysis “arrangement roles” on source tracks (Track Map) — **analysis vocabulary**, not Arrangement product mode

Do not conflate Track Map / `arrangement_*` analysis contracts with Arrangement product mode.

## 5. Build order (binding historical readiness)

Foundation gates that unlocked Channel Rack domain UI (technical readiness; delivered):

1. **Product canon** (this document + PRD/architecture alignment)
2. **Session ownership** — one Live Kit truth; QML commands → native transport/audio — **DONE** (#647)
3. **Minimal Pattern Core** — Channel, Pattern, Trigger/Event, musical position, stable slot/channel IDs — **DONE** (#656)
4. **Minimal Sequencer Playback** — pattern position → `TempoMap` → scheduled engine frame → cached PCM voice — **DONE** (#663 scheduler + #676 PCM cache/decode provider + #698 voice lifecycle)
5. **Channel Rack domain UI** — Channel Rack Python core is **DONE** (#667); initial DEFAULT_ON step semantics are **DONE** (#677); extensible channels are **DONE** (#681); QML implementation (#678 / PR #755) is **DONE**; parent epic #675 is CLOSED

`TECHNICALLY_UNBLOCKED` is not `CURRENT_PRODUCT_PRIORITY`.

### Current product follow-ups (Edit → Arrangement → later Live)

1. Canon / open-issue boundary freeze — [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076) under [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075)
2. Edit Live Kit module — [#1077](https://github.com/jannekbuengener/sample-brain/issues/1077); Edit docking/DnD — [#1069](https://github.com/jannekbuengener/sample-brain/issues/1069)–[#1073](https://github.com/jannekbuengener/sample-brain/issues/1073)
3. Arrangement contract wave — [#1082](https://github.com/jannekbuengener/sample-brain/issues/1082) / [#1083](https://github.com/jannekbuengener/sample-brain/issues/1083) / [#1084](https://github.com/jannekbuengener/sample-brain/issues/1084) (after #1076)
4. Arrangement domain + transition + visual/QML — [#1085](https://github.com/jannekbuengener/sample-brain/issues/1085)–[#1087](https://github.com/jannekbuengener/sample-brain/issues/1087), [#1078](https://github.com/jannekbuengener/sample-brain/issues/1078), [#1079](https://github.com/jannekbuengener/sample-brain/issues/1079), [#1080](https://github.com/jannekbuengener/sample-brain/issues/1080)
5. Later Live — [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088) after Arrangement delivery

Closed [#908](https://github.com/jannekbuengener/sample-brain/issues/908) is historical bottom Rack projection evidence (geometry superseded by [#954](https://github.com/jannekbuengener/sample-brain/issues/954) where relevant), not an open product epic.

## 6. Documents this canon overrides (on conflict)

When wording conflicts, prefer this file and [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075)/[#1076](https://github.com/jannekbuengener/sample-brain/issues/1076) over:

- Exclusive Single-Workspace-only navigation as current product authority (#905 thesis where it forbids Edit / Arrangement / Live modes)
- Former multi-screen product navigation `Screen 1 → Screen 2 → Screen 3` as current user workflow
- “VST3-first / VST3 is the primary product interface” in `docs/PRODUCT_REQUIREMENTS.md`, `docs/TARGET_ARCHITECTURE.md` §10.2, `docs/DAW_INTEGRATION_SPEC.md`, `docs/SYSTEM_REQUIREMENTS.md`, `docs/product/README.md`, `docs/product/05_VST_PRODUCING_WORKSPACE_SPEC.md`
- Blanket “no drum patterns / no arrangement” non-goals that forbid user-authored Channel Rack patterns or Arrangement mode
- Build → Performance as current product sequence

Historical VST pillar specs (#90–#95) remain **archived design notes** for a parked plugin path; they do not authorize VST as the current main producing path.

Existing runtime seams that still use screen-transition names (for example `enter_screen2` / `return_to_screen1` in [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md)) describe **current runtime ownership hooks**, not product-page navigation. [#907](https://github.com/jannekbuengener/sample-brain/issues/907) owns whether those seams need later repair/generalization. Do not treat them as authority to restore multi-screen product navigation.

## 7. Related live contracts

| Topic | Canonical live reference |
|-------|--------------------------|
| Product sequence / navigation | This file + [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076) |
| Edit progressive disclosure / geometry evidence | [`WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md`](WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md) (exclusive nav thesis superseded where conflicting) |
| Program chrome modes vs tools | [`PROGRAM_CHROME_CONTRACT.md`](PROGRAM_CHROME_CONTRACT.md) |
| Functional settings (`arrangement_mode_enabled` docs freeze) | [`WORKBENCH_FEATURE_SETTINGS.md`](WORKBENCH_FEATURE_SETTINGS.md) |
| Realtime Workbench boundary | `docs/REALTIME_WORKBENCH_SCOPE.md` |
| Workbench QML renderer lock | `LOCK_PYSIDE6_QML` in `docs/TARGET_ARCHITECTURE.md` |
| Session ownership (step 2 — done) | [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md), `src/workbench_session.py` |
| Pattern Core (step 3 — done, #656) | [`PATTERN_CORE_CONTRACT.md`](PATTERN_CORE_CONTRACT.md), `src/pattern_core.py` |
| Sequencer Playback (step 4 — done, #663 + #676) | [`SEQUENCER_PLAYBACK_CONTRACT.md`](SEQUENCER_PLAYBACK_CONTRACT.md), `src/sequencer_playback.py`, `src/sequencer_pcm.py`, `src/native_pcm_decode.py` |
| Channel Rack Python core (pre-UI — done, #667) | `src/channel_rack.py` |
| Live Kit state | `src/workbench_live_kit.py` |
| Session time / TempoMap | `src/session_grid.py` |
| Native voices | `src/native_audio.py` |
| QML Workbench shell | `src/workbench_qml.py` |

Steps 2→3→4→5 are green (scheduling + production PCM provider + #698 voice lifecycle + Channel Rack QML historical delivery). The Channel Rack Python core, DEFAULT_ON initial step semantics (#677), extensible channels (#681), and Channel Rack QML (#678 / PR #755) are merged; parent epic #675 is CLOSED. Current product navigation is Edit → Arrangement → later Live (#1075/#1076); Arrangement owner is [#679](https://github.com/jannekbuengener/sample-brain/issues/679); later Live is parked under [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088).
