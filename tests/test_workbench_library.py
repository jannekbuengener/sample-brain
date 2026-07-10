from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.workbench_library import (
    WORKBENCH_ANALYZER_VERSION,
    WORKBENCH_LIBRARY_SCHEMA_VERSION,
    WorkbenchCueMetadata,
    WorkbenchCueNotFoundError,
    WorkbenchCueValidationError,
    WorkbenchPlaylistValidationError,
    add_sample_to_playlist,
    connect_workbench_library,
    create_playlist,
    default_workbench_cue_metadata,
    get_or_create_playlist,
    init_workbench_library,
    list_library_folders,
    list_playlists,
    load_folder_samples,
    load_all_cached_samples,
    load_sample_cue,
    lookup_sample,
    normalize_display_name,
    normalize_playlist_name,
    register_library_folder,
    remove_library_folder,
    save_sample_cue,
    upsert_folder,
    upsert_sample,
    validate_workbench_cue_metadata,
    workbench_library_db_path,
)
from src.workbench_controller import WorkbenchRow


@pytest.fixture
def library_state(tmp_path: Path) -> Path:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def library_db(library_state: Path) -> Path:
    db_path = workbench_library_db_path(state_dir=library_state)
    init_workbench_library(db_path)
    return db_path


def test_workbench_library_db_path_uses_state_dir(library_state: Path):
    db_path = workbench_library_db_path(state_dir=library_state)
    assert db_path == library_state / "workbench_library.db"


def test_init_workbench_library_creates_schema(library_db: Path):
    assert library_db.is_file()


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("kick_808_FINAL.wav", "kick 808 FINAL"),
        ("dark-pad-loop-120bpm.wav", "dark pad loop 120bpm"),
        ("  snare__wet.wav  ", "snare wet"),
    ],
)
def test_normalize_display_name(filename: str, expected: str):
    assert normalize_display_name(filename) == expected


