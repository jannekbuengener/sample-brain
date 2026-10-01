"""Frozen acceptance tests for #768 bidirectional sample file Drag & Drop.

TEST_FREEZE: do not weaken assertions to fit implementation.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import pytest

from tests.audio_fixtures import write_sine_wav


@pytest.fixture(autouse=True)
def _isolated_workbench_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = tmp_path / "workbench_state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))


@pytest.fixture
def library_db(tmp_path: Path) -> Path:
    return tmp_path / "workbench_library.db"


@pytest.fixture
def registered_source(tmp_path: Path, library_db: Path) -> Path:
    from src.workbench_library import upsert_folder

    root = tmp_path / "registered_source"
    root.mkdir()
    sub = root / "drums"
    sub.mkdir()
    upsert_folder(root, db_path=library_db)
    return root


def _folder_id(root: Path, library_db: Path) -> int:
    from src.workbench_library import list_library_folders

    folders = list_library_folders(db_path=library_db)
    resolved = str(root.resolve())
    for folder in folders:
        if str(Path(folder.path).resolve()) == resolved:
            return int(folder.id)
    raise AssertionError("registered source missing")


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_01_valid_single_file_inbound_copy(tmp_path: Path, library_db: Path, registered_source: Path):
    from src.workbench_sample_dnd import import_dropped_files

    external = tmp_path / "external"
    external.mkdir()
    src = write_sine_wav(external / "kick.wav", duration_sec=0.25, frequency_hz=80.0)
    folder_id = _folder_id(registered_source, library_db)
    node_id = f"root:{folder_id}"

    result = import_dropped_files(
        [src.as_uri()],
        destination_node_id=node_id,
        library_db_path=library_db,
    )

    assert result.error_code is None
    assert len(result.imported) == 1
    dest = result.imported[0].destination_path
    assert dest is not None
    assert dest.parent == registered_source.resolve()
    assert dest.is_file()
    assert dest.name == "kick.wav"


def test_02_original_external_unchanged(tmp_path: Path, library_db: Path, registered_source: Path):
    from src.workbench_sample_dnd import import_dropped_files

    external = tmp_path / "external"
    external.mkdir()
    src = write_sine_wav(external / "snare.wav", duration_sec=0.2, frequency_hz=200.0)
    before = _file_digest(src)
    folder_id = _folder_id(registered_source, library_db)

    import_dropped_files(
        [src.as_uri()],
        destination_node_id=f"root:{folder_id}",
        library_db_path=library_db,
    )

    assert src.is_file()
    assert _file_digest(src) == before


def test_03_correct_destination_subfolder(tmp_path: Path, library_db: Path, registered_source: Path):
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_sample_dnd import import_dropped_files

    external = tmp_path / "external"
    external.mkdir()
    src = write_sine_wav(external / "hat.wav", duration_sec=0.15, frequency_hz=400.0)
    folder_id = _folder_id(registered_source, library_db)
    nav = WorkbenchLibraryNavigation(library_db_path=library_db)
    children = nav.children(f"root:{folder_id}")
    drums = next(node for node in children if node.label == "drums")

    result = import_dropped_files(
        [src.as_uri()],
        destination_node_id=drums.node_id,
        library_db_path=library_db,
    )

    assert len(result.imported) == 1
    dest = result.imported[0].destination_path
    assert dest is not None
    assert dest.parent == (registered_source / "drums").resolve()


def test_04_collision_without_overwrite(tmp_path: Path, library_db: Path, registered_source: Path):
    from src.workbench_sample_dnd import import_dropped_files

    existing = write_sine_wav(
        registered_source / "kick.wav", duration_sec=0.3, frequency_hz=60.0
    )
    existing_digest = _file_digest(existing)
    external = tmp_path / "external"
    external.mkdir()
    src = write_sine_wav(external / "kick.wav", duration_sec=0.1, frequency_hz=120.0)
    folder_id = _folder_id(registered_source, library_db)

    result = import_dropped_files(
        [src.as_uri()],
        destination_node_id=f"root:{folder_id}",
        library_db_path=library_db,
    )

    assert len(result.imported) == 0
    assert len(result.skipped_conflict) == 1
    assert _file_digest(existing) == existing_digest
    assert existing.read_bytes() != src.read_bytes()


def test_05_invalid_synthetic_destination_rejected(tmp_path: Path, library_db: Path, registered_source: Path):
    from src.workbench_sample_dnd import import_dropped_files

    _ = registered_source
    external = tmp_path / "external"
    external.mkdir()
    src = write_sine_wav(external / "x.wav", duration_sec=0.1, frequency_hz=100.0)

    for node_id in (
        "scope:all-library",
        "scope:catalog-readonly",
        "scope:favorites",
        "container:collections",
        "container:sample-sources",
        "status:error:abc",
        "not-a-real-node",
    ):
        result = import_dropped_files(
            [src.as_uri()],
            destination_node_id=node_id,
            library_db_path=library_db,
        )
        assert result.imported == ()
        assert result.error_code == "invalid_destination"
        assert result.destination is None


def test_06_offline_unavailable_destination(tmp_path: Path, library_db: Path):
    from src.workbench_library import upsert_folder
    from src.workbench_sample_dnd import import_dropped_files

    missing = tmp_path / "gone_source"
    missing.mkdir()
    folder_id = upsert_folder(missing, db_path=library_db)
    shutil.rmtree(missing)
    external = tmp_path / "external"
    external.mkdir()
    src = write_sine_wav(external / "y.wav", duration_sec=0.1, frequency_hz=90.0)

    result = import_dropped_files(
        [src.as_uri()],
        destination_node_id=f"root:{folder_id}",
        library_db_path=library_db,
    )

    assert result.imported == ()
    assert result.error_code in {"destination_offline", "invalid_destination"}


def test_07_multi_file_partial_success(tmp_path: Path, library_db: Path, registered_source: Path):
    from src.workbench_sample_dnd import import_dropped_files

    write_sine_wav(registered_source / "keep.wav", duration_sec=0.2, frequency_hz=70.0)
    external = tmp_path / "external"
    external.mkdir()
    ok = write_sine_wav(external / "new.wav", duration_sec=0.2, frequency_hz=75.0)
    conflict = write_sine_wav(external / "keep.wav", duration_sec=0.1, frequency_hz=50.0)
    bad = external / "notes.txt"
    bad.write_text("not audio", encoding="utf-8")
    folder_id = _folder_id(registered_source, library_db)

    result = import_dropped_files(
        [ok.as_uri(), conflict.as_uri(), bad.as_uri()],
        destination_node_id=f"root:{folder_id}",
        library_db_path=library_db,
    )

    assert len(result.imported) == 1
    assert result.imported[0].destination_path is not None
    assert result.imported[0].destination_path.name == "new.wav"
    assert len(result.skipped_conflict) == 1
    assert len(result.failed) == 1
    assert (registered_source / "new.wav").is_file()


def test_08_unsupported_unreadable_isolation(tmp_path: Path, library_db: Path, registered_source: Path):
    from src.workbench_sample_dnd import import_dropped_files

    external = tmp_path / "external"
    external.mkdir()
    good = write_sine_wav(external / "good.wav", duration_sec=0.2, frequency_hz=110.0)
    junk = external / "junk.bin"
    junk.write_bytes(b"\x00\x01\x02not-audio")
    folder_id = _folder_id(registered_source, library_db)

    result = import_dropped_files(
        [junk.as_uri(), good.as_uri()],
        destination_node_id=f"root:{folder_id}",
        library_db_path=library_db,
    )

    assert len(result.imported) == 1
    assert len(result.failed) == 1
    assert (registered_source / "good.wav").is_file()


def test_09_path_traversal_rejection(tmp_path: Path, library_db: Path, registered_source: Path):
    from src.workbench_sample_dnd import resolve_drop_destination

    folder_id = _folder_id(registered_source, library_db)
    # Synthetic encoded relative path attempting escape must fail closed.
    evil = f"folder:{folder_id}:Li4vLi4vZXNjYXBl"  # base64url of ../escape without padding rules
    resolved = resolve_drop_destination(evil, library_db_path=library_db)
    assert resolved.ok is False
    assert resolved.error_code == "invalid_destination"


def test_10_symlink_junction_escape_as_platform_allows(
    tmp_path: Path, library_db: Path, registered_source: Path
):
    from src.workbench_sample_dnd import import_dropped_files, resolve_drop_destination

    outside = tmp_path / "outside_escape"
    outside.mkdir()
    link = registered_source / "escape_link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        pytest.skip("symlink/junction creation not permitted on this platform/user")

    folder_id = _folder_id(registered_source, library_db)
    from src.workbench_library_navigation import WorkbenchLibraryNavigation

    nav = WorkbenchLibraryNavigation(library_db_path=library_db)
    # Navigation itself skips link children; crafted node must still fail.
    children = nav.children(f"root:{folder_id}")
    assert all(node.label != "escape_link" for node in children)

    crafted = resolve_drop_destination(
        f"folder:{folder_id}:ZXNjYXBlX2xpbms",
        library_db_path=library_db,
    )
    assert crafted.ok is False

    external = tmp_path / "external"
    external.mkdir()
    src = write_sine_wav(external / "z.wav", duration_sec=0.1, frequency_hz=88.0)
    # Even if somehow destination resolved to link path, copy must fail closed.
    from src.workbench_sample_dnd import DropDestination, copy_files_into_destination

    unsafe = DropDestination(
        folder_id=folder_id,
        source_root=registered_source.resolve(),
        destination_dir=link.resolve(),
        node_id="crafted",
        relative_path="escape_link",
    )
    copy_result = copy_files_into_destination([src], unsafe)
    assert copy_result.imported == ()
    assert copy_result.error_code in {"path_escape", "invalid_destination"}


def test_11_targeted_analysis_only_for_imported_files(
    tmp_path: Path, library_db: Path, registered_source: Path, monkeypatch: pytest.MonkeyPatch
):
    from src import workbench_controller as controller
    from src.workbench_sample_dnd import import_and_analyze_dropped_files

    write_sine_wav(registered_source / "existing.wav", duration_sec=0.25, frequency_hz=55.0)
    controller.analyze_folder_for_workbench(
        registered_source, library_db_path=library_db
    )

    external = tmp_path / "external"
    external.mkdir()
    src = write_sine_wav(external / "fresh.wav", duration_sec=0.25, frequency_hz=66.0)
    folder_id = _folder_id(registered_source, library_db)

    analyzed: list[tuple[Path, tuple[Path, ...]]] = []
    real = controller.analyze_audio_paths_for_workbench

    def spy(root, audio_paths, **kwargs):
        analyzed.append((Path(root), tuple(Path(p) for p in audio_paths)))
        return real(root, audio_paths, **kwargs)

    monkeypatch.setattr(controller, "analyze_audio_paths_for_workbench", spy)
    monkeypatch.setattr(
        "src.workbench_sample_dnd.analyze_audio_paths_for_workbench",
        spy,
    )

    folder_calls: list[Path] = []

    def forbid_folder(folder, *args, **kwargs):
        folder_calls.append(Path(folder))
        raise AssertionError("full-folder analyze must not run for inbound DnD")

    monkeypatch.setattr(controller, "analyze_folder_for_workbench", forbid_folder)
    monkeypatch.setattr(
        "src.workbench_sample_dnd.analyze_folder_for_workbench",
        forbid_folder,
        raising=False,
    )

    result = import_and_analyze_dropped_files(
        [src.as_uri()],
        destination_node_id=f"root:{folder_id}",
        library_db_path=library_db,
    )

    assert result.import_result.imported
    assert folder_calls == []
    assert len(analyzed) == 1
    assert len(analyzed[0][1]) == 1
    assert analyzed[0][1][0].name == "fresh.wav"


def test_12_no_full_library_analyze(
    tmp_path: Path, library_db: Path, registered_source: Path, monkeypatch: pytest.MonkeyPatch
):
    from src.workbench_sample_dnd import import_and_analyze_dropped_files

    external = tmp_path / "external"
    external.mkdir()
    src = write_sine_wav(external / "one.wav", duration_sec=0.2, frequency_hz=77.0)
    folder_id = _folder_id(registered_source, library_db)

    def forbid(*_a, **_k):
        raise AssertionError("analyze_folder_for_workbench must not be used")

    monkeypatch.setattr(
        "src.workbench_sample_dnd.analyze_folder_for_workbench",
        forbid,
        raising=False,
    )
    monkeypatch.setattr(
        "src.workbench_controller.analyze_folder_for_workbench",
        forbid,
    )

    result = import_and_analyze_dropped_files(
        [src.as_uri()],
        destination_node_id=f"root:{folder_id}",
        library_db_path=library_db,
    )
    assert len(result.import_result.imported) == 1
    assert result.analysis is not None
    assert result.analysis.summary["files_found"] == 1


def test_13_targeted_vs_canonical_analyzer_equivalence(
    tmp_path: Path, library_db: Path, registered_source: Path
):
    from src.workbench_controller import (
        analyze_audio_paths_for_workbench,
        analyze_folder_for_workbench,
    )
    from src.workbench_library import lookup_sample

    audio = write_sine_wav(
        registered_source / "eq.wav", duration_sec=0.35, frequency_hz=220.0
    )
    folder = analyze_folder_for_workbench(registered_source, library_db_path=library_db)
    folder_row = next(r for r in folder.rows if Path(r.path).name == "eq.wav")

    # Clear cache entry by re-analyzing path with use_cache False equivalence path
    targeted = analyze_audio_paths_for_workbench(
        registered_source,
        [audio],
        library_db_path=library_db,
        use_cache=False,
    )
    target_row = targeted.rows[0]

    assert target_row.status == folder_row.status
    assert target_row.bpm == folder_row.bpm
    assert target_row.key == folder_row.key
    assert target_row.pred_type == folder_row.pred_type
    assert target_row.sample_class == folder_row.sample_class
    assert abs((target_row.loudness or 0) - (folder_row.loudness or 0)) < 1e-6
    assert abs((target_row.brightness or 0) - (folder_row.brightness or 0)) < 1e-3

    st = audio.stat()
    cached = lookup_sample(audio.resolve(), st.st_size, st.st_mtime_ns, db_path=library_db)
    assert cached is not None
    assert cached.analyzer_version == folder_row.details.get("analyzer_version")


def test_14_browser_refresh_flag(tmp_path: Path, library_db: Path, registered_source: Path):
    from src.workbench_sample_dnd import import_and_analyze_dropped_files

    external = tmp_path / "external"
    external.mkdir()
    src = write_sine_wav(external / "refresh_me.wav", duration_sec=0.2, frequency_hz=99.0)
    folder_id = _folder_id(registered_source, library_db)

    result = import_and_analyze_dropped_files(
        [src.as_uri()],
        destination_node_id=f"root:{folder_id}",
        library_db_path=library_db,
    )

    assert result.should_refresh_browser is True
    assert result.should_auto_audition is False


def test_15_no_auto_audition(tmp_path: Path, library_db: Path, registered_source: Path):
    from src.workbench_sample_dnd import ImportAnalyzeResult, import_and_analyze_dropped_files

    external = tmp_path / "external"
    external.mkdir()
    src = write_sine_wav(external / "quiet.wav", duration_sec=0.2, frequency_hz=40.0)
    folder_id = _folder_id(registered_source, library_db)
    result = import_and_analyze_dropped_files(
        [src.as_uri()],
        destination_node_id=f"root:{folder_id}",
        library_db_path=library_db,
    )
    assert isinstance(result, ImportAnalyzeResult)
    assert result.should_auto_audition is False


def test_16_outbound_local_file_url(tmp_path: Path):
    from src.workbench_sample_dnd import outbound_local_file_url

    audio = write_sine_wav(tmp_path / "out.wav", duration_sec=0.15, frequency_hz=150.0)
    url = outbound_local_file_url(audio)
    assert url is not None
    assert url.startswith("file:")
    assert Path(audio).resolve().as_uri() == url


def test_17_outbound_source_unchanged(tmp_path: Path):
    from src.workbench_sample_dnd import outbound_local_file_url

    audio = write_sine_wav(tmp_path / "stable.wav", duration_sec=0.15, frequency_hz=160.0)
    before = _file_digest(audio)
    mtime = audio.stat().st_mtime_ns
    url = outbound_local_file_url(audio)
    assert url is not None
    assert _file_digest(audio) == before
    assert audio.stat().st_mtime_ns == mtime


def test_18_dnd_must_not_damage_selection_audition_contracts():
    from src.workbench_qml import QML_SOURCE
    from src.workbench_sample_dnd import outbound_local_file_url

    # Outbound drag must expose standard uri-list MIME, not proprietary DAW MIME.
    assert "text/uri-list" in QML_SOURCE
    assert "Drag.mimeData" in QML_SOURCE or "Drag.keys" in QML_SOURCE
    # Drop targets must be Library-scoped, not Browser synthetic scopes.
    assert "DropArea" in QML_SOURCE
    assert "importDroppedFiles" in QML_SOURCE or "importDroppedUrls" in QML_SOURCE
    # Selection/audition remain via existing Python slots; drag must not invent audition.
    assert "selectRow" in QML_SOURCE
    assert "previewRow" in QML_SOURCE
    # Outbound helper is path-only and does not mutate selection state.
    assert callable(outbound_local_file_url)


def test_qml_boundary_no_fs_mutation_authority():
    from src.workbench_qml import QML_SOURCE

    # QML may call typed intents only; must not embed shutil/copy/analyze authority.
    assert "shutil" not in QML_SOURCE
    assert "analyze_folder_for_workbench" not in QML_SOURCE
    assert "copy2" not in QML_SOURCE


def test_outbound_missing_file_fail_soft(tmp_path: Path):
    from src.workbench_sample_dnd import outbound_local_file_url

    missing = tmp_path / "missing.wav"
    assert outbound_local_file_url(missing) is None
