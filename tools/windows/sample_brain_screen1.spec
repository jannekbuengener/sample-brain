# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec — #729 fallback when Nuitka+librosa is blocked."""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

REPO = Path(SPECPATH).resolve().parents[1]
ENTRY = REPO / "tools" / "windows" / "sample_brain_gui_entry.py"
DLL = REPO / "native" / "audio" / "build" / "bin" / "Release" / "samplebrain_audio.dll"
# Single runtime truth: path and filename are owned by the brand slot
# (src/workbench_brand_motion.py resolve_brand_slots). The QML binds
# analysisBrandBrain to brandBrainUrl, so the frozen build must carry this
# exact file at exactly this repo-relative destination.
SCREEN1_BRAND_ASSET = (
    REPO
    / "docs"
    / "assets"
    / "portfolio"
    / "references"
    / "brand"
    / "sample_brain_logo_primary.png"
)
SCREEN1_BRAND_ASSET_DEST = (
    Path("docs") / "assets" / "portfolio" / "references" / "brand"
)

datas = []
binaries = []
hiddenimports = [
    "src",
    "src.workbench_distributable_main",
    "src.workbench_qml",
    "src.workbench_qml_runtime",
    "src.workbench_library",
    "src.native_audio",
    "soundfile",
    "librosa",
    "numpy",
    "scipy",
    "sqlalchemy",
]

# Collect PySide6 / shiboken runtime (QML + platforms). Broader than ideal, but
# Screen-1 loadData still needs QtQuick/platform plugins present.
for pkg in ("PySide6", "shiboken6"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

binaries += collect_dynamic_libs("soundfile")

if DLL.is_file():
    binaries.append((str(DLL), "."))

# Screen-1 brand runtime asset (required for the frozen analysis/loading brand
# Image; fail closed so the distributable never ships without it). Datas land
# under <bundle>/_internal, where the frozen resolvers' repo-root logic points.
if not SCREEN1_BRAND_ASSET.is_file():
    raise SystemExit(f"REQUIRED Screen-1 brand asset missing: {SCREEN1_BRAND_ASSET}")
datas.append((str(SCREEN1_BRAND_ASSET), str(SCREEN1_BRAND_ASSET_DEST)))

a = Analysis(
    [str(ENTRY)],
    pathex=[str(REPO)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "transformers",
        "audio_separator",
        "sqlite_vec",
        "beat_this",
        "pytest",
        "tkinter",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SampleBrain",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SampleBrain",
)
