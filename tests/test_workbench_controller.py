from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from src.workbench_controller import analyze_folder_for_workbench
from tests.audio_fixtures import write_kick_transient_wav, write_sine_wav


PLAYLIST_KEYS = {
    "display_name",
    "relative_path",
    "bpm",
    "key",
    "key_conf",
    "loudness",
    "brightness",
    "sample_class",
    "pred_type",
    "status",
    "error",
}


@pytest.fixture
def sample_folder(tmp_path: Path) -> Path:
    samples = tmp_path / "samples"
    write_sine_wav(samples / "tone_a.wav", duration_sec=0.5, frequency_hz=440.0)
    write_kick_transient_wav(samples / "kick_b.wav", bpm=120.0, duration_sec=2.0)
    (samples / "notes.txt").write_text("not audio", encoding="utf-8")
    return samples


def test_controller_finds_audio_files(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder)

    assert result.summary["files_found"] == 2
    names = {row.display_name for row in result.rows}
    assert names == {"tone_a.wav", "kick_b.wav"}


def test_controller_summary_counts(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder, limit=1)

    assert result.summary["files_found"] == 1
    assert result.summary["analyzed_count"] + result.summary["error_count"] == 1
    assert len(result.rows) == 1


def test_controller_collects_errors(tmp_path: Path):
    samples = tmp_path / "broken"
    samples.mkdir()
    bad = samples / "broken.wav"
    bad.write_bytes(b"not-a-valid-wav")

    result = analyze_folder_for_workbench(samples)

    assert result.summary["files_found"] == 1
    assert result.summary["error_count"] == 1
    assert result.rows[0].status == "error"
    assert result.rows[0].error is not None


def test_playlist_rows_contain_expected_fields(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder)

    assert result.rows
    for row in result.rows:
        fields = row.playlist_fields()
        assert PLAYLIST_KEYS <= set(fields.keys())
        assert row.details
        assert "path" in row.details


def test_invalid_folder_raises(tmp_path: Path):
    missing = tmp_path / "does_not_exist"
    with pytest.raises(ValueError, match="Not a directory"):
        analyze_folder_for_workbench(missing)


def test_cli_help_includes_workbench():
    proc = subprocess.run(
        [sys.executable, "-m", "src.cli", "--help"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode == 0
    assert "workbench" in proc.stdout


def test_cli_import_does_not_load_tkinter():
    for name in ("tkinter", "src.workbench"):
        sys.modules.pop(name, None)

    import src.cli  # noqa: F401

    assert "tkinter" not in sys.modules
    assert "src.workbench" not in sys.modules


def test_workbench_module_imports_tkinter_only_when_loaded():
    mod = importlib.import_module("src.workbench")
    assert mod is not None
