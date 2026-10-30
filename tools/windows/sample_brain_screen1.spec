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
    "sample_brain_analysis",
    # QML Screen-1 still imports workbench_transport_ui (Tk presentation helper).
    "tkinter",
    "tkinter.ttk",
    "soundfile",
    "librosa",
    "numpy",
    "scipy",
    "sqlalchemy",
]

# Collect PySide6 / shiboken runtime (QML + platforms). Broader than ideal, but
# Screen-1 loadData still needs QtQuick/platform plugins present.
# sample_brain_analysis is a required pure-Python dependency (bpm/matching import
# chain). Keep it in hiddenimports only — collect_all() on it can pull conflicting
# native binaries that break QtCore DLL load in the frozen onedir.
for pkg in ("PySide6", "shiboken6"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
try:
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(
        "sample_brain_analysis",
        include_py_files=True,
    )
    # Datas/py only — drop foreign binaries from analysis collect.
    datas += pkg_datas
    hiddenimports += pkg_hidden
except Exception:
    # Fail soft to hiddenimport string above; Analysis still traces imports.
    pass

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
    ],
    noarchive=False,
    optimize=0,
)

# Drop foreign ICU DLLs pulled from conda/Miniforge via PATH during Analysis.
# Qt6Core on this pilot must bind to Windows System32 icuuc.dll; shipping
# conda icuuc/icudt yields: ImportError DLL load failed while importing QtCore
# (WinError 127 / procedure not found).
def _is_foreign_icu(entry: object) -> bool:
    parts: list[str] = []
    if isinstance(entry, (tuple, list)):
        parts = [str(x) for x in entry]
    else:
        parts = [str(entry)]
    blob = " ".join(parts).lower().replace("/", "\\")
    name_hit = any(
        Path(part).name.lower().startswith(prefix)
        for part in parts
        for prefix in ("icuuc", "icudt", "icuin")
    )
    conda_hit = "\\library\\bin\\icu" in blob or "\\conda\\" in blob or "\\miniforge\\" in blob
    return name_hit or conda_hit


a.binaries = [entry for entry in a.binaries if not _is_foreign_icu(entry)]
a.datas = [entry for entry in a.datas if not _is_foreign_icu(entry)]

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
