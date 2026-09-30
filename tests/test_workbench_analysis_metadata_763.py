"""#763 analysis metadata persistence / projection / cache-heal contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.workbench_controller import (
    WorkbenchRow,
    analyze_folder_for_workbench,
    load_cached_folder_rows,
    workbench_scope_requires_refresh,
)
from src.workbench_harmony import HarmonicMatchLibraryController
from src.workbench_library import (
    WORKBENCH_ANALYZER_VERSION,
    connect_workbench_library,
    lookup_sample,
    upsert_folder,
    upsert_sample,
)
from src.workbench_qml import _qml_row
from src.workbench_qml_library import LibrarySelectionIntent, WorkbenchLibraryTreeState
from src.workbench_library_navigation import (
    LibraryNodeKind,
    WorkbenchLibraryNavigation,
)
from src.workbench_qml_runtime import Screen1QmlRuntimeComposition
from tests.audio_fixtures import (
    write_kick_transient_wav,
    write_major_chord_wav,
    write_pulse_train_wav,
    write_sine_wav,
)


PRIOR_HOLLOW_ANALYZER_VERSION = "workbench_v2"


def _seed_hollow_ok_row(
    root: Path,
    audio: Path,
    *,
    db_path: Path,
    analyzer_version: str = PRIOR_HOLLOW_ANALYZER_VERSION,
) -> None:
    """Persist a degraded historical ok-row: loudness/class present, BPM/Key/brightness absent."""
    st = audio.stat()
    folder_id = upsert_folder(root, db_path=db_path)
    row = WorkbenchRow(
        display_name=audio.stem,
        relative_path=audio.name,
        path=str(audio.resolve()),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=-18.0,
        brightness=None,
        sample_class="loop",
        pred_type="Loop",
        status="ok",
        details={"path": str(audio.resolve())},
    )
    upsert_sample(
        folder_id,
        row,
        size_bytes=st.st_size,
        mtime_ns=st.st_mtime_ns,
        db_path=db_path,
        analyzer_version=analyzer_version,
    )


def test_case1_analyze_persist_reload_metadata_equivalence(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    db = tmp_path / "workbench_library.db"
    write_pulse_train_wav(root / "pulse.wav", bpm=120.0, duration_sec=6.0)

    result = analyze_folder_for_workbench(root, use_cache=True, library_db_path=db)
    assert result.summary["analyzed_count"] == 1
    assert result.summary["error_count"] == 0
    produced = result.rows[0]
    assert produced.status == "ok"
    assert produced.bpm is not None and produced.bpm > 0
    assert produced.details.get("analyzer_version") == WORKBENCH_ANALYZER_VERSION

    reloaded = load_cached_folder_rows(root, library_db_path=db)
    assert len(reloaded) == 1
    cached = reloaded[0]
    assert cached.bpm == produced.bpm
    assert cached.key == produced.key
    assert cached.key_conf == produced.key_conf
    assert cached.status == produced.status
    assert cached.details.get("analyzer_version") == WORKBENCH_ANALYZER_VERSION
    assert cached.pred_type == produced.pred_type
    assert cached.sample_class == produced.sample_class

    qml = _qml_row(cached)
    assert qml.bpm != "—"
    assert produced.key is None or qml.key != "—"


def test_case2_runtime_completion_projects_analyzed_bpm_key(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    db = tmp_path / "workbench_library.db"
    write_pulse_train_wav(root / "pulse.wav", bpm=120.0, duration_sec=6.0)
    write_major_chord_wav(root / "chord.wav", duration_sec=3.0)

    analyze_folder_for_workbench(root, use_cache=True, library_db_path=db)

    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    root_node = next(
        node
        for node in navigation.children("container:sample-sources")
        if node.kind is LibraryNodeKind.REGISTERED_ROOT
    )
    scope = navigation.resolve_scope(root_node.node_id)
    state = composition.dispatch_selection(
        LibrarySelectionIntent(node=root_node, scope=scope)
    )
    qml_rows = [_qml_row(row) for row in state.rows]
    assert any(row.bpm != "—" for row in qml_rows)
    assert any(row.key != "—" for row in qml_rows)
    assert composition.library_db_path.resolve() == db.resolve()


def test_case3_restart_reuses_cache_and_preserves_metadata(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    db = tmp_path / "workbench_library.db"
    write_kick_transient_wav(root / "kick.wav", bpm=120.0, duration_sec=6.0)

    first = analyze_folder_for_workbench(root, use_cache=True, library_db_path=db)
    assert first.summary["cache_misses"] >= 1
    assert first.rows[0].bpm is not None

    second = analyze_folder_for_workbench(root, use_cache=True, library_db_path=db)
    assert second.summary["cache_hits"] >= 1
    assert second.summary["cache_misses"] == 0
    assert second.rows[0].bpm == first.rows[0].bpm
    assert second.rows[0].key == first.rows[0].key
    assert _qml_row(second.rows[0]).bpm != "—"


def test_case4_error_and_no_result_stay_truthful(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    db = tmp_path / "workbench_library.db"
    # Very short sine: analyzer may omit BPM/Key; must not fabricate values.
    write_sine_wav(root / "blip.wav", duration_sec=0.05, frequency_hz=440.0)
    (root / "broken.wav").write_bytes(b"not-a-wav")

    result = analyze_folder_for_workbench(root, use_cache=True, library_db_path=db)
    by_name = {row.display_name: row for row in result.rows}
    assert "broken" in by_name
    assert by_name["broken"].status == "error"
    assert by_name["broken"].bpm is None
    assert by_name["broken"].key is None

    blip = by_name["blip"]
    assert blip.bpm is None
    assert _qml_row(blip).bpm == "—"

    with connect_workbench_library(db) as conn:
        broken = conn.execute(
            "SELECT bpm, key, status FROM samples WHERE display_name = ?",
            ("broken",),
        ).fetchone()
    assert broken["status"] == "error"
    assert broken["bpm"] is None
    assert broken["key"] is None


def test_case5_harmony_receives_real_analyzed_row(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    db = tmp_path / "workbench_library.db"
    write_pulse_train_wav(root / "pulse.wav", bpm=120.0, duration_sec=6.0)
    write_major_chord_wav(root / "chord.wav", duration_sec=3.0)
    result = analyze_folder_for_workbench(root, use_cache=True, library_db_path=db)
    rows = load_cached_folder_rows(root, library_db_path=db)
    anchor = next(row for row in rows if row.bpm is not None and row.bpm > 0)
    controller = HarmonicMatchLibraryController()
    controller.set_anchor(anchor, tuple(rows))
    assert controller.anchor is not None
    assert controller.anchor.bpm == anchor.bpm
    assert controller.anchor.bpm is not None and controller.anchor.bpm > 0
    if anchor.key:
        assert controller.anchor.key == anchor.key
    assert result.summary["analyzed_count"] >= 1


def test_hollow_prior_version_cache_row_is_reanalyzed_and_healed(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    db = tmp_path / "workbench_library.db"
    audio = write_pulse_train_wav(root / "pulse.wav", bpm=120.0, duration_sec=6.0)
    _seed_hollow_ok_row(root, audio, db_path=db)

    assert PRIOR_HOLLOW_ANALYZER_VERSION != WORKBENCH_ANALYZER_VERSION
    assert workbench_scope_requires_refresh(
        folder_id=None,
        folder_path=root,
        library_db_path=db,
    )

    result = analyze_folder_for_workbench(root, use_cache=True, library_db_path=db)
    assert result.summary["cache_misses"] == 1
    assert result.summary["cache_hits"] == 0
    healed = result.rows[0]
    assert healed.status == "ok"
    assert healed.bpm is not None and healed.bpm > 0
    assert healed.brightness is not None
    assert healed.details.get("analyzer_version") == WORKBENCH_ANALYZER_VERSION

    st = audio.stat()
    cached = lookup_sample(
        audio, st.st_size, st.st_mtime_ns, db_path=db
    )
    assert cached is not None
    assert cached.analyzer_version == WORKBENCH_ANALYZER_VERSION
    assert cached.bpm is not None
    assert cached.brightness is not None
    assert _qml_row(cached.to_workbench_row()).bpm != "—"
