"""#766 minimum Favorites persistence + #767 Browser Favorite wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_library import (
    WORKBENCH_LIBRARY_SCHEMA_VERSION,
    connect_workbench_library,
    init_workbench_library,
    is_sample_favorite,
    list_favorite_sample_paths,
    set_sample_favorite,
    toggle_sample_favorite,
    workbench_library_db_path,
)
from src.workbench_qml import (
    QmlBrowserRow,
    Screen1QmlInteractionAdapter,
    Screen1QmlViewModel,
    _qml_row,
)


@pytest.fixture
def library_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state))
    return state


@pytest.fixture
def library_db(library_state: Path) -> Path:
    db_path = workbench_library_db_path(state_dir=library_state)
    init_workbench_library(db_path)
    return db_path


def _row(path: Path, name: str = "kick.wav") -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=name,
        path=str(path),
        bpm=120.0,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=0.4,
        sample_class="one_shot",
        pred_type="Kick",
        status="ok",
        details={"duration_sec": 1.25},
    )


def test_new_library_db_has_favorite_samples_table(library_db: Path) -> None:
    assert WORKBENCH_LIBRARY_SCHEMA_VERSION == 5
    with connect_workbench_library(library_db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "favorite_samples" in tables
    # Favorites must not be a magic playlist row.
    assert "playlists" in tables


def test_favorite_toggle_persists_and_survives_reconnect(
    library_db: Path, tmp_path: Path
) -> None:
    sample = tmp_path / "kick.wav"
    sample.write_bytes(b"wav")
    assert not is_sample_favorite(sample, db_path=library_db)
    assert toggle_sample_favorite(sample, db_path=library_db) is True
    assert is_sample_favorite(sample, db_path=library_db) is True
    assert list_favorite_sample_paths(db_path=library_db) == [
        str(sample.resolve())
    ]

    # Fresh connection / process boundary.
    assert is_sample_favorite(sample, db_path=library_db) is True
    assert toggle_sample_favorite(sample, db_path=library_db) is False
    assert is_sample_favorite(sample, db_path=library_db) is False
    assert list_favorite_sample_paths(db_path=library_db) == []


def test_favorite_set_is_idempotent_and_not_a_rating(
    library_db: Path, tmp_path: Path
) -> None:
    sample = tmp_path / "snare.wav"
    sample.write_bytes(b"wav")
    assert set_sample_favorite(sample, True, db_path=library_db) is True
    assert set_sample_favorite(sample, True, db_path=library_db) is True
    assert set_sample_favorite(sample, False, db_path=library_db) is False
    assert set_sample_favorite(sample, False, db_path=library_db) is False
    # No rating columns / multi-star values in the domain table.
    with connect_workbench_library(library_db) as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(favorite_samples)").fetchall()
        }
    assert "rating" not in columns
    assert "stars" not in columns


def test_qml_row_projects_favorite_flag(tmp_path: Path) -> None:
    sample = tmp_path / "hat.wav"
    sample.write_bytes(b"wav")
    plain = _qml_row(_row(sample))
    assert plain.is_favorite is False
    starred = _qml_row(_row(sample), is_favorite=True)
    assert starred.is_favorite is True
    assert isinstance(starred, QmlBrowserRow)


def test_adapter_toggle_favorite_updates_projection_via_domain(
    library_db: Path, tmp_path: Path
) -> None:
    sample = tmp_path / "perc.wav"
    sample.write_bytes(b"wav")
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    view_model.set_browser_state(
        rows=(_row(sample),),
        selected_index=0,
        browser_context="Samples",
        error=None,
        favorite_paths={str(sample.resolve())},
    )
    assert view_model.browser_rows[0].is_favorite is True
    assert view_model.qml_context()["browserRows"][0]["favorite"] is True

    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        library_db_path=library_db,
    )
    # Seed domain so toggle starts from favorited.
    set_sample_favorite(sample, True, db_path=library_db)
    assert adapter.toggle_favorite(0) is False
    assert view_model.browser_rows[0].is_favorite is False
    assert is_sample_favorite(sample, db_path=library_db) is False
    assert adapter.toggle_favorite(0) is True
    assert view_model.browser_rows[0].is_favorite is True
    assert is_sample_favorite(sample, db_path=library_db) is True
