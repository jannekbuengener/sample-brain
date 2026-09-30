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

From a Python **3.12.10** venv with `pip install -e ".[qtquick]"` and
`pip install -r tools/windows/requirements-packaging.txt`:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\windows\build_distributable.ps1 -BuildNative
```

Produces `dist/packaging/SampleBrain-Screen1-Pilot-<build-id>-win64.zip` plus
`.sha256` sidecar. Entry: `SampleBrain/SampleBrain.exe` (QML Screen 1).

Native `samplebrain_audio.dll` is **required** for packaging acceptance.

## State

Distributable launcher defaults workbench state to
`%LOCALAPPDATA%\SampleBrain\state` when `SAMPLE_BRAIN_WORKBENCH_STATE_DIR` is
unset. Existing env overrides are preserved.

## Not in this slice

OneFile, MSI/MSIX, installer, auto-updater, CI packaging workflow, Screen 2/3.
