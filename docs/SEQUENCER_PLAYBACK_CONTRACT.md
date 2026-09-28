# Sequencer Playback Contract (Minimal) — Sample Brain

Status: **DOCS_GATE** definition only. **Not implemented.**  
Blocked behind: [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md) + [`PATTERN_CORE_CONTRACT.md`](PATTERN_CORE_CONTRACT.md).

Parent: [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md) build-order step 4.

## Goal

Schedule Pattern triggers onto the native engine without Screen-2 UI and without using the monophonic audition owner as the polyphonic scheduler.

## Pipeline

```text
Pattern playhead / upcoming triggers
  → musical position (quarter / MusicalPosition)
  → TempoMap → session/engine frame
  → ensure PCM cache entry for channel.sample_path
  → NativeAudioEngine.create_voice (or reuse pooled voice)
  → schedule_voice_start(voice_id, engine_frame)
```

## Ownership rules

| Concern | Owner | Must not |
|---------|-------|----------|
| Pattern truth | Pattern core (Python) | Live in QML |
| Musical → frame map | `TempoMap` / `SessionTransport` (`src/session_grid.py`) | Use wall-clock or preview `start_ms` as authority |
| Voice schedule | `NativeAudioEngine` (`src/native_audio.py`) | Route through `WorkbenchPreviewPlayer` |
| Screen-1 audition | `TransportAwarePreview` | Own polyphonic pattern voices |
| PCM cache | New small Python cache (path → float32 buffer) | Decode inside audio callback; commit audio |

## Constraints from live code

- `SB_MAX_VOICES = 32` — pattern polyphony must fail soft or voice-steal under explicit policy (product decision at TEST_GATE).
- Voice create copies PCM into the engine — cache lifetime and re-trigger policy need tests.
- `schedule_events_in_buffer` is a buffer-window helper only; the sequencer still decides which absolute frames to arm ahead of time.
- Source `BeatGrid` stays analysis/edit time; pattern scheduling uses session `TempoMap` unless a later product decision adds BeatGrid sync.

## Non-goals

- Screen-2 UI
- SYNC rate / key-lock as v1 requirement (may reuse later)
- Mixer / per-voice live gain FFI
- Arrangement timeline
- Piano-roll note lengths
- Pitch / stretch

## Acceptance (future product_code slice)

- [ ] Given a Pattern + TempoMap + cached paths, triggers schedule at expected engine frames in tests
- [ ] Concurrent triggers on different channels do not go through `TransportAwarePreview`
- [ ] Empty / missing sample_path does not crash the engine loop
- [ ] No QML Channel Rack in the same slice unless explicitly scoped out

## Next

Only after this playback seam is green: Screen-2 Channel Rack UI (build-order step 5).
