# Product Workflow Canon — Sample Brain

Status: **canonical product-path decision** (updated 2026-10-05 for Single Workspace / [#905](https://github.com/jannekbuengener/sample-brain/issues/905) / [#906](https://github.com/jannekbuengener/sample-brain/issues/906)).
Supersedes older “VST3-first as primary producing path”, blanket “no patterns / no arrangement” wording, and the former multi-screen product-navigation model `Screen 1 → Screen 2 → Screen 3` where those conflict with this file.

Product-navigation geometry is refined by [`WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md`](WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md) (Owner Decision A — Stable Workspace + Progressive Disclosure). On product-navigation conflict, prefer that contract together with this file over older multi-screen wording elsewhere.

## 1. Internal producing workflow

The core producer path is **one persistent local Workbench**, not an external DAW and not a VST host:

```text
ONE PERSISTENT WORKBENCH
  ├── Library / Sources          (stable left rail)
  ├── Main sample playlist       (dominant upper workspace)
  ├── Harmonic Matches           (contextual / optional)
  └── Live Kit / Rack / Step-Sequencer  (bottom workspace capability)
```

- Progressive disclosure: the current musical work step determines which tools are visible; irrelevant surfaces stay hidden, collapsed, or de-emphasized.
- `Channel Rack`, `Pattern`, `Live Kit`, and `Arrangement` are **domain capabilities**, not separate product pages.
- No external DAW is part of this core workflow.
- FL Browser export remains a **legacy/fallback CLI** integration.
- VST3 / host-plugin work remains **parked** (see [#469](https://github.com/jannekbuengener/sample-brain/issues/469)) and is **not** the primary product path.

## 2. Workbench surfaces and domain capabilities

| Surface / capability | Intent | Status on `main` |
|--------|--------|------------------|
| Library / Sources + main playlist + Harmonic Matches | Browse, select, and match samples inside the one Workbench | Partial/shipped QML Workbench shell; Tk remains default/fallback; `LOCK_PYSIDE6_QML` for new visuals |
| Live Kit | Assign samples into canonical kit slots; seeds Rack channels | Shipped domain capability inside the Workbench |
| Channel Rack / Pattern / Step-Sequencer | Program patterns/triggers over kit-referenced and user channels | Domain foundations **DONE** — historical delivery [#675](https://github.com/jannekbuengener/sample-brain/issues/675)/[#678](https://github.com/jannekbuengener/sample-brain/issues/678) (session ownership, Pattern Core, sequencer, Channel Rack Python core, PCM provider #676, DEFAULT_ON #677, extensible channels #681, voice lifecycle #698, QML Channel Rack #678 / PR #755). Bottom-workspace projection into Single Workspace is [#908](https://github.com/jannekbuengener/sample-brain/issues/908) after [#906](https://github.com/jannekbuengener/sample-brain/issues/906)/[#907](https://github.com/jannekbuengener/sample-brain/issues/907) |
| Arrangement | Future song-structure capability inside the same Workbench | **PARKED / UNDESIGNED — requires later explicit Owner design decision** ([#679](https://github.com/jannekbuengener/sample-brain/issues/679)) |

Historical issues/PRs may still say “Screen 1 / Screen 2 / Screen 3” as delivery evidence. That wording is not current product-navigation authority.

## 3. Channel Rack product rules (domain capability)

These are product constraints for the Channel Rack / Pattern domain. They are **not** a claim that a separate Channel Rack product page remains current authority.

- Live Kit assignments can be taken into the Channel Rack (kit → channels) as the **initial seed**.
- The Channel Rack is **not** limited to the fixed Live Kit slot universe; user-added channels with opaque IDs (no fake Live Kit slot) are in scope for the Python core (#681).
- A sample remains the unchanged library asset; channels **reference** samples and do not duplicate audio files.
- Channel Rack is **pattern/trigger first** (grid programming).
- **Initial step semantics (v1, #677):** New sample-bearing Channel Rack channels initialize with every v1 step active. Empty channels initialize without triggers. The Rack domain uses DEFAULT_ON / subtractive programming: click removes an active step trigger; click again restores it. Pattern storage remains an explicit trigger list (no inverted / off-mask). There is no additive/subtractive mode selector or preference in v1.
- A later piano / event editor may share the same pattern substrate; it is **not** required for Channel Rack v1.
- Arrangement, mixer, sends, inserts, buses, and complex routing are **out of Channel Rack v1 scope**.
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

- Pattern / trigger programming in the Channel Rack domain
- Later Arrangement capability inside the same Workbench (still **PARKED / UNDESIGNED — requires later explicit Owner design decision**)
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

Current Single Workspace follow-ups:

1. Canon/docs migration to Single Workspace — [#906](https://github.com/jannekbuengener/sample-brain/issues/906)
2. Session/audio-focus audit for Single Workspace Rack integration — [#907](https://github.com/jannekbuengener/sample-brain/issues/907) (do not silently change runtime seams in docs-only work)
3. Bottom Live Kit / Rack projection — [#908](https://github.com/jannekbuengener/sample-brain/issues/908) after #906/#907
4. Arrangement — [#679](https://github.com/jannekbuengener/sample-brain/issues/679) remains **PARKED / UNDESIGNED — requires later explicit Owner design decision**

## 6. Documents this canon overrides (on conflict)

When wording conflicts, prefer this file and [`WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md`](WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md) over:

- Former multi-screen product navigation `Screen 1 → Screen 2 → Screen 3` as current user workflow
- “VST3-first / VST3 is the primary product interface” in `docs/PRODUCT_REQUIREMENTS.md`, `docs/TARGET_ARCHITECTURE.md` §10.2, `docs/DAW_INTEGRATION_SPEC.md`, `docs/SYSTEM_REQUIREMENTS.md`, `docs/product/README.md`, `docs/product/05_VST_PRODUCING_WORKSPACE_SPEC.md`
- Blanket “no drum patterns / no arrangement” non-goals that forbid user-authored Channel Rack patterns or a later Arrangement capability inside the Workbench

Historical VST pillar specs (#90–#95) remain **archived design notes** for a parked plugin path; they do not authorize VST as the current main producing path.

Existing runtime seams that still use screen-transition names (for example `enter_screen2` / `return_to_screen1` in [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md)) describe **current runtime ownership hooks**, not product-page navigation. [#907](https://github.com/jannekbuengener/sample-brain/issues/907) owns whether those seams need later repair/generalization. Do not treat them as authority to restore multi-screen product navigation.

## 7. Related live contracts

| Topic | Canonical live reference |
|-------|--------------------------|
| Single Workspace navigation / geometry | [`WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md`](WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md) |
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

Steps 2→3→4→5 are green (scheduling + production PCM provider + #698 voice lifecycle + Channel Rack QML historical delivery). The Channel Rack Python core, DEFAULT_ON initial step semantics (#677), extensible channels (#681), and Channel Rack QML (#678 / PR #755) are merged; parent epic #675 is CLOSED. Single Workspace product navigation is current; bottom-workspace Rack projection remains [#908](https://github.com/jannekbuengener/sample-brain/issues/908).
