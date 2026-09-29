# Sequencer Playback Contract (Minimal) — Sample Brain

Status: **SCHEDULER + PCM PROVIDER on `main` path** — `src/sequencer_playback.py` (#663) and production cache/decode provider `src/sequencer_pcm.py` + shared `src/native_pcm_decode.py` (#676).
Prerequisites [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md) and [`PATTERN_CORE_CONTRACT.md`](PATTERN_CORE_CONTRACT.md) are implemented.

Parent: [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md) build-order step 4.

## Goal

Schedule Pattern triggers onto the native engine without Screen-2 UI and without using the monophonic audition owner as the polyphonic scheduler.

## Pipeline

```text
Pattern playhead / upcoming triggers
  → musical position (quarter / MusicalPosition)
  → TempoMap → session/engine frame
  → SequencerPcmProvider (path → cached PcmBufferConfig)
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
| Offline decode | `native_pcm_decode.decode_native_pcm` | Run inside the audio callback |
| PCM cache | `SequencerPcmProvider` (`src/sequencer_pcm.py`) | Decode inside audio callback; commit audio |

## Cache policy (v1)

- Key: `(normalized path, provider sample_rate)`
- Identical path + sample_rate → cache hit (no re-decode)
- Different sample rates use distinct provider instances / keys (no false hits)
- Failed / empty / non-finite loads are **not** cached
- Bounded LRU eviction (`max_entries`, default 64)
- Keep `SequencerPcmProvider` at rack/session lifetime and pass it as
  `pcm_provider=` (or `pcm_for_path=`) across pattern passes; the ephemeral
  default inside `play_channel_rack_once` is one-shot only
- Prefer `warm_channel_rack_pcm(state, provider)` before anchoring playback so
  decode completes before engine-frame scheduling

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

## Implemented acceptance

- [x] Given a Pattern + TempoMap + cached paths, triggers schedule at expected engine frames in tests
- [x] Concurrent triggers on different channels do not go through `TransportAwarePreview`
- [x] Empty / missing `sample_path` fails soft without crashing the engine loop
- [x] Sequencer scheduling remains separate from Screen-2 QML
- [x] Production path provides a reusable `pcm_for_path` cache/decode provider outside the audio callback

## Next

Build-order step 4 (minimal sequencer playback including production PCM cache/decode) is complete on the #676 path. Screen-2 Channel Rack QML remains HOLD until explicitly scoped.
