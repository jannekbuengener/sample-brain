from __future__ import annotations

from pathlib import Path

import pytest

from src.workbench_distributable_buildinfo import (
    default_pilot_buildinfo_fields,
    format_buildinfo,
    validate_buildinfo_hygiene,
)

ROOT = Path(__file__).resolve().parents[1]


def test_buildinfo_rejects_absolute_windows_paths() -> None:
    dirty = (
        "build_id=demo\n"
        "nuitka_blocker_log=D:\\Temp\\sample-brain\\dist\\packaging\\nuitka-blocker.txt\n"
    )
    with pytest.raises(ValueError, match="absolute paths"):
        validate_buildinfo_hygiene(dirty)


def test_buildinfo_rejects_unix_home_paths() -> None:
    dirty = "native_audio_dumpbin_log=/home/builder/dumpbin.txt\n"
    with pytest.raises(ValueError, match="absolute paths"):
        validate_buildinfo_hygiene(dirty)


def test_default_pilot_buildinfo_uses_relative_evidence_ids_only() -> None:
    fields = default_pilot_buildinfo_fields(
        build_id="20260930T120000Z-abcdef123456",
        source_sha="a" * 40,
        python="3.12.10",
        pyside6="6.11.2",
        qt="6.11.2",
        pyinstaller="6.16.0",
        nuitka="4.1.1",
        artifact_zip="SampleBrain-Screen1-Pilot-20260930T120000Z-abcdef123456-win64.zip",
    )
    text = format_buildinfo(fields)
    assert "nuitka_blocker_evidence=nuitka-blocker-20260930T120000Z-abcdef123456.txt" in text
    assert (
        "native_audio_dumpbin_evidence="
        "dumpbin-samplebrain_audio-20260930T120000Z-abcdef123456.txt" in text
    )
    assert "pyinstaller=6.16.0" in text
    assert "D:\\" not in text
    assert "/home/" not in text
    assert "nuitka_blocker_log=" not in text
    assert "native_audio_dumpbin_log=" not in text


def test_build_script_patches_staged_spec_only() -> None:
    text = (ROOT / "tools" / "windows" / "build_distributable.ps1").read_text(encoding="utf-8")
    assert "nuitka_blocker_log=$BlockerNote" not in text
    assert "native_audio_dumpbin_log=$DumpbinLog" not in text
    assert "$StagedSpec" in text
    assert "WriteAllText($StagedSpec" in text
    assert "WriteAllText($SpecPath" not in text
    assert "write_buildinfo.py" in text
    assert 'throw "Pilot packaging requires exact Python 3.12.10' in text
    assert 'throw "Pilot packaging requires exact PySide6 6.11.2' in text


def test_packaging_requirements_pin_pilot_pyside6_and_pyinstaller() -> None:
    text = (ROOT / "tools" / "windows" / "requirements-packaging.txt").read_text(encoding="utf-8")
    assert "PySide6==6.11.2" in text
    assert "pyinstaller==6.16.0" in text
