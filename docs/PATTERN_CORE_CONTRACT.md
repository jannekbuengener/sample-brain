# Pattern Core Contract (Minimal) — Sample Brain

Status: **IMPLEMENTED on `main`** — `src/pattern_core.py` via PR #656.  
Not a Channel Rack UI spec. Not a full DAW event model.

Parent: [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md) build-order step 3.  
Depends on: [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md) (**completed** on `main`, PR #647).

## Purpose

Define the smallest Python-owned musical model so a later sequencer can fire sample triggers from Live Kit channels without inventing Screen-2 UI, mixer, or arrangement.

## Vocabulary

| Term | Meaning |
|------|---------|
| **Channel** | Stable instrument lane that **references** a sample (via Live Kit slot / durable sample ref). Does not own audio bytes. |
| **Pattern** | Finite loop of musical length that holds triggers for one or more channels. |
| **Trigger / Event** | Point trigger: at musical position P, fire channel C (optional velocity later). No pitch/stretch required for v1. |
| **Musical position** | Session grid position derived from existing `TempoMap` (quarter notes → bar/beat). Not source `BeatGrid`. Not wall-clock ms as authority. |
| **Slot / channel ID** | Stable identifier independent of display labels. |

## Stable IDs

### Channel ID

- Format: opaque stable string, e.g. `ch_kick`, `ch_closed_hat`; the v1 mapping is implemented and frozen in `src/pattern_core.py`.
- Live Kit taxonomy labels (`"Kick"`, `"Closed Hat"`) remain **display / mapping** keys.
- Mapping: each canonical Live Kit `(group, slot)` maps 1:1 to one `channel_id` for v1.
- Renaming a display label must **not** change `channel_id`.

### Pattern ID

- Opaque stable string per pattern instance in the session (e.g. `pat_…`).
- v1 may hold a single active pattern; multi-pattern banks are allowed later without changing Trigger shape.

### Sample reference on a Channel

- Channel stores a **reference**, not PCM.
- v1 recommended ref: filesystem `path` string consistent with `WorkbenchRow.path` / playlist precedent.
- Library DB id is **not** required for v1 runtime; persistence policy is later.
- Missing / unloadable path → channel stays assigned but trigger is a soft miss (fail-soft; exact error surfacing at sequencer slice).

## Minimal data shapes (conceptual — not schema)

```text
Channel {
  channel_id: str          # stable
  live_kit_group: str      # display/mapping
  live_kit_slot: str       # display/mapping
  sample_path: str | None  # reference; None = empty channel
}

Trigger {
  channel_id: str
  position: MusicalPosition | quarter_note Fraction
  # velocity: optional later
}

Pattern {
  pattern_id: str
  length_quarter_notes: Fraction   # e.g. 4 bars * beats_per_bar
  triggers: list[Trigger]
}
```

Reuse existing types where possible:

- `MusicalPosition` / `TempoMap` from `src/session_grid.py`
- Live Kit taxonomy from `src/workbench_live_kit.py` (`LIVE_KIT_SLOT_MAPPING`)

## Ownership

- Pattern core is **Python-owned**, same session as `LiveKitState`.
- QML/Tk only project and send intents (add/remove trigger, set length) through an adapter — **no** pattern truth in QML.
- Kit assignments remain in `LiveKitState`; Pattern/Channel **reference** kit slots via `channel_id`, they do not duplicate `WorkbenchRow` graphs unless a thin projection requires it.

## Relationship to Live Kit

```text
LiveKitState.assign(group, slot, row)
        │
        ▼
Channel.sample_path  ← derived / synced from kit assignment (policy at impl)
        │
        ▼
Trigger(channel_id, position) inside Pattern
```

Product rule: taking a Live Kit into the Channel Rack means channels are created/updated from current kit assignments; samples stay library assets.

## Explicit non-goals (this contract)

- Screen-2 / Channel Rack widgets
- Piano roll / note duration / MIDI export
- Arrangement timeline / clips on a song ruler
- Mixer, sends, buses, live gain automation
- PPQ / MIDI tick layer (quarters suffice)
- Pitch, stretch, resynthesis
- Vocal/beatbox → pattern generation
- Persistence / DB tables
- BeatGrid as pattern authority (source analysis stays separate)

## Sequencer handoff (step 4 — implemented separately)

The minimal playback seam is implemented in `src/sequencer_playback.py` via PR #663:

```text
pattern playhead (musical)
  → TempoMap.quarter_note_to_frame / bar_beat_to_frame
  → NativeAudioEngine.schedule_voice_start(voice_id, engine_frame)
  → PCM from cache keyed by sample_path (decode outside audio callback)
```

Audition (`TransportAwarePreview`) remains separate and monophonic.

## Implemented acceptance

- [x] Stable `channel_id` mapping from `LIVE_KIT_SLOT_MAPPING`
- [x] Pattern + Trigger types with exact quarter-note `Fraction` positions compatible with `TempoMap`
- [x] Channels reference `sample_path` (or None); no audio file copies
- [x] Unit tests for mapping, trigger ordering, and length bounds
- [x] Pattern Core remains Python-owned; Screen-2 QML was not added in the Pattern Core slice

## Next

Session ownership (#647) → Pattern Core (#656) → Sequencer Playback (#663) → Channel Rack Python core (#667) are complete on `main`. Screen-2 QML is the next product layer.
