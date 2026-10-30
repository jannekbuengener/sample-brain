# FL Workflow Zero-Touch Recorder (#1321)

Durable dual-plane recorder for parent **#1319**. Evolves the #1320 probe into a long-lived local sidecar.

**Not** Sample Brain core product runtime. **Not** ADR-0006 measurement. **Not** #1322 analyzer.

Contract: [`docs/rnd/FL_WORKFLOW_RECORDER_1321.md`](../../docs/rnd/FL_WORKFLOW_RECORDER_1321.md)

## Layout

```text
%LOCALAPPDATA%/sample-brain/workflow-observer/
  workflow.sqlite3
  spool/fl-events.jsonl
  spool/windows-events.jsonl
  state/health.json
  logs/
```

## One-time setup (Windows)

1. Ensure MIDI ports from #1320: IN `Sample Brain Observer`, OUT `Sample Brain Observer Out`, FL pair `240`.
2. Install FL device script:

```powershell
cd <repo>\tools\fl_workflow_recorder
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

3. In FL Studio → Options → MIDI Settings: Controller type **SB Workflow Observer** on that input (OUT paired).
4. Register login autostart:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_autostart.ps1
Start-ScheduledTask -TaskName SampleBrainWorkflowObserver
```

5. Status:

```powershell
cd <repo>\tools\fl_workflow_recorder
python -m fl_workflow_recorder status
python -m fl_workflow_recorder midi-check --json
```

Disable: `uninstall_autostart.ps1` then optional `uninstall.ps1`.

## Privacy

Fail-closed. No typed characters, clipboard, screenshots, audio, out-of-FL keylogging, private paths in durable props.

## Tests

```powershell
python -m pytest -q tests/test_fl_workflow_recorder.py
```
