# Sequencer Playback Contract (Minimal) — Sample Brain

Status: **SCHEDULER + PCM PROVIDER + VOICE LIFECYCLE on `main` path** —
`src/sequencer_playback.py` (#663 / #698), production cache/decode provider
`src/sequencer_pcm.py` + shared `src/native_pcm_decode.py` (#676).
Prerequisites [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md) and
[`PATTERN_CORE_CONTRACT.md`](PATTERN_CORE_CONTRACT.md) are implemented.

Parent: [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md) build-order step 4.

## Goal

Schedule Pattern triggers onto the native engine without Screen-2 UI and without
using the monophonic audition owner as the polyphonic scheduler. Total pattern
event count is independent of concurrent native voice capacity.

## Pipeline

```text
Pattern playhead / upcoming triggers
  → musical position (quarter / MusicalPosition)
  → TempoMap → session/engine frame
  → plan_pattern_once (pure; full event list)
  → SequencerPcmProvider (path → cached PcmBufferConfig)
  → PatternPassPlayer.tick (bounded materialization + IDLE reclaim)
       → NativeAudioEngine.create_voice
       → schedule_voice_start(voice_id, engine_frame)
  → (eager helper) schedule_pattern_once for single-shot create-budget paths
```

## Public surfaces

| Surface | Role |
|---------|------|
| `plan_pattern_once` | Pure planner — full pass event list; no native side effects |
| `PatternPassPlayer` | Stateful control-thread runtime for one finite pattern pass: injectable `lookahead_frames`, IDLE reclaim via `remove_voice`, materialize within lookahead while engine-global capacity remains |
| `schedule_pattern_once` | Compatible **eager** helper: create+schedule up to a create budget in one call; no reclaim / no multi-tick lifecycle |
| `play_channel_rack_once` | Channel Rack entry: plans, builds `PatternPassPlayer`, runs an initial `tick`, returns a handle so the caller can continue ticking |

Do not redefine `schedule_pattern_once` as a stateful first-tick API. Full passes
with more events than concurrent capacity must be driven through
`PatternPassPlayer`.

## Ownership rules

| Concern | Owner | Must not |
|---------|-------|----------|
| Pattern truth | Pattern core (Python) | Live in QML |
| Musical → frame map | `TempoMap` / `SessionTransport` (`src/session_grid.py`) | Use wall-clock or preview `start_ms` as authority |
| Voice schedule | `NativeAudioEngine` (`src/native_audio.py`) | Route through `WorkbenchPreviewPlayer` |
| Pass voice lifecycle | `PatternPassPlayer` (control thread) | Steal voices; run decode/Python in the audio callback |
| Screen-1 audition | `TransportAwarePreview` | Own polyphonic pattern voices |
| Offline decode | `native_pcm_decode.decode_native_pcm` | Run inside the audio callback |
| PCM cache | `SequencerPcmProvider` / `PathPcmCache` (`src/sequencer_pcm.py`) | Decode inside audio callback; commit audio |

## Capacity contract (`SB_MAX_VOICES`)

- `SB_MAX_VOICES = 32` is the engine-global bound on **registered** native voices
  (`snapshot.total_voice_count`), not a maximum pattern event count.
- `PatternPassPlayer` reclaims **owned** IDLE voices with `remove_voice`, then
  reads `snapshot.total_voice_count` and materializes at most
  `SB_MAX_VOICES - total_voice_count` new voices.
- Foreign / external voices already on the engine reduce remaining capacity.
  The player must never drive registered voices above 32 (no snapshot truncation).
- Temporally spread events (e.g. DEFAULT_ON 3×16 = 48, 4×16 = 64) must all be
  materialised frame-exactly when true concurrency stays ≤ 32 (short one-shots).
- When more than 32 voices are required at the **same** engine frame,
  fail soft with `skipped_voice_limit_count` — **no** voice stealing and no
  cutting of currently PLAYING one-shots to free slots.
- `schedule_pattern_once` keeps its eager create-budget fail-soft behaviour
  (no reclaim within that single call).

## Lookahead

- `lookahead_frames` is **explicit and injectable** on `PatternPassPlayer`
  (construction / tick). It is validated as a non-negative `int`.
- It is not a hardcoded product law such as `sample_rate // 10`.
- Callers supply the window (tests inject; production may later derive from
  engine/transport buffer configuration).
- Timing authority remains each planned `ScheduledTrigger.engine_frame` passed
  unchanged into `schedule_voice_start`.

## Stop / cleanup

- `PatternPassPlayer.stop` stops and removes **owned** live voices only.
- Foreign voices are left untouched.
- After stop, owned registered voices must be gone (no owned leaks).
- SCHEDULED / PLAYING / IDLE owned voices are all cleaned up on stop.

## Cache policy (v1)

- Key: `(canonicalize_pcm_path(path), provider sample_rate)` — absolute /
  collapsed / symlink-resolved when possible
- Identical path aliases + sample_rate → cache hit (no re-decode)
- Different sample rates use distinct provider instances / keys (no false hits)
- Failed / empty / non-finite loads are **not** cached
- Bounded LRU eviction (`max_entries`, default 64)
- Meaningful trailing whitespace in paths is preserved (only all-whitespace
  rejected)
- `play_channel_rack_once` requires `pcm_provider` or `pcm_for_path` — never
  creates an ephemeral provider per call
- `pcm_provider.sample_rate` must match `tempo_map.sample_rate`
- Prefer `warm_channel_rack_pcm(state, provider)` before anchoring playback so
  decode completes before engine-frame scheduling

## Constraints from live code

- Native PCM voices become `SB_VOICE_IDLE` at EOF but are **not** auto-removed;
  reclaim is explicit `remove_voice` on the control thread.
- Voice create deep-copies PCM into the engine.
- `schedule_events_in_buffer` is a buffer-window helper only; the sequencer /
  `PatternPassPlayer` decides which absolute frames to arm ahead of time.
- Source `BeatGrid` stays analysis/edit time; pattern scheduling uses session
  `TempoMap` unless a later product decision adds BeatGrid sync.
- Channel Rack DEFAULT_ON (#677) seeds 16 triggers per sample-bearing channel.
- Arrangement 32-field / 8-bar time + legacy migration *policy* are frozen in
  [`ARRANGEMENT_32_FIELD_TIME_CONTRACT.md`](ARRANGEMENT_32_FIELD_TIME_CONTRACT.md)
  (#1083). Runtime timing/migration execution is #1086; this playback contract
  does not silently reinterpret the live 16-step rack as 32 fields.

## Non-goals

- Screen-2 UI / QML
- Continuous looping **inside** `PatternPassPlayer` / a public
  `loop_pattern_forever` sequencer API (the one-pass primitive stays finite)
- Full transport engine / arrangement timeline / song mode
- Voice stealing as default polyphony policy
- Raising `SB_MAX_VOICES`
- SYNC rate / key-lock as v1 requirement (may reuse later)
- Mixer / per-voice live gain FFI
- Piano-roll note lengths
- Pitch / stretch

## Channel Rack multi-pass orchestration (#810)

Screen-2 Channel Rack Play may loop by **controller-owned** succession of
finite `play_channel_rack_once` / `PatternPassPlayer` passes. Musical pass
starts advance by `pattern.length_quarter_notes` on the live `TempoMap`
(quarter-note authority → engine-frame anchors). That is not Arrangement,
Timeline, or Clip semantics — only repeated pattern passes until Stop.

## Implemented acceptance

- [x] Given a Pattern + TempoMap + cached paths, triggers schedule at expected engine frames in tests
- [x] Concurrent triggers on different channels do not go through `TransportAwarePreview`
- [x] Empty / missing `sample_path` fails soft without crashing the engine loop
- [x] Sequencer scheduling remains separate from Screen-2 QML
- [x] Production path provides a reusable `pcm_for_path` cache/decode provider outside the audio callback
- [x] `PatternPassPlayer` materialises >32 temporally spread events without total-event drops while keeping `total_voice_count <= 32`
- [x] >32 simultaneous events at one frame fail soft without stealing
- [x] Global capacity respects foreign registered voices

## Next

Voice lifecycle (#698) is DONE_MERGED_CLOSED and unblocks full DEFAULT_ON kit playback for Screen-2.
Screen-2 Channel Rack QML (#678 / PR #755) and parent epic #675 are **DONE** on `main`.
