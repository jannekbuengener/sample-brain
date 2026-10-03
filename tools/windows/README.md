# Windows helpers — Local Workbench

For source development, start the checkout explicitly:

```powershell
python -m src.cli workbench
```

This is intentionally a developer command: it runs the code in that checkout.

Screen-1 QML (dev):

```powershell
python -m src.cli workbench --qml-screen1
```

Screen-1 UI acceptance (local Windows desktop smoke; evidence outside repo):

```powershell
python tools/screen1_ui_acceptance.py
```

See `docs/SCREEN1_UI_ACCEPTANCE.md`.

## Producer runtime and desktop shortcut

Install the dedicated, provenance-checked runtime from a current `main` ref:

```powershell
git fetch origin --prune
powershell -ExecutionPolicy Bypass -File .\tools\windows\install_runtime_workbench.ps1 -CreateShortcut
```

This creates **Sample Brain Runtime Workbench** on your desktop. It uses the
runtime's dedicated `.venv` and checks its manifest, Git HEAD, working-tree
state, interpreter, and import root before starting the Workbench.

- A known older valid runtime may start as `STALE`; it never updates itself.
- Missing, dirty, or contradictory runtime provenance blocks the launch.
- The legacy `create_workbench_desktop_shortcut.ps1` helper now only creates
  this verified shortcut when the default runtime already exists.

This path still requires Git + Python. It is **not** the external tester
distributable.

## Tester distributable (#729)

Portable Windows ZIP for external testers (no Python/Git/checkout):

```powershell
# Packaging venv: exact Python 3.12.10
python -m pip install -e .
python -m pip install -r tools/windows/requirements-packaging.txt
powershell -ExecutionPolicy Bypass -File .\tools\windows\build_distributable.ps1 -BuildNative
```

Pipeline: `pyside6-deploy --dry-run` documents the preferred Nuitka `standalone`
invocation. The documented librosa/lazy_loader Nuitka blocker routes the build to
**PyInstaller onedir** (`sample_brain_screen1.spec`).
Output: `dist/packaging/SampleBrain-Screen1-Pilot-<build-id>-win64.zip` with
`SampleBrain/SampleBrain.exe` (QML Screen 1).
See `PACKAGING.md` and `TESTER_NOTE.md`.

No OneFile / MSI / installer / auto-updater in this slice.
