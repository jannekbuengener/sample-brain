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
| Play / Stop preview buttons | `_play_btn` / `_stop_btn` in detail header | ✅ PASS |
| Long path detail formatting | `format_path_display_lines` in detail panel (`tests/test_workbench_controller.py`) | ✅ PASS |
| CLI entrypoint | `python -m src.cli workbench --help` via `workbench` subcommand | ✅ PASS |
| Analysis limit restored on startup | `load_workbench_analysis_limit` + `tests/test_workbench_gui_smoke.py` | ✅ PASS |
| FL export button present / state | `_fl_export_btn` in `tests/test_workbench_gui_smoke.py` | ✅ PASS |
| Catalog→cache import button present | `_catalog_import_btn` in `tests/test_workbench_gui_smoke.py` | ✅ PASS |
| Playlist action column per sample row | `playlist_action` / `+ Playlist` in `tests/test_workbench_gui_smoke.py` | ✅ PASS |
| Playlist sidebar list present | `_playlist_list` in `tests/test_workbench_gui_smoke.py` | ✅ PASS |
| View toolbar visible by default | `_view_bar` mapped on startup | ✅ PASS |
| Edit menu toggles view toolbar | `_show_view_toolbar_var` + hide/show in `tests/test_workbench_gui_smoke.py` | ✅ PASS |
| View toolbar setting persists | `show_view_toolbar` in `workbench_view_settings.json` | ✅ PASS |
| Similar samples button + panel | `_similar_btn` / `_similar_tree` in `tests/test_workbench_gui_smoke.py` | ✅ PASS |
| Harmonie-Finder tab (center Notebook) | `_center_notebook` / `_harmony_frame` / `_harmony_tree` / `_harmony_ref_combo` in `tests/test_workbench_gui_smoke.py` | ✅ PASS |
| Harmonie-Finder match population | `test_workbench_harmony_finder_tab_populates` | ✅ PASS |

## Interactive manual smoke (producer workflow)

Not automated in CI. When running locally with a display:

1. Start: `python -m src.cli workbench`
2. Confirm **Library-Ordner** sidebar and playlist table are visible
3. Confirm waveform panel and usage hint under detail area
4. Add a local folder with `+` (user-owned path only — never commit private paths)
5. Select a sample → waveform envelope draws; for a deep folder path, detail panel shows collapsed/segment path lines (not one unreadable horizontal line)
6. **▶ Abspielen** in detail header → play from saved cue (or file start)
7. **■ Stop** → stop preview
8. **Left-click** waveform → play from saved cue
9. **Right-click** waveform → temporary play from click position
10. **Shift+left-click** → set cue (persists in `workbench_library.db`)
11. Change **Limit** (e.g. `25`), start analysis or leave the field — value persists in user-local state (`workbench_analysis_limit.txt` under `~/.sample-brain` or `SAMPLE_BRAIN_WORKBENCH_STATE_DIR`)
12. With analyzed playlist rows visible, click **FL exportieren** — writes FL Browser tags via existing `export_fl` logic (configured `fl_user_data_path`, `SAMPLE_BRAIN_FL_USER_DATA`, or folder picker)
13. In **Catalog lesen**, with visible catalog rows, click **Aus Catalog importieren** — confirm dialog shows import/skip/conflict counts; target folder must be registered in Library; cache rows update without re-analyzing audio and `catalog.db` stays read-only
14. Enable **Loop bearbeiten** → two clicks set loop region
15. **Loop vorhören** → plays loop region once (temp slice; original unchanged)
16. **Loop wiederholen** → repeats loop region until Stop
17. Enable **Attack bearbeiten** → single click sets attack marker
18. **Attack vorschlagen** → shows suggestion only; **Vorschlag übernehmen** persists after explicit click
19. Click **+ Playlist** on a sample row → choose existing playlist or enter a new name → status confirms assignment in `workbench_library.db` (`playlists` / `playlist_samples` tables)
20. Select a playlist under **Playlists** in the sidebar → sample table shows assigned samples; empty playlist shows 0 samples without crash
21. Under **Edit**, uncheck **Ansichtsleiste anzeigen** → view toolbar hides; sample table gains vertical space; section toggles remain in saved settings
22. Re-enable **Ansichtsleiste anzeigen** → toolbar returns with all section controls and help text
23. Click **Standardansicht wiederherstellen** → toolbar and all section toggles return to visible defaults
24. Select a sample with analyzed BPM → click **Ähnliche Samples** → suggestion table lists scored matches from loaded rows (reference excluded); right-click a suggestion for **Pfad kopieren** or **Preview**

## Harmonie-Finder (issue #213)

The center column is a `ttk.Notebook` with two pages: **Samples** (existing playlist + Similar-V1 panel) and **Harmonie-Finder**. The Harmonie-Finder finds musically related already-loaded `WorkbenchRow`s against a chosen reference:

- Reference picker (dropdown of loaded rows) plus **Aus Auswahl** to use the current playlist selection.
- Optional local text filter and an in-memory **Key-Override** (never mutates the row or DB).
- Results group into **Direkt / Verwandt / Transpose / Unsicher**, scored by `0.75 * harmony + 0.25 * BPM`, sorted by relation priority then score.
- Pitch-shift hint is limited to `-3..+3` semitones and shown only when a defined harmony relationship exists.
- Unknown mode stays cautious: same root with unknown mode is **Unsicher**, not Direkt. No relative/fifth/fourth claim without both modes known.
- Reuses existing Preview, path-copy, "Als Referenz", and playlist-focus actions. Similar-V1 is unchanged.

## Limitations

- Agent/CI environments cannot reliably perform full interactive GUI smoke (no display, no audio output assertion).
- Audio playback is not asserted in automated tests — backends are mocked in unit tests.
- Private sample paths and filenames must not appear in reports, docs, or commits.
- Original audio files are never modified by any workbench action.

## Safety contract (unchanged)

- Cue/loop/attack metadata and song-context playlist assignments live in `~/.sample-brain/workbench_library.db` (or `SAMPLE_BRAIN_WORKBENCH_STATE_DIR`).
- Preview may create **temporary** PCM WAV slices in the system temp directory; originals stay untouched.

---

*Refs #117 — status documentation only; does not close the parent issue.*
