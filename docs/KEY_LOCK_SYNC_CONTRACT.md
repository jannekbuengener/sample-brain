# Key-Lock SYNC Mode Contract (#324)

## Overview

This document defines the contract for the **Key-Lock Sync** mode — the second SYNC mode alongside the existing **Rate Sync** mode (#323).

## Two Distinct SYNC Modes

### Mode A — Rate Sync (existing #323)
- **Tempo**: follows master BPM
- **Pitch**: follows tempo (rate = master_bpm / source_bpm)
- **Use case**: percussive material, clicks, drum loops

### Mode B — Key-Lock Sync (new #324)
- **Tempo**: follows master BPM (same ratio as Rate Sync)
- **Pitch/Root-Key**: preserved (original pitch maintained)
- **Backend**: Signalsmith Stretch v1.3.2 (MIT licensed)
- **Use case**: tonal material, melodic samples, sustained sounds

## Signalsmith Integration Details

### Pinned Versions
- **Signalsmith Stretch**: commit `57b93f4e9206a089a45387eaa39bdc9f310d3308` (v1.3.2)
- **Signalsmith Linear**: commit `5668673560146a9cfe38c25315071e3fd68c8317` (v0.3.1)
- **License**: MIT (both)
- **Source**: https://github.com/Signalsmith-Audio/signalsmith-stretch (mirror), original: https://signalsmith-audio.co.uk/code/stretch.git

### Key API Used
```cpp
signalsmith::stretch::SignalsmithStretch<float> stretch;
stretch.presetDefault(channels, sampleRate, false /* splitComputation */);
// For key-lock: NO pitch transpose (freqMultiplier = 1.0)
// Time-stretch achieved by different input/output buffer sizes
stretch.process(inputBuffers, inputSamples, outputBuffers, outputSamples);

// Latency (MUST be modeled and compensated)
int inputLatencyFrames = stretch.inputLatency();   // analysis latency
int outputLatencyFrames = stretch.outputLatency(); // synthesis latency
```

## Tempo Ratio (Shared with #323)

```
tempo_ratio = master_bpm / source_bpm
```

Examples:
- 128 → 132 BPM: ratio = 1.03125
- 128 → 140 BPM: ratio = 1.09375
- 140 → 128 BPM: ratio ≈ 0.9142857143

**Key-Lock uses the SAME ratio** — Signalsmith stretches time by this ratio while preserving pitch.

## DSP Latency Model (Mandatory)

Signalsmith introduces algorithmic latency that MUST be modeled and compensated:

### Latency Components
```cpp
// From Signalsmith Stretch:
int inputLatencyFrames = stretch.inputLatency();    // frames to supply input ahead
int outputLatencyFrames = stretch.outputLatency();  // frames output lags behind

// Effective grid compensation for a voice:
effective_grid_compensation_frames = inputLatencyFrames + outputLatencyFrames
```

### Grid Compensation Rule
The Session Grid remains the authority. A Key-Lock voice scheduled at musical position P must be **audibly aligned** to P. The native engine must advance the voice's scheduled start by `effective_grid_compensation_frames` so the audible output lands on the grid.

### Snapshot Exposure
The latency values MUST be exposed in the native snapshot for machine readability:
- `input_latency_frames`
- `output_latency_frames`
- `effective_grid_compensation_frames`

## Fallback Behavior

If Signalsmith is unavailable or initialization fails:
- **No crash**
- **Controlled fallback** to existing Rate Sync mode (#323)
- Status MUST report: `key_lock_active = false` (or equivalent)
- **Must NOT claim** pitch is preserved when fallback is active

## Acceptance Criteria

### Pitch Preservation (Objective Test)
- **Source**: 440 Hz sine wave at 128 BPM
- **Session**: 132 BPM with Key-Lock enabled
- **Expected**: Output dominant frequency ≈ 440 Hz (within documented tolerance, e.g., ±5 cents)
- **Rate Sync comparison**: Rate Sync would shift pitch to ~453 Hz

### Duration / Tempo
- Key-Lock output duration MUST change according to tempo_ratio
- 128 → 132: output ~3.125% shorter
- Simultaneously: pitch preserved

### Multiple Voices
- Voice A: 128 BPM → 132 BPM with Key-Lock
- Voice B: 140 BPM → 132 BPM with Key-Lock
- Both use SAME SessionTransport/Grid
- Individual stretch ratios, shared clock
- No growing relative drift

### Tempo Change During Playback
- Session: 132 BPM → 140 BPM at next bar boundary
- Key-Lock voices: adopt new stretch ratio at SAME frame
- No separate tempo timeline
- Signalsmith internal buffering allowed, but grid switch point authoritative

### Mode Toggle
- Rate Sync → Key-Lock → Rate Sync
- No cumulative ratio errors
- Always recompute from authoritative state

### Invalid BPM (per #323)
- None/0/negative/NaN source BPM → no stretch, not_syncable, no crash

## Non-Goals (Explicit)
- Rubber Band backend
- Major ↔ Minor conversion
- Auto-Tune / Pitch Correction
- Formant Designer
- Melody Editing
- Recording (#325)
- Editing (#326)
- HÄFTIG (#327)
- ASIO / VST / FL Plugin

## Hardware Uncertainty
- Full Windows/latency/device-recovery validation deferred to #328
- Report unmeasured values as `NOT_MEASURED`

## Files to Modify
- `native/audio/CMakeLists.txt` - add Signalsmith as vendored
- `native/audio/include/samplebrain_audio.h` - extend API with key-lock mode
- `native/audio/src/keylock_voice.h/.cpp` - new KeyLockVoice class
- `native/audio/src/engine.cpp` - integrate KeyLockVoice
- `src/native_audio.py` - extend Python bindings
- `src/session_grid.py` - no changes (shared tempo logic)
- `src/workbench_transport_adapter.py` - add key-lock mode toggle
- `tests/test_keylock_*.py` - new test files
- `native/audio/tests/test_keylock.cpp` - native unit tests

## Version/License Documentation
This contract itself serves as the version/license evidence for #324.