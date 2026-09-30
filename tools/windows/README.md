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
# From a packaging venv with Python 3.12.10 + pip install -e ".[qtquick]"
# + tools/windows/requirements-packaging.txt
powershell -ExecutionPolicy Bypass -File .\tools\windows\build_distributable.ps1 -BuildNative
```

Pipeline: preferred `pyside6-deploy` → Nuitka `standalone`. If Nuitka hits the documented
librosa/lazy_loader blocker, the build script uses **PyInstaller onedir** fallback.
Output: `SampleBrain-Screen1-Pilot-<build-id>-win64.zip` with `SampleBrain.exe` (QML Screen 1).
See `TESTER_NOTE.md`.

No OneFile / MSI / installer / auto-updater in this slice.
