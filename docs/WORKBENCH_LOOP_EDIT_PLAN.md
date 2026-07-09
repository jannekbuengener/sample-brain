# Workbench Loop Edit Plan

**Status:** Loop edit mode v1 shipped on `main`. Loop region **once** preview (`Loop vorhören`) shipped — temp slice only; no endless repeat; original files unchanged.  
**Parent:** [#117 — workbench usability and library workflow follow-ups](https://github.com/jannekbuengener/sample-brain/issues/117)  
**Related:** [`WORKBENCH_CUE_METADATA_PLAN.md`](WORKBENCH_CUE_METADATA_PLAN.md)

## 1. Goal

Let producers **set and clear** `loop_start_ms` / `loop_end_ms` in local workbench metadata without modifying original audio files. Loop region is already **visible** read-only when both values exist.

## 2. Current waveform bindings (do not break)

| Input | Behavior | Persists |
|---|---|---|
| Left-click | Play from saved `cue_start_ms` | No |
| Right-click | Temporary play from click position | No |
| Shift + left-click | Set `cue_start_ms` | Yes (`workbench_library.db`) |
| Double-click row / Space | Toggle preview | No |

Usage hint under waveform documents the three click modes (PR #139).

## 3. Constraints

- Original sample files must never be modified, trimmed, or exported by this feature.
- No loop playback in the first edit slice.
- No drag handles in v1 edit (markers are read-only today).
- Reuse existing metadata API: `save_workbench_sample_cue` / `WorkbenchCueMetadata`.
- Prefer discoverability without a large UI redesign.

## 4. Option matrix

| Option | Set loop start | Set loop end | Clear loop | Conflicts | Discoverability |
|---|---|---|---|---|---|
| **A. Loop-edit mode toggle** | Next left-click on waveform | Next left-click (2nd) or dedicated “Ende” click | Button “Loop löschen” or mode reset | None if mode is explicit | High (mode + status text) |
| **B. Context menu (right-click)** | Menu item at click ms | Second menu action | “Loop löschen” item | **Breaks** right-click temp play unless moved to Shift+right | Medium |
| **C. Ctrl + left / Ctrl + right** | Ctrl+left at x | Ctrl+right at x | Ctrl+Shift+click or menu | Low — modifiers free today | Low without hint update |
| **D. Shift + right-click** | Shift+right at x | Alt+Shift+right or second Shift+right | Keyboard/menu | Shift+left is cue; asymmetric | Medium |
| **E. Small loop buttons** | “Loop Start” arms click | “Loop Ende” arms click | “Loop löschen” | None | High but adds chrome |

## 5. Recommendation (v1 edit)

**Primary: Option A — Loop-edit mode toggle** (small control near waveform or in detail header).

### Flow

1. User enables **“Loop setzen”** (toggle or momentary arm).
2. Status bar: `Loop-Start: Klick auf Waveform` → first left-click writes `loop_start_ms`, preserves `cue_start_ms` and `attack_ms`.
3. Status bar: `Loop-Ende: Klick auf Waveform` → second left-click writes `loop_end_ms` (validated: `end > start`, within duration).
4. Mode exits automatically; waveform redraws read-only region (existing PR #138 logic).
5. **“Loop löschen”** sets both loop fields to `NULL` via `save_workbench_sample_cue`.

### Why not right-click menu (Option B)

Right-click is already **temporary audition**. Moving play-to-menu would regress the fastest “scrub this spot” gesture. A menu could be a **secondary** entry (e.g. “Ab hier abspielen”) but should not replace right-click play.

### Why not Ctrl+click alone (Option C)

Technically clean, but **not documented in the usage hint** and easy to miss. Acceptable as **power-user addition later** if mode toggle feels too heavy — not as sole v1 edit UX.

### Why not Shift+right-click (Option D)

Shift+left is cue. Using Shift+right for loop start only covers **one** boundary; end still needs a second gesture. Asymmetric and harder to explain than mode + two clicks.

## 6. Validation (reuse existing)

`validate_workbench_cue_metadata` in `workbench_library.py` already enforces:

- both loop fields set together
- `loop_end_ms >= loop_start_ms`
- bounds within `duration_ms`

Invalid pairs must not be saved; UI should show a short status error, not crash.

## 7. Explicit non-goals (loop edit v1)

- Loop playback / repeat preview
- Snapping to BPM grid
- Auto-detect loop bounds
- Writing loops into `catalog.db` or FL export
- Dragging loop handles
- Changing original WAV/FLAC/MP3 on disk

## 8. Suggested implementation slices (after GO)

1. `workbench_loop_edit_mode_v1` — toggle + two-click set + clear; tests with mocked canvas clicks; hint/status updates.
2. `workbench_loop_edit_ux_polish` — keyboard shortcut to clear loop; optional Ctrl+click shortcuts documented.
3. `workbench_attack_marker_v1` — separate slice (see cue metadata plan).

## 9. Open product question (non-blocking for plan)

Should loop edit be **allowed on all samples** or only when `duration_class == loop` / `pred_type` suggests loop?  
**Plan default:** allow manual override on any sample (metadata is user-owned); optional UI warning for non-loop classes is follow-up.

---

*Refs #117 — planning only; does not close the parent issue.*
