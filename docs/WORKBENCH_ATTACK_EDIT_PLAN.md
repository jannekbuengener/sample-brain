# Workbench Attack Edit Plan

**Status:** Attack edit mode v1 shipped on `main` (toggle + single-click set + clear). Read-only attack marker (PR #143). Attack **suggestion** (`suggest_attack_ms`) is analysis-only — user must explicitly accept before persisting; original files unchanged.  
**Parent:** [#117 — workbench usability and library workflow follow-ups](https://github.com/jannekbuengener/sample-brain/issues/117)  
**Related:** [`WORKBENCH_CUE_METADATA_PLAN.md`](WORKBENCH_CUE_METADATA_PLAN.md), [`WORKBENCH_LOOP_EDIT_PLAN.md`](WORKBENCH_LOOP_EDIT_PLAN.md)

## 1. Goal

Let producers **set and clear** `attack_ms` in local workbench metadata without modifying original audio files. Attack is already **visible** as a dashed gold marker when `attack_ms` is set (PR #143).

## 2. Cue vs Attack (product semantics)

| Field | Meaning | Preview impact today | Typical use |
|---|---|---|---|
| `cue_start_ms` | Audition / export start point | Preview begins here | Trim head, FL slice offset |
| `attack_ms` | Onset / transient peak | None (marker only) | Visual reference, future auto-trim hint |

They may coincide but are **independent** fields. Setting attack must not change cue unless the user explicitly sets cue (Shift+left-click).

## 3. Current waveform bindings (do not break)

| Input | Behavior (normal mode) | Persists |
|---|---|---|
| Left-click | Play from saved `cue_start_ms` | No |
| Right-click | Temporary play from click position | No |
| Shift + left-click | Set `cue_start_ms` | Yes |
| Loop-edit mode ON | Two left-clicks set loop bounds | Yes |
| Double-click row / Space | Toggle preview | No |

## 4. Constraints

- Original audio files never modified.
- No preview-from-attack in v1 edit (preview stays cue-based).
- Reuse `save_workbench_sample_cue` / `WorkbenchCueMetadata`.
- Loop-edit and attack-edit modes are **mutually exclusive** (only one armed at a time).
- No librosa auto-detect in the first edit slice (separate `workbench_attack_detect_suggest`).

## 5. Option matrix

| Option | Set attack | Clear attack | Conflicts | Discoverability |
|---|---|---|---|---|
| **A. Attack-edit mode toggle** | Single left-click on waveform | Button “Attack löschen” | None if exclusive with loop mode | High |
| **B. Alt + left-click** | Alt+left at x | Alt+Shift+click or button | Low modifier collision | Low without hint |
| **C. Ctrl + left-click** | Ctrl+left at x | Button | Ctrl unused today | Medium |
| **D. Separate attack slider** | Drag slider | Reset button | No click conflict | Adds chrome |

## 6. Recommendation (v1 edit)

**Primary: Option A — Attack-edit mode toggle** (next to loop controls).

### Flow

1. User enables **“Attack bearbeiten”** → loop mode turns off; hint switches to attack mode text.
2. Status: `Attack bearbeiten aktiv — Klick auf Waveform`.
3. Single left-click writes `attack_ms`, preserves `cue_start_ms` and loop fields.
4. Mode exits automatically; dashed attack marker redraws.
5. **“Attack löschen”** sets `attack_ms` to `NULL`.

### Why not Alt/Ctrl+click (Options B/C)

Loop edit already uses a mode toggle successfully (PR #141). A single-point attack fits the same pattern with **one click** (simpler than loop’s two-click flow). Modifier chords stay available for power users later.

## 7. Validation (reuse existing)

`validate_workbench_cue_metadata` enforces `0 <= attack_ms < duration_ms` when set. UI shows status error on validation failure.

## 8. Explicit non-goals (attack edit v1)

- Preview from attack position
- Auto onset detection during edit
- Writing attack into `catalog.db` / FL export
- Changing original WAV/FLAC/MP3 on disk
- Coupling attack to cue automatically

## 9. Suggested implementation slices

1. `workbench_attack_edit_mode_v1` — toggle + single-click set + clear; mutual exclusion with loop mode.
2. `workbench_attack_edit_usage_help` — dynamic hint for attack mode.
3. `workbench_attack_detect_suggest` — optional librosa onset → `attack_ms` suggestion (analysis path only).

## 10. Open product question (non-blocking)

Should setting attack offer “also move cue here”?  
**Plan default:** no — keep fields independent; combined action is a follow-up UX polish slice.

---

*Refs #117 — planning only; does not close the parent issue.*
