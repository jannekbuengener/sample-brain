"""#766 Favorites LibraryScope + compact libraryScopeBar navigation."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow, load_favorite_workbench_rows
from src.workbench_library import (
    init_workbench_library,
    list_favorite_sample_paths,
    set_sample_favorite,
    toggle_sample_favorite,
    workbench_library_db_path,
)
from src.workbench_library_navigation import (
    LibraryNodeKind,
    LibraryScopeKind,
    WorkbenchLibraryNavigation,
)
from src.workbench_qml import (
    QML_SOURCE,
    Screen1QmlInteractionAdapter,
    Screen1QmlViewModel,
    _sync_runtime_browser_state,
)
from src.workbench_qml_library import WorkbenchLibraryTreeState
from src.workbench_qml_runtime import Screen1QmlRuntimeComposition


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


def _row(path: Path, name: str | None = None) -> WorkbenchRow:
    label = name or path.name
    return WorkbenchRow(
        display_name=label,
        relative_path=label,
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


def test_favorites_scope_is_secondary_not_source_tree(library_db: Path) -> None:
    navigation = WorkbenchLibraryNavigation(library_db_path=library_db)
    top = navigation.top_level_nodes()
    secondary = navigation.secondary_nodes()

    assert [(node.node_id, node.kind) for node in top] == [
        ("container:sample-sources", LibraryNodeKind.SAMPLE_SOURCES),
    ]
    assert [(node.node_id, node.kind) for node in secondary] == [
        ("scope:all-library", LibraryNodeKind.ALL_SAMPLES),
        ("container:collections", LibraryNodeKind.COLLECTIONS),
        ("scope:favorites", LibraryNodeKind.FAVORITES),
        ("scope:recordings", LibraryNodeKind.RECORDINGS),
    ]
    source_ids = [node.node_id for node in navigation.children("container:sample-sources")]
    assert not any("favorite" in node_id.lower() for node_id in source_ids)

    scope = navigation.resolve_scope("scope:favorites")
    assert scope is not None
    assert scope.kind is LibraryScopeKind.FAVORITES


def test_library_scope_bar_exposes_distinct_favorites_control() -> None:
    source = QML_SOURCE
    assert 'objectName: "libraryFavoritesScopeButton"' in source
    assert 'Accessible.name: "Favorites"' in source
    assert 'libraryScopeBar.mode = "favorites"' in source
    assert 'selectLibraryNode("scope:favorites")' in source
    assert 'Accessible.name: "Collections"' in source
    assert 'objectName: "libraryCollectionsScopeButton"' in source
    # Favorites must remain distinct from Collections and must not use emoji glyphs.
    favorites_block = source.split('objectName: "libraryFavoritesScopeButton"', 1)[1].split(
        'objectName: "libraryRecordingsScopeButton"', 1
    )[0]
    assert "★" not in favorites_block
    assert "⭐" not in favorites_block
    for forbidden in ("My Kits", "Recently Added", "Splice", "User Library"):
        assert forbidden not in source


def test_favorites_loader_projects_only_favorited_paths_deterministically(
    library_db: Path, tmp_path: Path
) -> None:
    first = tmp_path / "a_kick.wav"
    second = tmp_path / "b_snare.wav"
    missing = tmp_path / "gone_hat.wav"
    first.write_bytes(b"wav")
    second.write_bytes(b"wav")
    assert set_sample_favorite(second, True, db_path=library_db) is True
    assert set_sample_favorite(first, True, db_path=library_db) is True
    assert set_sample_favorite(missing, True, db_path=library_db) is True
    expected_paths = list_favorite_sample_paths(db_path=library_db)
    assert set(Path(path).name for path in expected_paths) == {
        "a_kick.wav",
        "b_snare.wav",
        "gone_hat.wav",
    }

    rows = load_favorite_workbench_rows(library_db_path=library_db)
    assert [row.path for row in rows] == expected_paths
    assert all(row.details.get("song_playlist") is None for row in rows)
    missing_row = next(row for row in rows if Path(row.path).name == "gone_hat.wav")
    assert missing_row.status == "error"
    assert missing_row.error_code == "unsupported_or_unreadable_audio"


def test_runtime_favorites_scope_loads_favorite_rows_only(
    library_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sample = tmp_path / "fav.wav"
    other = tmp_path / "other.wav"
    sample.write_bytes(b"wav")
    other.write_bytes(b"wav")
    set_sample_favorite(sample, True, db_path=library_db)

    navigation = WorkbenchLibraryNavigation(library_db_path=library_db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=library_db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    intent = composition.library_tree.select("scope:favorites")
    assert intent is not None
    assert intent.scope.kind is LibraryScopeKind.FAVORITES

    state = composition.dispatch_selection(intent)
    assert state.error is None
    assert state.browser_context == "Favorites"
    assert [Path(row.path).name for row in state.rows] == ["fav.wav"]
    assert all(Path(row.path).name != "other.wav" for row in state.rows)


def test_unfavorite_in_favorites_scope_removes_row_immediately(
    library_db: Path, tmp_path: Path
) -> None:
    keep = tmp_path / "keep.wav"
    drop = tmp_path / "drop.wav"
    keep.write_bytes(b"wav")
    drop.write_bytes(b"wav")
    set_sample_favorite(keep, True, db_path=library_db)
    set_sample_favorite(drop, True, db_path=library_db)

    navigation = WorkbenchLibraryNavigation(library_db_path=library_db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=library_db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    intent = composition.library_tree.select("scope:favorites")
    assert intent is not None
    composition.dispatch_selection(intent)

    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        library_db_path=library_db,
    )
    adapter._runtime_composition = composition
    _sync_runtime_browser_state(view_model, adapter, composition)
    names = {Path(row.source_row.path).name for row in view_model.browser_rows}
    assert names == {"keep.wav", "drop.wav"}
    assert all(row.is_favorite for row in view_model.browser_rows)

    drop_index = next(
        index
        for index, row in enumerate(view_model.browser_rows)
        if Path(row.source_row.path).name == "drop.wav"
    )
    assert adapter.toggle_favorite(drop_index) is False
    assert [Path(row.source_row.path).name for row in view_model.browser_rows] == [
        "keep.wav"
    ]
    assert view_model.browser_rows[0].is_favorite is True
    assert list_favorite_sample_paths(db_path=library_db) == [str(keep.resolve())]
    # Source files remain untouched.
    assert keep.is_file() and drop.is_file()


def test_toggle_outside_favorites_updates_flag_without_removing_row(
    library_db: Path, tmp_path: Path
) -> None:
    sample = tmp_path / "browser.wav"
    sample.write_bytes(b"wav")
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    view_model.set_browser_state(
        rows=(_row(sample),),
        selected_index=0,
        browser_context="Samples",
        error=None,
        favorite_paths=set(),
    )
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        library_db_path=library_db,
    )
    assert adapter.toggle_favorite(0) is True
    assert view_model.browser_rows[0].is_favorite is True
    assert Path(view_model.browser_rows[0].source_row.path).name == "browser.wav"
    assert toggle_sample_favorite(sample, db_path=library_db) is False


PY_SIDE6_AVAILABLE = __import__("importlib").util.find_spec("PySide6") is not None


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_automated_runtime_visual_acceptance_favorites_scope(
    library_db: Path, tmp_path: Path
) -> None:
    """AUTOMATED_RUNTIME_VISUAL_ACCEPTANCE for #766 Favorites navigation."""
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_qml_spike import _settle_qml_frame

    keep = tmp_path / "keep_fav.wav"
    drop = tmp_path / "drop_fav.wav"
    keep.write_bytes(b"wav")
    drop.write_bytes(b"wav")
    set_sample_favorite(keep, True, db_path=library_db)
    set_sample_favorite(drop, True, db_path=library_db)

    navigation = WorkbenchLibraryNavigation(library_db_path=library_db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=library_db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
        library_tree=composition.library_tree,
    )
    state_dir = tmp_path / "ui-state"
    state_dir.mkdir()
    apply_clean_start_launch(view_model, composition, state_dir=state_dir)
    view_model.set_library_revealed(True)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.resize(1400, 900)
    window.show()
    engine._screen1_interaction_bridge.refreshState()
    engine._screen1_layout_model.syncFromInteraction()
    _settle_qml_frame(app)
    adapter = engine._screen1_interaction_adapter
    library_bridge = engine._screen1_library_bridge
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    try:
        bar = window.findChild(QQuickItem, "libraryScopeBar")
        favorites_btn = window.findChild(QQuickItem, "libraryFavoritesScopeButton")
        collections_btn = window.findChild(QQuickItem, "libraryCollectionsScopeButton")
        assert bar is not None and bar.isVisible()
        assert favorites_btn is not None and favorites_btn.isVisible()
        assert collections_btn is not None and collections_btn.isVisible()
        assert favorites_btn.objectName() != collections_btn.objectName()

        bar.setProperty("mode", "favorites")
        library_bridge.selectLibraryNode("scope:favorites")
        app.processEvents()
        _settle_qml_frame(app)

        assert view_model.browser_context == "Favorites"
        names = {Path(row.source_row.path).name for row in view_model.browser_rows}
        assert names == {"keep_fav.wav", "drop_fav.wav"}
        assert all(row.is_favorite for row in view_model.browser_rows)

        tree = window.findChild(QQuickItem, "libraryTree")
        coll = window.findChild(QQuickItem, "libraryCollectionList")
        assert tree is not None and not tree.isVisible()
        assert coll is not None and not coll.isVisible()
        assert float(bar.y()) > 80.0

        drop_index = next(
            index
            for index, row in enumerate(view_model.browser_rows)
            if Path(row.source_row.path).name == "drop_fav.wav"
        )
        assert adapter.toggle_favorite(drop_index) is False
        app.processEvents()
        _settle_qml_frame(app)
        assert [Path(row.source_row.path).name for row in view_model.browser_rows] == [
            "keep_fav.wav"
        ]

        bar.setProperty("mode", "collections")
        app.processEvents()
        _settle_qml_frame(app)
        assert window.findChild(QQuickItem, "libraryCollectionList").isVisible()
        bar.setProperty("mode", "sources")
        app.processEvents()
        _settle_qml_frame(app)
        assert window.findChild(QQuickItem, "libraryTree").isVisible()

        grab = window.grabWindow()
        assert not grab.isNull()
        evidence_path = evidence_dir / "favorites_scope_runtime.png"
        assert grab.save(str(evidence_path))
        assert evidence_path.is_file() and evidence_path.stat().st_size > 0
    finally:
        window.close()
        app.processEvents()
