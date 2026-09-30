# Product Workflow Canon — Sample Brain

Status: **canonical product-path decision** (2026-09-28).  
Supersedes older “VST3-first as primary producing path” and blanket “no patterns / no arrangement” wording in vision docs where those conflict with this file.

## 1. Internal producing workflow

The core producer path is **local Workbench**, not an external DAW and not a VST host:

```text
Library / Screen 1
  → Live Kit
  → Sample-Brain Channel Rack / Screen 2
  → later Arrangement mode / Screen 3
```

- No external DAW is part of this core workflow.
- FL Browser export remains a **legacy/fallback CLI** integration.
- VST3 / host-plugin work remains **parked** (see [#469](https://github.com/jannekbuengener/sample-brain/issues/469)) and is **not** the primary product path.

## 2. Screen intents (product, not implementation status)

| Screen | Intent | Status on `main` |
|--------|--------|------------------|
| Screen 1 | Library browse + Live Kit assignment | Live Kit + QML Screen-1 shell exist; Tk remains default/fallback |
| Screen 2 | Channel Rack — program patterns/triggers over Live Kit channels | **FOUNDATIONS READY / TECHNICALLY UNBLOCKED; PRODUCT PROGRAM PARKED** — session ownership, Pattern Core, sequencer scheduling, Channel Rack Python core, production PCM provider (#676), DEFAULT_ON initial step semantics (#677), extensible channels (#681), and voice lifecycle (#698) are DONE on `main`; Screen-2 QML (#678) is technically unblocked. Product execution remains **PARKED / NOT ACTIVE** and sequenced after the Screen-1 pilot gate (#727); no Screen-2 UI without explicit Owner-GO |
| Screen 3 | Arrangement mode over patterns/channels | **Not built** — must not be designed in Screen-2 slices |

## 3. Channel Rack product rules (Screen 2 intent)

These are product constraints for later implementation. They are **not** a claim that Screen 2 exists.

- Live Kit assignments can be taken into the Channel Rack (kit → channels) as the **initial seed**.
- The Channel Rack is **not** limited to the fixed Live Kit slot universe; user-added channels with opaque IDs (no fake Live Kit slot) are in scope for the Python core (#681).
- A sample remains the unchanged library asset; channels **reference** samples and do not duplicate audio files.
- Channel Rack is **pattern/trigger first** (grid programming).
- **Initial step semantics (v1, #677):** New sample-bearing Channel Rack channels initialize with every v1 step active. Empty channels initialize without triggers. Screen 2 uses DEFAULT_ON / subtractive programming: click removes an active step trigger; click again restores it. Pattern storage remains an explicit trigger list (no inverted / off-mask). There is no additive/subtractive mode selector or preference in v1.
- A later piano / event editor may share the same pattern substrate; it is **not** required for Screen-2 v1.
- Arrangement, mixer, sends, inserts, buses, and complex routing are **out of Screen-2 scope**.
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

- Pattern / trigger programming on a Channel Rack
- Later Arrangement mode that places patterns in session time
- Analysis “arrangement roles” on source tracks (Track Map) — **analysis vocabulary**, not Screen-3 Arrangement mode

Do not conflate Track Map / `arrangement_*` analysis contracts with Screen-3 Arrangement mode.

## 5. Build order (binding)

Foundation gates before Screen-2 UI (technical readiness):

1. **Product canon** (this document + PRD/architecture alignment)
2. **Session ownership** — one Live Kit truth; QML commands → native transport/audio — **DONE** (#647)
3. **Minimal Pattern Core** — Channel, Pattern, Trigger/Event, musical position, stable slot/channel IDs — **DONE** (#656)
4. **Minimal Sequencer Playback** — pattern position → `TempoMap` → scheduled engine frame → cached PCM voice — **DONE** (#663 scheduler + #676 PCM cache/decode provider + #698 voice lifecycle)
5. **Screen-2 Channel Rack UI** — Channel Rack Python core is **DONE** (#667); initial DEFAULT_ON step semantics are **DONE** (#677); extensible channels are **DONE** (#681); QML implementation (#678) is **technically unblocked**. Product execution remains **PARKED / NOT ACTIVE** and sequenced after Screen-1 pilot gate [#727](https://github.com/jannekbuengener/sample-brain/issues/727); do **not** start Screen-2 UI without explicit Owner-GO

`TECHNICALLY_UNBLOCKED` is not `CURRENT_PRODUCT_PRIORITY`.

## 6. Documents this canon overrides (on conflict)

When wording conflicts, prefer this file over:

- “VST3-first / VST3 is the primary product interface” in `docs/PRODUCT_REQUIREMENTS.md`, `docs/TARGET_ARCHITECTURE.md` §10.2, `docs/DAW_INTEGRATION_SPEC.md`, `docs/SYSTEM_REQUIREMENTS.md`, `docs/product/README.md`, `docs/product/05_VST_PRODUCING_WORKSPACE_SPEC.md`
- Blanket “no drum patterns / no arrangement” non-goals that forbid user-authored Channel Rack patterns or a later Screen-3 Arrangement mode

Historical VST pillar specs (#90–#95) remain **archived design notes** for a parked plugin path; they do not authorize VST as the current main producing path.

## 7. Related live contracts

| Topic | Canonical live reference |
|-------|--------------------------|
| Realtime Workbench boundary | `docs/REALTIME_WORKBENCH_SCOPE.md` |
| Screen-1 renderer lock | `LOCK_PYSIDE6_QML` in `docs/TARGET_ARCHITECTURE.md` |
| Session ownership (step 2 — done) | [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md), `src/workbench_session.py` |
| Pattern Core (step 3 — done, #656) | [`PATTERN_CORE_CONTRACT.md`](PATTERN_CORE_CONTRACT.md), `src/pattern_core.py` |
| Sequencer Playback (step 4 — done, #663 + #676) | [`SEQUENCER_PLAYBACK_CONTRACT.md`](SEQUENCER_PLAYBACK_CONTRACT.md), `src/sequencer_playback.py`, `src/sequencer_pcm.py`, `src/native_pcm_decode.py` |
| Channel Rack Python core (pre-UI — done, #667) | `src/channel_rack.py` |
| Live Kit state | `src/workbench_live_kit.py` |
| Session time / TempoMap | `src/session_grid.py` |
| Native voices | `src/native_audio.py` |
| QML Screen-1 shell | `src/workbench_qml.py` |

Steps 2→3→4 are green (scheduling + production PCM provider + #698 voice lifecycle). The Channel Rack Python core, DEFAULT_ON initial step semantics (#677), and extensible channels (#681) are merged; Screen-2 Channel Rack QML (#678) is **technically unblocked** but **product-parked** until after #727 and an explicit Owner-GO.
