# Windows Screen-1 tester distributable (#729)

## Goal

Ship a portable Windows ZIP an external tester can extract and double-click —
no Python, Git, Visual Studio, or repo checkout.

## Preferred packager

`pyside6-deploy --dry-run` documents the intended Nuitka standalone invocation.

**Documented blocker (2026-09-30):** Nuitka 2.7.12 / 2.8.10 / 4.1.1 all fail
while analyzing `librosa` (`lazy_loader` missing `_StubVisitor`).

**Authorized fallback:** PyInstaller onedir via
[`sample_brain_screen1.spec`](sample_brain_screen1.spec).

## Build

From a Python **3.12.10** venv:

```powershell
python -m pip install -e .
python -m pip install -r tools/windows/requirements-packaging.txt
powershell -ExecutionPolicy Bypass -File .\tools\windows\build_distributable.ps1 -BuildNative
```

`requirements-packaging.txt` pins **PySide6==6.11.2**, Nuitka, and PyInstaller for the
release path. The build script **fails closed** if Python or PySide6 do not match.

Produces `dist/packaging/SampleBrain-Screen1-Pilot-<build-id>-win64.zip` plus
`.sha256` sidecar. Entry: `SampleBrain/SampleBrain.exe` (QML Screen 1).

Native `samplebrain_audio.dll` is **required** for packaging acceptance
(copied from `native/audio/build/bin/Release/` into the standalone folder).

`pysidedeploy.spec` is only patched as a **staged copy** under `dist/packaging/stage-*`;
the tracked file stays clean. Shipped `BUILDINFO.txt` uses relative evidence IDs only
(no machine-local absolute paths).

## State

Distributable launcher defaults workbench state to
`%LOCALAPPDATA%\SampleBrain\state` when `SAMPLE_BRAIN_WORKBENCH_STATE_DIR` is
unset. Existing env overrides are preserved.

Screen-1 background PNG is packed into the onedir tree
(`docs/assets/portfolio/references/screen1_background_reference.png`) and
resolved via `sys._MEIPASS` / exe-adjacent fallback — no repo checkout required.

## Not in this slice

OneFile, MSI/MSIX, installer, auto-updater, CI packaging workflow, Screen 2/3.
