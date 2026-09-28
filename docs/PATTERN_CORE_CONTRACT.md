# Pattern Core Contract (Minimal) — Sample Brain

Status: **IMPLEMENTED on `main`** — `src/pattern_core.py` via PR #656;  
extensible user-added channels via issue #681.  
Not a Channel Rack UI spec. Not a full DAW event model.

Parent: [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md) build-order step 3.  
Depends on: [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md) (**completed** on `main`, PR #647).

## Purpose

Define the smallest Python-owned musical model so a later sequencer can fire sample triggers from Live Kit channels **and** additional user-added rack channels without inventing Screen-2 UI, mixer, arrangement, or a plugin host.

## Vocabulary

| Term | Meaning |
|------|---------|
| **Channel** | Stable instrument lane with opaque `channel_id`. May reference a sample path and optionally Live Kit provenance. Does not own audio bytes. Does not imply "exactly one canonical Live Kit slot". |
| **Pattern** | Finite loop of musical length that holds triggers for one or more channels. |
| **Trigger / Event** | Point trigger: at musical position P, fire channel C (optional velocity later). No pitch/stretch required for v1. |
| **Musical position** | Session grid position derived from existing `TempoMap` (quarter notes → bar/beat). Not source `BeatGrid`. Not wall-clock ms as authority. |
| **Slot / channel ID** | Stable identifier independent of display labels. |

## Stable IDs

### Channel ID

- Format: opaque stable string.
- **Live Kit seed channels** (frozen): e.g. `ch_kick`, `ch_closed_hat`; mapping implemented in `src/pattern_core.py` and must remain stable.
- **User-added rack channels**: opaque IDs allocated outside the Live Kit table (e.g. `ch_user_1`). They must **not** reuse a canonical Live Kit `channel_id`.
- Live Kit taxonomy labels (`"Kick"`, `"Closed Hat"`) remain **display / mapping** keys for seed channels only.
- Mapping: each canonical Live Kit `(group, slot)` maps 1:1 to one `channel_id` for the seed set.
- Renaming a display label must **not** change `channel_id`.

### Pattern ID

- Opaque stable string per pattern instance in the session (e.g. `pat_…`).
- v1 may hold a single active pattern; multi-pattern banks are allowed later without changing Trigger shape.

### Sample reference on a Channel

- Channel stores a **reference**, not PCM.
- v1 recommended ref: filesystem `path` string consistent with `WorkbenchRow.path` / playlist precedent.
- `sample_path` may be `None` (empty lane). A future non-sample instrument/plugin source is a **seam only** — not modeled in this contract beyond not forcing every channel to be a Live Kit sample slot.
- Library DB id is **not** required for v1 runtime; persistence policy is later.
- Missing / unloadable path → channel stays assigned but trigger is a soft miss (fail-soft; exact error surfacing at sequencer slice).

## Minimal data shapes (conceptual — not schema)

```text
Channel {
  channel_id: str               # stable opaque
  live_kit_group: str | None    # Live Kit provenance; None for user-added
  live_kit_slot: str | None     # Live Kit provenance; None for user-added
  sample_path: str | None       # reference; None = empty channel
}

Trigger {
  channel_id: str               # opaque; not globally limited to Live Kit IDs
  position: MusicalPosition | quarter_note Fraction
  # velocity: optional later
}

Pattern {
  pattern_id: str
  length_quarter_notes: Fraction   # e.g. 4 bars * beats_per_bar
  triggers: list[Trigger]
}
```

### Channel validation

- Live Kit seed channel: both `live_kit_group` and `live_kit_slot` set → pair must be a known `LIVE_KIT_SLOT_MAPPING` entry and `channel_id` must match the frozen table (fail-closed on mismatch).
- User-added channel: both provenance fields `None` → `channel_id` must be a non-empty opaque ID that is **not** a canonical Live Kit ID (no fake Live Kit slot required).
- Partial provenance (only group or only slot) is invalid.

### Trigger validation

- `Trigger` itself accepts any non-empty opaque `channel_id` plus a valid `Fraction` position.
- Membership ("does this trigger refer to a channel that exists in this rack/pattern context?") is validated at the **rack / session / planner boundary** (e.g. `ChannelRackState`, `toggle_step`, `require_triggers_reference_known_channels`, and the public `plan_pattern_once` seam), not against a global hardcoded Live Kit ID universe.
- Phantom channel IDs must fail closed at that boundary. Unknown channel ≠ missing `sample_path` (empty path on a known channel remains fail-soft).

Reuse existing types where possible:

- `MusicalPosition` / `TempoMap` from `src/session_grid.py`
- Live Kit taxonomy from `src/workbench_live_kit.py` (`LIVE_KIT_SLOT_MAPPING`)

## Ownership

- Pattern core is **Python-owned**, same session as `LiveKitState`.
- QML/Tk only project and send intents (add/remove trigger, set length, add channel) through an adapter — **no** pattern truth in QML.
- Kit assignments remain in `LiveKitState`; Live Kit seed Channels **reference** kit slots via provenance + `channel_id`. User-added channels have no Live Kit provenance.

## Relationship to Live Kit

```text
LiveKitState.assign(group, slot, row)
        │
        ▼
Channel (seed) .sample_path  ← derived / synced from kit assignment
        │
        ▼
Trigger(channel_id, position) inside Pattern

+ Add Channel (later UI) → Channel (user-added, no Live Kit slot)
        │
        ▼
same Trigger / Pattern substrate
```

Product rule: Live Kit is the **initial seed** for the Channel Rack, not a fixed channel universe. Samples stay library assets.

## Explicit non-goals (this contract)

- Screen-2 / Channel Rack widgets / `+` button UI
- VST3 / CLAP / plugin host / device chain / presets / plugin routing
- Piano roll / note duration / MIDI export
- Arrangement timeline / clips on a song ruler
- Mixer, sends, buses, live gain automation
- Track / device / routing graphs
- PPQ / MIDI tick layer (quarters suffice)
- Pitch, stretch, resynthesis
- Vocal/beatbox → pattern generation
- Persistence / DB tables
- BeatGrid as pattern authority (source analysis stays separate)

## Sequencer handoff (step 4 — implemented separately)

The one-pass scheduling seam is implemented in `src/sequencer_playback.py` via PR #663. A production PCM cache/decode provider for its injected `pcm_for_path` dependency is still pending:

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
- [x] User-added channels without Live Kit provenance (#681)
- [x] Trigger membership validated at rack/context boundary, not only against Live Kit IDs (#681)

## Next

Session ownership (#647), Pattern Core (#656), the sequencer scheduling seam (#663), Channel Rack Python core (#667), and extensible channel identity (#681) are on `main` (or in flight). The production PCM cache/decode provider (#676) and initial step semantics (#677) must complete before Screen-2 QML (#678) starts.
