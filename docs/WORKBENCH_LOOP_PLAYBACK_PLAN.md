# Workbench Loop Playback Plan

**Status:** Loop **once** preview shipped (`Loop vorhören`, PR #149). **Endless repeat** remains planned — this document defines scope, constraints, and a minimal v1 approach.  
**Parent:** [#117 — workbench usability and library workflow follow-ups](https://github.com/jannekbuengener/sample-brain/issues/117)  
**Related:** [`WORKBENCH_LOOP_EDIT_PLAN.md`](WORKBENCH_LOOP_EDIT_PLAN.md), [`WORKBENCH_CUE_METADATA_PLAN.md`](WORKBENCH_CUE_METADATA_PLAN.md), `src/workbench_preview.py`

## 1. Goal

Let producers **audition a saved loop region repeatedly** in the workbench without modifying original audio files. This extends the existing once-preview (`play_region`) with an optional **repeat mode** until the user stops playback.

## 2. What is shipped today

| Capability | Status |
|---|---|
| Loop region metadata (`loop_start_ms` / `loop_end_ms`) | ✅ Edit mode + validation |
| Loop region visible on waveform | ✅ Read-only overlay |
| **Once** loop preview (`Loop vorhören`) | ✅ Temp slice via `play_region`; original unchanged |
| Endless / repeat loop preview | ❌ Not shipped |
| Playhead sync during loop | ❌ Not shipped |

## 3. Safety contract (non-negotiable)

1. **Original audio files are never modified.**
2. Preview uses **temporary in-memory/temp-dir slices** only (`prepare_preview_playback_path`).
3. Loop playback must **stop cleanly** when the user clicks Stop, selects another sample, starts a different preview, or closes the workbench.
4. No new dependencies — reuse `soundfile`, `numpy`, platform backends in `workbench_preview.py`.
5. No export, trim, or bounce of source files.

## 4. Why endless loop is a separate slice

`WorkbenchPreviewPlayer` today fires playback and returns immediately. Platform backends differ:

| Platform | Backend | End-of-play detection | Repeat feasibility |
|---|---|---|---|
| Windows | `winsound.PlaySound` (async) | **No reliable callback** | Needs timer/thread polling or switch to subprocess for loop mode |
| macOS | `afplay` subprocess | `proc.poll()` | Timer or wait-thread can re-trigger |
| Linux | `aplay` subprocess | `proc.poll()` | Same as macOS |

Once-preview works because we do not need to know when playback ends. Repeat requires **knowing when each pass finishes** or **scheduling the next pass**.

## 5. Recommended v1 approach (minimal)

**Option A — subprocess + poll loop (preferred for cross-platform parity)**

1. Add `play_region_loop(path, start_ms, end_ms)` on `WorkbenchPreviewPlayer`.
2. For loop mode, always route through subprocess player (even on Windows) using a small bundled or PATH-resolved player, **or** use `winsound` only for once-preview and subprocess for loop-repeat on Windows.
3. Background thread:
   - Prepare temp slice once (reuse `prepare_preview_playback_path` with `end_ms`).
   - Start subprocess play.
   - Poll `proc.poll()`; when process exits and loop flag is still set, restart same temp file.
   - On `stop()`, set flag false, terminate process, unlink temp.
4. UI: new button **「Loop wiederholen」** next to **「Loop vorhören」**, or toggle on existing button (hold vs click) — prefer **separate button** for discoverability.
5. Status text: `Loop-Wiederholung aktiv (start–end ms) — Stop zum Beenden`.

**Option B — timer estimate (fallback only)**

- Estimate duration = `end_ms - start_ms`, schedule `root.after(duration, replay)`.
- **Risk:** drift, incorrect on non-WAV backends, bad for variable latency.
- Use only if subprocess path is blocked; not recommended as primary.

## 6. Stop semantics

Loop repeat must stop when:

- User presses **Stop** (Space toggle if same file, or explicit stop path)
- User starts another preview (cue play, right-click scrub, once loop, other sample)
- User closes workbench window (`WM_DELETE_WINDOW` → `preview.stop()`)
- Analysis starts (`_busy` guard — already used elsewhere)

Implementation: extend `_stop_unlocked()` to cancel loop thread + clear loop-active flag.

## 7. Temp file lifecycle

| Event | Action |
|---|---|
| Loop repeat starts | Create one temp slice for region |
| Each repeat pass | Reuse same temp path (no re-decode) |
| Stop / switch sample | `unlink(missing_ok=True)` under existing `_temp_lock` |
| Crash / exception | `finally` block cleans temp |

Do not accumulate multiple temp files per session.

## 8. UI scope (v1, small)

- One new button: **「Loop wiederholen」** (disabled when loop bounds missing)
- Reuse existing status bar for active/stop messaging
- No playhead animation, no BPM sync, no drag handles
- Mutual exclusion: starting loop repeat stops cue/once preview; starting cue/once stops loop repeat

## 9. Tests (no real audio output)

- Mock `play_fn` / loop thread scheduling
- Assert `stop()` clears loop-active state
- Assert temp slice prepared once per loop session (mock `prepare_preview_playback_path`)
- Assert invalid loop bounds return validation errors without playback
- Synthetic WAV in `tmp_path` only

## 10. Explicit non-goals

- Seamless gapless looping
- Synced playhead on waveform during repeat
- Writing loop metadata to `catalog.db` or FL export
- Auto-detect loop bounds
- Crossfade at loop boundaries
- New audio dependencies (pygame, miniaudio, etc.)

## 11. Suggested implementation slices

1. `workbench_loop_repeat_preview_v1` — `play_region_loop` + stop semantics + button + tests
2. `workbench_loop_repeat_ux_polish` — keyboard shortcut, hint text update
3. `workbench_loop_playhead_v2` — optional future; separate GO

## 12. Open product question (non-blocking)

Should **「Loop vorhören」** become a toggle (once vs repeat)?  
**Plan default:** keep **once** and **repeat** as separate explicit actions to avoid accidental endless playback.

---

*Refs #117 — planning only; does not close the parent issue.*
