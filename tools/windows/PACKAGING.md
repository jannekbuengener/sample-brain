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

The primary brand asset
(`docs/assets/portfolio/references/brand/sample_brain_logo_primary.png`) is
packed into the onedir tree and resolved by `resolve_brand_slots()` — the QML
`analysisBrandBrain` image binds `brandBrainUrl` from the brand runtime
payload. The build fails closed if the asset is missing. In a frozen onedir
build the bundled-module `__file__` points under `_internal`, so the runtime
resolver's repo-root logic lands on the same `_internal` root PyInstaller
fills with datas — no path duplication.

The historical Screen-1 background reference PNG is **not** packaged. It is
V7-rejected historical evidence (`visible: false` historical seam; solid-fill
runtime root), so the spec no longer carries or hard-requires it.

## Not in this slice

OneFile, MSI/MSIX, installer, auto-updater, CI packaging workflow, Screen 2/3.
