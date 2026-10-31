"""#1220: poisoned prior-version error cache rows must miss and re-analyze."""

from __future__ import annotations

from pathlib import Path

from src.workbench_controller import (
    WorkbenchRow,
    analyze_folder_for_workbench,
    workbench_scope_requires_refresh,
)
from src.workbench_library import (
    WORKBENCH_ANALYZER_VERSION,
    lookup_sample,
    upsert_folder,
    upsert_sample,
)
from src.workbench_qml import _qml_row
from tests.audio_fixtures import write_sine_wav

PRIOR_POISONED_ANALYZER_VERSION = "workbench_v4"


def test_prior_version_sticky_error_is_refreshed_with_duration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    root.mkdir()
    db = tmp_path / "workbench_library.db"
    audio = write_sine_wav(root / "loop_tone.wav", duration_sec=0.5, frequency_hz=220.0)
    st = audio.stat()
    folder_id = upsert_folder(root, db_path=db)
    poisoned = WorkbenchRow(
        display_name=audio.stem,
        relative_path=audio.name,
        path=str(audio.resolve()),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=None,
        pred_type=None,
        status="error",
        error="analysis failed",
        error_code="analysis_exception",
        details={
            "path": str(audio.resolve()),
            "error_code": "analysis_exception",
            "error_detail": "No module named 'scipy._external.array_api_compat.numpy.fft'",
            "analyzer_version": PRIOR_POISONED_ANALYZER_VERSION,
        },
    )
    upsert_sample(
        folder_id,
        poisoned,
        size_bytes=st.st_size,
        mtime_ns=st.st_mtime_ns,
        db_path=db,
        analyzer_version=PRIOR_POISONED_ANALYZER_VERSION,
    )
    assert PRIOR_POISONED_ANALYZER_VERSION != WORKBENCH_ANALYZER_VERSION
    assert workbench_scope_requires_refresh(
        folder_id=None, folder_path=root, library_db_path=db
    )

    result = analyze_folder_for_workbench(root, use_cache=True, library_db_path=db)
    assert result.summary["cache_misses"] == 1
    assert result.summary["cache_hits"] == 0
    healed = result.rows[0]
    assert healed.status == "ok"
    assert healed.details.get("analyzer_version") == WORKBENCH_ANALYZER_VERSION
    assert healed.details.get("duration_sec") is not None
    assert _qml_row(healed).duration != "—"

    cached = lookup_sample(audio, st.st_size, st.st_mtime_ns, db_path=db)
    assert cached is not None
    assert cached.analyzer_version == WORKBENCH_ANALYZER_VERSION
    assert cached.status == "ok"
    assert cached.duration_sec is not None
