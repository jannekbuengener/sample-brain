"""#1220/#1203: Browser consumes deterministic path-claim resolutions.

When analysis abstains but an explicit filename claim exists, Browser must show
the DECLARED_ONLY resolved consumer value — not invent free-text, and not stay
blank when the claim contract already resolved a value.
"""

from __future__ import annotations

from pathlib import Path

from src.path_metadata import STATUS_DECLARED_ONLY, STATUS_UNKNOWN
from src.workbench_controller import analyze_audio_paths_for_workbench
from src.workbench_library import WORKBENCH_ANALYZER_VERSION, lookup_sample
from src.workbench_qml import _qml_row
from tests.audio_fixtures import write_sine_wav


def test_declared_only_filename_bpm_and_key_reach_browser(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    root = tmp_path / "samples"
    root.mkdir()
    # Short tone: analyzer typically abstains on BPM/Key; filename carries explicit claims.
    wav = write_sine_wav(
        root / "loop_150bpm_Cmin.wav",
        duration_sec=0.25,
        frequency_hz=220.0,
    )
    db = tmp_path / "workbench_library.db"
    result = analyze_audio_paths_for_workbench(
        root, [wav], use_cache=True, library_db_path=db
    )
    row = result.rows[0]
    assert row.status == "ok"
    assert row.details.get("analyzer_version") == WORKBENCH_ANALYZER_VERSION
    assert row.details.get("bpm_resolution_status") == STATUS_DECLARED_ONLY
    assert row.details.get("key_resolution_status") == STATUS_DECLARED_ONLY
    assert row.bpm == 150.0
    assert row.key == "Cmin"
    assert row.details.get("analysis_bpm") in (None, "")
    assert row.details.get("analysis_key") in (None, "")
    qml = _qml_row(row)
    assert qml.bpm == "150"
    assert qml.key == "Cmin"
    assert qml.duration != "—"

    cached = lookup_sample(
        wav, wav.stat().st_size, wav.stat().st_mtime_ns, db_path=db
    )
    assert cached is not None
    restored = cached.to_workbench_row()
    assert restored.bpm == 150.0
    assert restored.key == "Cmin"
    assert _qml_row(restored).bpm == "150"


def test_plain_filename_without_claims_stays_honest_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    root = tmp_path / "samples"
    root.mkdir()
    wav = write_sine_wav(
        root / "kiki_riggs_yeah.wav",
        duration_sec=0.2,
        frequency_hz=440.0,
    )
    db = tmp_path / "workbench_library.db"
    result = analyze_audio_paths_for_workbench(
        root, [wav], use_cache=True, library_db_path=db
    )
    row = result.rows[0]
    qml = _qml_row(row)
    if row.bpm is None:
        assert row.details.get("bpm_resolution_status") == STATUS_UNKNOWN
        assert qml.bpm == "—"
    if not row.key:
        assert row.details.get("key_resolution_status") == STATUS_UNKNOWN
        assert qml.key == "—"
    assert qml.duration != "—"
