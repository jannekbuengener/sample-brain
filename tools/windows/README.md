# Windows helpers — Local Workbench

Start the Local Workbench from the CLI:

```powershell
python -m src.cli workbench
```

## Desktop shortcut

From the repository root (with a local `.venv` recommended):

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\windows\create_workbench_desktop_shortcut.ps1
```

This creates **Sample Brain Workbench** on your desktop. Double-click it to launch the workbench.

- The shortcut runs `tools\windows\start_workbench.cmd`.
- Working directory is the repo root (resolved relative to the script — no hardcoded paths in the repo).
- Python: `.venv\Scripts\python.exe` when present, otherwise `python` on `PATH`.

No installer or packaged EXE — local shortcut only.
