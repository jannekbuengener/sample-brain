# Screen-1 Preview Playhead Contract (#738)

**Status:** ACTIVE_SUPPORTING (production slice under #691)  
**Parent:** [#691](https://github.com/jannekbuengener/sample-brain/issues/691)  
**Research binding:** [#695](https://github.com/jannekbuengener/sample-brain/issues/695) / PR #736 → `KEEP_CANVAS_PLUS_ACTIVE_OVERLAY`  
**Issue:** [#738](https://github.com/jannekbuengener/sample-brain/issues/738)

## Playback-position audit (live)

| Question | Finding |
|---|---|
| Who starts preview? | `Screen1QmlInteractionAdapter` → `on_preview_requested` → session `_SessionAuditionPlayRow` → `TransportAwarePreview.play_row` (shared Browser / Harmony / Live Kit audition owner) |
| Who stops / Esc? | `stop_preview` → `on_preview_stopped` → `TransportAwarePreview.stop`; Esc in Browser/Harmony QML calls `stopPreview()` |
| Playing sample identity today? | Adapter `_preview_active: bool` only. Path lives on `TransportAwarePreview.current_path` / native path — **not** projected as playhead telemetry to QML |
| Duration? | Available on `WorkbenchRow.details` / file metadata; **not** part of a preview snapshot today |
| Current position? | **Not** exposed to Screen-1 QML. Legacy `WorkbenchPreviewPlayer` (winsound/subprocess) has **no** position API. Native voice keeps internal `pcm_position` but it is **not** in `sb_snapshot_t` / Python `Snapshot` |
| Engine-backed source playhead? | `WorkbenchTransportAdapter.get_source_frame()` exists for HÄFTIG and advances from **native engine frame deltas** (not wall clock). Not wired as Screen-1 preview progress; not gated on voice `PLAYING` for end-of-sample |
| How QML gets preview state? | `previewActive` boolean via interaction bridge only |
| Same authority Browser + Harmony? | Yes — both call the same adapter preview seam |
| Lifecycle signals? | Start / replace / stop through adapter; no progress / generation signal today |

### Classification

**`B — AUTHORITATIVE_PROGRESS_MISSING`** at the Screen-1 presentation boundary.

Not missing forever: the native audition path already has engine-backed transport source-frame authority. Legacy OS playback cannot supply position and must **fail closed** (no playhead), never approximate.

## Telemetry contract (smallest remediation)

`PreviewPlaybackSnapshot` owned by `TransportAwarePreview`:

- `playing: bool` — true only while the active native audition voice is `SCHEDULED` or `PLAYING`
- `sample_path: str` — resolved path identity of the active audition (empty when idle)
- `position_ms: int` — from refreshed transport source-frame / sample-rate (engine authority)
- `duration_ms: int` — captured at `play_row` from file duration metadata
- `progress: float` — `clamp(position_ms / duration_ms, 0, 1)` only when playing, duration > 0, position valid; else `0.0`
- `playback_instance_id: int` — native voice id (generation); `0` when idle

Rules:

- Refresh native snapshot before reading position.
- If native unavailable, legacy preview active, voice idle/stopping, source-frame unknown, or duration ≤ 0 → idle snapshot (no playhead).
- No QML/`Date.now`/`performance.now`/monotonic/NumberAnimation fake clocks.
- Normalized progress is derived presentation only; playback ownership stays in preview/transport.

## Overlay contract

- Canvas waveform body unchanged; no per-frame `Canvas.requestPaint()` for playback.
- Thin QML `Rectangle` playhead inside the existing waveform surface.
- Visible only when motion ≠ `off`, snapshot.playing, row identity matches, progress valid, row materialized.
- One global presentation refresh driver may re-read the snapshot; it never invents position.
- Browser and Harmonic Match share the same snapshot properties.
- ListView `reuseItems` fail-closed: no per-row timers; identity/progress come only from authoritative snapshot.
- Motion On / Reduced / Off consumed from #696 display preferences
  ([`WORKBENCH_DISPLAY_PREFERENCES.md`](WORKBENCH_DISPLAY_PREFERENCES.md);
  canonical `on` \| `reduced` \| `off`). Motion Off disables playhead and the
  presentation driver for this feature.
- Selection color updates must `requestPaint()` on selection change independently of playback.

## Non-scope

Renderer migration, intensity/glow/energy, spectrogram/FFT, Preferences UI
(owned by #696), Screen 2, audio-engine rewrite, exposing native `pcm_position`
(optional later improvement; not required for this slice while transport
source-frame is engine-backed).
