# Workbench GUI Smoke — Status

**Status:** Programmatic startup smoke **PASS** on Windows (tkinter 8.6). Full interactive manual smoke is **LIMITED** in headless/agent environments.  
**Parent:** [#117 — workbench usability and library workflow follow-ups](https://github.com/jannekbuengener/sample-brain/issues/117)  
**Start command:** `python -m src.cli workbench` (or `sample-brain workbench`)

## What was verified

| Check | Method | Result |
|---|---|---|
| App constructs without exception | `tests/test_workbench_gui_smoke.py` | ✅ PASS |
| Library folder list widget present | `_library_list` Listbox | ✅ PASS |
| Waveform canvas present | `_waveform_canvas` | ✅ PASS |
| Usage hint visible | `WAVEFORM_USAGE_HINT` in `_waveform_usage_var` | ✅ PASS |
| Loop edit mode control | `_loop_edit_mode_var` | ✅ PASS |
| Attack edit mode control | `_attack_edit_mode_var` | ✅ PASS |
| Attack suggestion apply button | `_attack_suggest_apply_btn` | ✅ PASS |
| CLI entrypoint | `python -m src.cli workbench --help` via `workbench` subcommand | ✅ PASS |

## Interactive manual smoke (producer workflow)

Not automated in CI. When running locally with a display:

1. Start: `python -m src.cli workbench`
2. Confirm **Library-Ordner** sidebar and playlist table are visible
3. Confirm waveform panel and usage hint under detail area
4. Add a local folder with `+` (user-owned path only — never commit private paths)
5. Select a sample → waveform envelope draws
6. **Left-click** waveform → play from saved cue
7. **Right-click** waveform → temporary play from click position
8. **Shift+left-click** → set cue (persists in `workbench_library.db`)
9. Enable **Loop bearbeiten** → two clicks set loop region
10. **Loop vorhören** → plays loop region once (temp slice; original unchanged)
11. **Loop wiederholen** → repeats loop region until Stop
12. Enable **Attack bearbeiten** → single click sets attack marker
13. **Attack vorschlagen** → shows suggestion only; **Vorschlag übernehmen** persists after explicit click

## Limitations

- Agent/CI environments cannot reliably perform full interactive GUI smoke (no display, no audio output assertion).
- Audio playback is not asserted in automated tests — backends are mocked in unit tests.
- Private sample paths and filenames must not appear in reports, docs, or commits.
- Original audio files are never modified by any workbench action.

## Safety contract (unchanged)

- Cue/loop/attack metadata lives in `~/.sample-brain/workbench_library.db` (or `SAMPLE_BRAIN_WORKBENCH_STATE_DIR`).
- Preview may create **temporary** PCM WAV slices in the system temp directory; originals stay untouched.

---

*Refs #117 — status documentation only; does not close the parent issue.*