def test_upsert_folder_is_idempotent(library_db: Path, tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()

    first = upsert_folder(folder, db_path=library_db)
    second = upsert_folder(folder, db_path=library_db)

    assert first == second


def test_upsert_sample_lookup_roundtrip(library_db: Path, tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()
    audio = folder / "tone_a.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 40)

    folder_id = upsert_folder(folder, db_path=library_db)
    row = WorkbenchRow(
        display_name="tone a",
        relative_path="tone_a.wav",
        path=str(audio.resolve()),
        bpm=120.0,
        key="C",
        key_conf=0.8,
        loudness=-12.0,
        brightness=1500.0,
        sample_class="oneshot",
        pred_type="Kick",
        status="ok",
        details={"tags": ["Kick"]},
    )
    size_bytes = 44
    mtime_ns = 1_700_000_000_000_000_000

    upsert_sample(
        folder_id,
        row,
        size_bytes=size_bytes,
        mtime_ns=mtime_ns,
        db_path=library_db,
        analyzer_version=WORKBENCH_ANALYZER_VERSION,
    )

    cached = lookup_sample(audio.resolve(), size_bytes, mtime_ns, db_path=library_db)
    assert cached is not None
    assert cached.display_name == "tone a"
    assert cached.bpm == 120.0
    assert cached.pred_type == "Kick"
    assert cached.tags == ["Kick"]


def test_lookup_sample_cache_hit_and_miss_on_mtime(library_db: Path, tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()
    audio = folder / "kick.wav"
    audio.write_bytes(b"data")

    folder_id = upsert_folder(folder, db_path=library_db)
    row = WorkbenchRow(
        display_name="kick",
        relative_path="kick.wav",
        path=str(audio.resolve()),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=None,
        pred_type=None,
        status="ok",
    )
    upsert_sample(folder_id, row, size_bytes=4, mtime_ns=100, db_path=library_db)

    assert lookup_sample(audio.resolve(), 4, 100, db_path=library_db) is not None
    assert lookup_sample(audio.resolve(), 4, 200, db_path=library_db) is None


def test_lookup_sample_cache_miss_on_size(library_db: Path, tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()
    audio = folder / "kick.wav"
    audio.write_bytes(b"data")

    folder_id = upsert_folder(folder, db_path=library_db)
    row = WorkbenchRow(
        display_name="kick",
        relative_path="kick.wav",
        path=str(audio.resolve()),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=None,
        pred_type=None,
        status="ok",
    )
    upsert_sample(folder_id, row, size_bytes=4, mtime_ns=100, db_path=library_db)

    assert lookup_sample(audio.resolve(), 99, 100, db_path=library_db) is None


def test_list_library_folders_returns_registered_folders(library_db: Path, tmp_path: Path):
    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    alpha.mkdir()
    beta.mkdir()

    register_library_folder(alpha, db_path=library_db)
    register_library_folder(beta, db_path=library_db)

    folders = list_library_folders(db_path=library_db)
    paths = {folder.path for folder in folders}
    assert paths == {str(alpha.resolve()), str(beta.resolve())}
    assert all(folder.id > 0 for folder in folders)


def test_list_library_folders_orders_by_last_opened(library_db: Path, tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    register_library_folder(first, db_path=library_db)
    register_library_folder(second, db_path=library_db)
    register_library_folder(first, db_path=library_db)

    folders = list_library_folders(db_path=library_db)
    assert folders[0].path == str(first.resolve())


def test_remove_library_folder_deletes_folder_and_samples(library_db: Path, tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()
    audio = folder / "kick.wav"
    audio.write_bytes(b"data")

    folder_id = upsert_folder(folder, db_path=library_db)
    row = WorkbenchRow(
        display_name="kick",
        relative_path="kick.wav",
        path=str(audio.resolve()),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=None,
        pred_type=None,
        status="ok",
    )
    upsert_sample(folder_id, row, size_bytes=4, mtime_ns=100, db_path=library_db)

    assert remove_library_folder(folder_id, db_path=library_db)
    assert list_library_folders(db_path=library_db) == []
    assert load_folder_samples(folder, db_path=library_db) == []
    assert audio.is_file()


def test_remove_library_folder_by_path(library_db: Path, tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()
    upsert_folder(folder, db_path=library_db)

    assert remove_library_folder(str(folder.resolve()), db_path=library_db)
    assert list_library_folders(db_path=library_db) == []


def test_remove_library_folder_is_idempotent(library_db: Path, tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()
    folder_id = upsert_folder(folder, db_path=library_db)

    assert remove_library_folder(folder_id, db_path=library_db)
    assert not remove_library_folder(folder_id, db_path=library_db)
    assert not remove_library_folder(str(folder.resolve()), db_path=library_db)


def test_register_library_folder_without_scan_timestamp(library_db: Path, tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()

    register_library_folder(folder, db_path=library_db)
    folders = list_library_folders(db_path=library_db)

    assert len(folders) == 1
    assert folders[0].last_opened_at is not None
    assert folders[0].last_scan_at is None


def _sample_columns(db_path: Path) -> set[str]:
    with connect_workbench_library(db_path) as conn:
        rows = conn.execute("PRAGMA table_info(samples)").fetchall()
    return {str(row[1]) for row in rows}


def _create_legacy_v1_library_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE folders (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            last_scan_at TEXT,
            last_opened_at TEXT
        );
        CREATE TABLE samples (
            id INTEGER PRIMARY KEY,
            folder_id INTEGER NOT NULL,
            original_path TEXT UNIQUE NOT NULL,
            relative_path TEXT,
            size_bytes INTEGER,
            mtime_ns INTEGER,
            display_name TEXT,
            bpm REAL,
            key TEXT,
            key_conf REAL,
            loudness REAL,
            brightness REAL,
            sample_class TEXT,
            pred_type TEXT,
            status TEXT,
            error_code TEXT,
            quality_note TEXT,
            tags TEXT,
            analyzed_at TEXT,
            analyzer_version TEXT,
            FOREIGN KEY(folder_id) REFERENCES folders(id)
        );
        """
    )
    conn.commit()
    conn.close()


def _create_legacy_v2_library_db(db_path: Path) -> None:
    """Schema v2: cue columns present, no loop_source/attack_source."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE folders (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            last_scan_at TEXT,
            last_opened_at TEXT
        );
        CREATE TABLE samples (
            id INTEGER PRIMARY KEY,
            folder_id INTEGER NOT NULL,
            original_path TEXT UNIQUE NOT NULL,
            relative_path TEXT,
            size_bytes INTEGER,
            mtime_ns INTEGER,
            display_name TEXT,
            bpm REAL,
            key TEXT,
            key_conf REAL,
            loudness REAL,
            brightness REAL,
            sample_class TEXT,
            pred_type TEXT,
            status TEXT,
            error_code TEXT,
            quality_note TEXT,
            tags TEXT,
            analyzed_at TEXT,
            analyzer_version TEXT,
            cue_start_ms INTEGER DEFAULT 0,
            attack_ms INTEGER DEFAULT NULL,
            loop_start_ms INTEGER DEFAULT NULL,
            loop_end_ms INTEGER DEFAULT NULL,
            cue_source TEXT DEFAULT 'manual',
            cue_updated_at TEXT DEFAULT NULL,
            FOREIGN KEY(folder_id) REFERENCES folders(id)
        );
        """
    )
    conn.commit()
    conn.close()


def test_new_library_db_has_cue_columns(library_db: Path):
    columns = _sample_columns(library_db)
    assert "cue_start_ms" in columns
    assert "attack_ms" in columns
    assert "loop_start_ms" in columns
    assert "loop_end_ms" in columns
    assert "cue_source" in columns
    assert "cue_updated_at" in columns
    assert "loop_source" in columns
    assert "attack_source" in columns
    assert WORKBENCH_LIBRARY_SCHEMA_VERSION == 4


def test_legacy_library_db_is_migrated_to_add_cue_columns(tmp_path: Path):
    db_path = tmp_path / "state" / "workbench_library.db"
    _create_legacy_v1_library_db(db_path)
    assert "cue_start_ms" not in _sample_columns(db_path)

    init_workbench_library(db_path)
    init_workbench_library(db_path)

    columns = _sample_columns(db_path)
    assert "cue_start_ms" in columns
    assert "loop_end_ms" in columns


def test_legacy_v2_library_db_is_migrated_to_add_provenance_columns(tmp_path: Path):
    db_path = tmp_path / "state" / "workbench_library.db"
    _create_legacy_v2_library_db(db_path)
    columns = _sample_columns(db_path)
    assert "cue_start_ms" in columns
    assert "loop_source" not in columns
    assert "attack_source" not in columns

    init_workbench_library(db_path)
    init_workbench_library(db_path)

    columns = _sample_columns(db_path)
    assert "loop_source" in columns
    assert "attack_source" in columns


def test_load_sample_cue_returns_defaults_for_unknown_path(library_db: Path, tmp_path: Path):
    missing = tmp_path / "missing.wav"
    cue = load_sample_cue(missing, db_path=library_db)
    assert cue == default_workbench_cue_metadata()


def test_save_and_load_sample_cue_roundtrip(library_db: Path, tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()
    audio = folder / "tone.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 40)
    folder_id = upsert_folder(folder, db_path=library_db)
    row = WorkbenchRow(
        display_name="tone",
        relative_path="tone.wav",
        path=str(audio.resolve()),
        bpm=120.0,
        key="C",
        key_conf=0.8,
        loudness=-12.0,
        brightness=1500.0,
        sample_class="oneshot",
        pred_type="Kick",
        status="ok",
    )
    upsert_sample(folder_id, row, size_bytes=44, mtime_ns=100, db_path=library_db)

    metadata = WorkbenchCueMetadata(
        cue_start_ms=250,
        attack_ms=120,
        loop_start_ms=500,
        loop_end_ms=1500,
        cue_source="manual",
        loop_source="manual",
        attack_source="detected",
    )
    save_sample_cue(audio.resolve(), metadata, db_path=library_db, duration_ms=2000)
    loaded = load_sample_cue(audio.resolve(), db_path=library_db)

    assert loaded.cue_start_ms == 250
    assert loaded.attack_ms == 120
    assert loaded.loop_start_ms == 500
    assert loaded.loop_end_ms == 1500
    assert loaded.cue_source == "manual"
    assert loaded.loop_source == "manual"
    assert loaded.attack_source == "detected"
    assert loaded.cue_updated_at is not None


def test_save_sample_cue_rejects_negative_values(library_db: Path, tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()
    audio = folder / "kick.wav"
    audio.write_bytes(b"data")
    folder_id = upsert_folder(folder, db_path=library_db)
    row = WorkbenchRow(
        display_name="kick",
        relative_path="kick.wav",
        path=str(audio.resolve()),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=None,
        pred_type=None,
        status="ok",
    )
    upsert_sample(folder_id, row, size_bytes=4, mtime_ns=100, db_path=library_db)

    with pytest.raises(WorkbenchCueValidationError):
        save_sample_cue(
            audio.resolve(),
            WorkbenchCueMetadata(cue_start_ms=-1),
            db_path=library_db,
        )


def test_save_sample_cue_rejects_invalid_loop_range(library_db: Path, tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()
    audio = folder / "loop.wav"
    audio.write_bytes(b"data")
    folder_id = upsert_folder(folder, db_path=library_db)
    row = WorkbenchRow(
        display_name="loop",
        relative_path="loop.wav",
        path=str(audio.resolve()),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class="loop",
        pred_type=None,
        status="ok",
    )
    upsert_sample(folder_id, row, size_bytes=4, mtime_ns=100, db_path=library_db)

    with pytest.raises(WorkbenchCueValidationError):
        save_sample_cue(
            audio.resolve(),
            WorkbenchCueMetadata(loop_start_ms=1000, loop_end_ms=500),
            db_path=library_db,
        )


def test_save_sample_cue_unknown_sample_raises(library_db: Path, tmp_path: Path):
    missing = tmp_path / "ghost.wav"
    missing.write_bytes(b"data")
    with pytest.raises(WorkbenchCueNotFoundError):
        save_sample_cue(missing, WorkbenchCueMetadata(), db_path=library_db)


def test_upsert_sample_preserves_saved_cue_metadata(library_db: Path, tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()
    audio = folder / "tone.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 40)
    folder_id = upsert_folder(folder, db_path=library_db)
    row = WorkbenchRow(
        display_name="tone",
        relative_path="tone.wav",
        path=str(audio.resolve()),
        bpm=120.0,
        key="C",
        key_conf=0.8,
        loudness=-12.0,
        brightness=1500.0,
        sample_class="oneshot",
        pred_type="Kick",
        status="ok",
    )
    upsert_sample(folder_id, row, size_bytes=44, mtime_ns=100, db_path=library_db)
    save_sample_cue(
        audio.resolve(),
        WorkbenchCueMetadata(cue_start_ms=400),
        db_path=library_db,
    )

    updated = WorkbenchRow(
        display_name="tone",
        relative_path="tone.wav",
        path=str(audio.resolve()),
        bpm=128.0,
        key="D",
        key_conf=0.9,
        loudness=-10.0,
        brightness=1600.0,
        sample_class="oneshot",
        pred_type="Kick",
        status="ok",
    )
    upsert_sample(folder_id, updated, size_bytes=44, mtime_ns=100, db_path=library_db)

    cue = load_sample_cue(audio.resolve(), db_path=library_db)
    assert cue.cue_start_ms == 400
    assert lookup_sample(audio.resolve(), 44, 100, db_path=library_db).bpm == 128.0


def _cache_row(
    folder_id: int,
    *,
    folder: Path,
    name: str,
    library_db: Path,
) -> None:
    audio = folder / name
    audio.write_bytes(b"RIFF" + b"\x00" * 40)
    row = WorkbenchRow(
        display_name=name.replace(".wav", ""),
        relative_path=name,
        path=str(audio.resolve()),
        bpm=120.0,
        key="C",
        key_conf=0.8,
        loudness=-12.0,
        brightness=1500.0,
        sample_class="oneshot",
        pred_type="Kick",
        status="ok",
    )
    upsert_sample(folder_id, row, size_bytes=44, mtime_ns=100, db_path=library_db)


def test_load_all_cached_samples_returns_rows_from_multiple_folders(
    library_db: Path,
    tmp_path: Path,
) -> None:
    folder_a = tmp_path / "pack_a"
    folder_b = tmp_path / "pack_b"
    folder_a.mkdir()
    folder_b.mkdir()
    id_a = upsert_folder(folder_a, db_path=library_db)
    id_b = upsert_folder(folder_b, db_path=library_db)
    _cache_row(id_a, folder=folder_a, name="kick.wav", library_db=library_db)
    _cache_row(id_b, folder=folder_b, name="snare.wav", library_db=library_db)

    rows = load_all_cached_samples(db_path=library_db)
    assert len(rows) == 2
    folders = {row.library_folder_path for row in rows}
    assert folders == {str(folder_a.resolve()), str(folder_b.resolve())}


def test_load_all_cached_samples_excludes_removed_folder(
    library_db: Path,
    tmp_path: Path,
) -> None:
    folder_a = tmp_path / "pack_a"
    folder_b = tmp_path / "pack_b"
    folder_a.mkdir()
    folder_b.mkdir()
    id_a = upsert_folder(folder_a, db_path=library_db)
    id_b = upsert_folder(folder_b, db_path=library_db)
    _cache_row(id_a, folder=folder_a, name="kick.wav", library_db=library_db)
    _cache_row(id_b, folder=folder_b, name="snare.wav", library_db=library_db)

    remove_library_folder(folder_b, db_path=library_db)
    rows = load_all_cached_samples(db_path=library_db)

    assert len(rows) == 1
    assert rows[0].library_folder_path == str(folder_a.resolve())


def test_load_all_cached_samples_to_workbench_row_includes_library_folder(
    library_db: Path,
    tmp_path: Path,
) -> None:
    folder = tmp_path / "pack"
    folder.mkdir()
    folder_id = upsert_folder(folder, db_path=library_db)
    _cache_row(folder_id, folder=folder, name="tone.wav", library_db=library_db)

    wb_row = load_all_cached_samples(db_path=library_db)[0].to_workbench_row()
    assert wb_row.details.get("library_folder") == str(folder.resolve())
    assert wb_row.relative_path.startswith("pack/")


def test_new_library_db_has_playlist_tables(library_db: Path):
    with connect_workbench_library(library_db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "playlists" in tables
    assert "playlist_samples" in tables


def test_legacy_v3_library_db_is_migrated_to_add_playlist_tables(tmp_path: Path):
    db_path = tmp_path / "state" / "workbench_library.db"
    _create_legacy_v1_library_db(db_path)
    init_workbench_library(db_path)
    with connect_workbench_library(db_path) as conn:
        before = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='playlists'"
        ).fetchone()
    assert before is not None


def test_normalize_playlist_name_rejects_empty():
    with pytest.raises(WorkbenchPlaylistValidationError):
        normalize_playlist_name("   ")


def test_create_playlist_and_list_sorted(library_db: Path):
    create_playlist("Song B", db_path=library_db)
    create_playlist("Song A", db_path=library_db)
    names = [playlist.name for playlist in list_playlists(db_path=library_db)]
    assert names == ["Song A", "Song B"]


def test_add_sample_to_playlist_prevents_duplicates(library_db: Path, tmp_path: Path):
    sample = tmp_path / "kick.wav"
    sample.write_bytes(b"wav")
    playlist = create_playlist("Song A", db_path=library_db)
    assert add_sample_to_playlist(playlist.id, sample, db_path=library_db) == "added"
    assert add_sample_to_playlist(playlist.id, sample, db_path=library_db) == "duplicate"


def test_get_or_create_playlist_is_idempotent(library_db: Path):
    first = get_or_create_playlist("Song A", db_path=library_db)
    second = get_or_create_playlist("song a", db_path=library_db)
    assert first.id == second.id
    assert len(list_playlists(db_path=library_db)) == 1
