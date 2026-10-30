# #1320 Controlled Probe Matrix Runbook

## Preconditions

1. `install_fl_script.ps1` has copied the device script.
2. FL Studio open on a blank/safe project (saved once to avoid Save-as modals).
3. MIDI Settings: Controller type = **SB Workflow Signal Probe** on an **existing** port.
4. `View → Script output` shows OnInit; `%LOCALAPPDATA%\sample-brain\workflow-observer-probe\fl-events.jsonl` grows.
5. If step 3–4 fail → `MIDI_DRIVER_REQUIRED` / `HOLD` / Owner GO. Stop. No driver install.
6. Start Windows probe:
   ```powershell
   python "%LOCALAPPDATA%\sample-brain\workflow-observer-probe\win_fl_input_probe.py"
   ```

## Actions (perform slowly; pause ~1s between)

| # | ACTION |
|---|---|
| 1 | Focus Browser; select a sample (no need to drag yet) |
| 2 | Focus Playlist; click; short left-drag |
| 3 | Change Playlist tool (Pencil/Brush/Cut) — observe only; never script `selectTool()` |
| 4 | Focus Piano Roll; click/drag a note region if present |
| 5 | Focus Channel Rack; toggle a step / select channel |
| 6 | Focus Mixer; nudge a fader |
| 7 | Open/focus a plugin; nudge one parameter |
| 8 | Transport Play; wait ~2s; Stop |
| 9 | Undo; Redo |
| 10 | Alt+Tab away from FL; return |
| 11 | Ctrl+Z (KEY_CMD); then type a few letters in Browser search (TEXT_ENTRY redacted) |

## Correlation sequences

```text
Playlist → tool/hint → mouse_down → drag → FL undo/state → play
Browser → sample interaction → Playlist
Plugin focus → param/input → Playlist
```

## After matrix

1. Stop Windows probe (Ctrl+C).
2. Optionally Reload script once; confirm no crash.
3. Fuse:
   ```powershell
   python "%LOCALAPPDATA%\sample-brain\workflow-observer-probe\fuse_probe_matrix.py"
   ```
4. Fill ACTION matrix from fused timeline; classify V1 / DEFERRED / BLIND_SPOTS.
