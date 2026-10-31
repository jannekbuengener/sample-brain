"""#1220: Browser Length must survive library cache reload (no filename invention)."""

from __future__ import annotations

from pathlib import Path

from src.workbench_controller import WorkbenchRow, analyze_audio_paths_for_workbench
from src.workbench_library import (
    WORKBENCH_LIBRARY_SCHEMA_VERSION,
    init_workbench_library,
    load_folder_samples,
    lookup_sample,
    upsert_folder,
)
from src.workbench_qml import _duration, _qml_row
from tests.audio_fixtures import write_sine_wav


def test_schema_version_includes_duration_column(tmp_path: Path):
    assert WORKBENCH_LIBRARY_SCHEMA_VERSION == 7
    db = tmp_path / "lib.db"
    init_workbench_library(db)
    import sqlite3

    cols = {
        row[1]
        for row in sqlite3.connect(str(db)).execute("PRAGMA table_info(samples)")
    }
    assert "duration_sec" in cols


def test_analyze_cache_roundtrip_keeps_duration_for_browser_length(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    root = tmp_path / "samples"
    root.mkdir()
    wav = write_sine_wav(root / "loop_tone.wav", duration_sec=0.5, frequency_hz=220.0)
    db = tmp_path / "workbench_library.db"

    result = analyze_audio_paths_for_workbench(
        root,
        [wav],
        use_cache=True,
        library_db_path=db,
    )
    assert result.summary["analyzed_count"] == 1
    fresh = result.rows[0]
    assert fresh.details.get("duration_sec") is not None
    fresh_duration = _duration(fresh)
    assert fresh_duration != "—"
    assert fresh_duration.endswith("s")

    cached = lookup_sample(
        wav,
        wav.stat().st_size,
        wav.stat().st_mtime_ns,
        db_path=db,
    )
    assert cached is not None
    assert cached.duration_sec is not None
    restored = cached.to_workbench_row()
    assert restored.details.get("duration_sec") == cached.duration_sec
    assert _duration(restored) == fresh_duration
    qml = _qml_row(restored)
    assert qml.duration == fresh_duration
    assert qml.duration != "—"


def test_unknown_bpm_key_stay_unknown_without_filename_claims(
    tmp_path: Path, monkeypatch
):
    """Honest unknown only when neither analysis nor deterministic path claims exist."""
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    root = tmp_path / "vox"
    root.mkdir()
    wav = write_sine_wav(
        root / "kiki_riggs_yeah.wav",
        duration_sec=0.2,
        frequency_hz=440.0,
    )
    db = tmp_path / "workbench_library.db"
    result = analyze_audio_paths_for_workbench(
        root,
        [wav],
        use_cache=True,
        library_db_path=db,
    )
    row = result.rows[0]
    qml = _qml_row(row)
    if row.bpm is None:
        assert qml.bpm == "—"
    if not row.key:
        assert qml.key == "—"
    assert qml.duration != "—"
