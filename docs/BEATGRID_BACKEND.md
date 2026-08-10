# BeatGrid Backend Adapter

Issue [#236](https://github.com/jannekbuengener/sample-brain/issues/236)
provides the runtime adapter for the BeatGrid part of Track Map v1. It keeps
beat and downbeat positions on the `AudioTimebase` supplied by
`src.canon_audio` and exposes backend provenance without requiring the
optional primary model in the core installation.

## Backend policy

`BeatGridAdapter(backend="auto")` uses one backend at a time:

1. `beat_this/final0` is the provisional primary.
2. `librosa` is attempted only when the primary is unavailable, fails, or
   returns no beat positions.
3. The fallback trigger is recorded as `fallback_reason`; a second heavy
   backend is never started in parallel.

Use `backend="beat_this"` for strict primary-only execution or
`backend="librosa"` for an explicit lightweight fallback run. The
`beat-this` package, PyTorch, and model weights remain optional and are not
added to the core requirements.

## Result contract

```python
from src.beat_grid import BeatGridAdapter
from src.canon_audio import probe_audio

timebase = probe_audio(working_audio_path)
if timebase is None:
    raise RuntimeError("Unable to probe working audio")
result = BeatGridAdapter(backend="auto").analyze(
    working_audio_path,
    timebase,
)
```

`BeatGridResult` contains:

- `status`: `ok`, `partial`, `no_result`, or `failed`
- `bpm`: an observed backend value or a median interval estimate
- `beats` / `downbeats`: sample indices plus derived `times_sec`
- `source`: backend name, package version, checkpoint, config, and fallback
  provenance
- `error`: stable code, message, and retryability when execution fails

`result.to_track_map_timeline()` emits the Track Map v1 `bpm`, `beats`, and
`downbeats` blocks. The adapter's `sample_indices` remain the authoritative
runtime representation; `times_sec` is the portable Track Map representation
derived from the same timebase.

## Fallback limits

The current `librosa` fallback provides BPM and beat positions. Librosa does
not provide an evidence-backed downbeat detector in this adapter, so its
downbeat block is `no_result` with reason code `DOWNBEATS_UNAVAILABLE` and the
overall result is `partial`. No final quality claim is made for private audio;
the provisional primary still requires the planned private pilot.
