# FL Workflow Signal Probe (#1320) — throwaway

Throwaway dual-plane probe for GitHub issue **#1320** (parent #1319).  
**Not** the #1321 recorder. **Not** Sample Brain product runtime.

## Contracts

- Separate spools: `fl-events.jsonl` + `windows-events.jsonl` under `%LOCALAPPDATA%/sample-brain/workflow-observer-probe/`
- Fusion key: integer `t_wall_ns` (`t_utc` display-only; `t_mono_ns`/`seq` per-source only)
- Keyboard fail-closed: `KEY_CMD` identity only for modifier chords / F-keys / navigation / Escape/Delete/Backspace/Enter/Insert; printable unmodified → redacted `TEXT_ENTRY`
- Never call `playlist.selectTool()` for observation
- MIDI gate: normal Controller Type on an **existing** port; failure → `MIDI_DRIVER_REQUIRED` / `HOLD` / Owner GO — **no auto driver install**
- Capture `FL_VERSION` and `MIDI_SCRIPT_API_VERSION` separately

## Windows install

```powershell
cd <repo>\tools\fl_workflow_signal_probe
powershell -ExecutionPolicy Bypass -File .\install_fl_script.ps1
```

Then in FL Studio: Options → MIDI Settings → Controller type **SB Workflow Signal Probe** on an existing input. Confirm Script Output / `fl-events.jsonl`.

```powershell
python "$env:LOCALAPPDATA\sample-brain\workflow-observer-probe\win_fl_input_probe.py"
# run MATRIX_RUNBOOK.md actions
python "$env:LOCALAPPDATA\sample-brain\workflow-observer-probe\fuse_probe_matrix.py"
```

Never commit raw JSONL, private paths, or typed text.
