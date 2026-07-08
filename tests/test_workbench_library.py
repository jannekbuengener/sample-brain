from __future__ import annotations

from pathlib import Path

import pytest

from src.workbench_library import (
    WORKBENCH_ANALYZER_VERSION,
    init_workbench_library,
    lookup_sample,
    normalize_display_name,
    upsert_folder,
    upsert_sample,
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
