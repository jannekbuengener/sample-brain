from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from src.workbench_controller import (
    analyze_folder_for_workbench,
    error_message_for_code,
    validate_workbench_folder,
)
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
    "error_code",
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
    row = result.rows[0]
    assert row.status == "error"
    assert row.error_code is not None
    assert row.error == error_message_for_code(row.error_code)
    assert row.error != "Could not extract features"
    assert "error_detail" in row.details


def test_progress_callback_reports_current_and_total(sample_folder: Path):
    events: list[tuple[int, int, str, str]] = []

    def progress(current: int, total: int, name: str, phase: str) -> None:
        events.append((current, total, name, phase))

    result = analyze_folder_for_workbench(sample_folder, progress_callback=progress)

    assert result.summary["files_found"] == 2
    analyzing = [e for e in events if e[3] == "analyzing"]
    assert len(analyzing) == 2
    assert analyzing[0][0] == 1 and analyzing[0][1] == 2
    assert analyzing[1][0] == 2 and analyzing[1][1] == 2
    assert events[0][3] == "scanning"


def test_empty_folder_progress_and_summary(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    events: list[tuple[int, int, str, str]] = []

    result = analyze_folder_for_workbench(
        empty,
        progress_callback=lambda c, t, n, p: events.append((c, t, n, p)),
    )

    assert result.summary == {"files_found": 0, "analyzed_count": 0, "error_count": 0}
    assert events and events[0][3] == "scanning"


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


def test_validate_workbench_folder_rejects_empty():
    result = validate_workbench_folder("   ")

    assert not result.ok
    assert result.error_code == "empty"
    assert result.error_message == "Kein Ordner ausgewählt"
    assert result.normalized_path is None


def test_validate_workbench_folder_rejects_missing(tmp_path: Path):
    missing = tmp_path / "missing_dir"
    result = validate_workbench_folder(str(missing))

    assert not result.ok
    assert result.error_code == "not_found"
    assert result.error_message == "Ordner existiert nicht"


def test_validate_workbench_folder_rejects_file(tmp_path: Path):
    file_path = tmp_path / "not_a_folder.txt"
    file_path.write_text("x", encoding="utf-8")

    result = validate_workbench_folder(str(file_path))

    assert not result.ok
    assert result.error_code == "not_a_directory"
    assert result.error_message == "Pfad ist keine Ordner"


def test_validate_workbench_folder_accepts_valid_directory(tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()

    result = validate_workbench_folder(str(folder))

    assert result.ok
    assert result.error_code is None
    assert result.normalized_path == folder.resolve()


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
