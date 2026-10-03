"""#837 bottom Library icon navigation — Collections / Favorites / Recordings.

TEST_GATE / TEST_FREEZE — presentation placement above footer, visible scopes,
Catalog navigation removed (core retained), Recordings projection, a11y,
no auto-preview on view switch, Sample Sources non-regression seam.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.recording_take import RECORDINGS_PLAYLIST_NAME
from src.workbench_controller import (
    load_favorite_workbench_rows,
    load_playlist_workbench_rows,
    load_recording_workbench_rows,
)
from src.workbench_library import (
    add_sample_to_playlist,
    create_playlist,
    get_or_create_playlist,
    init_workbench_library,
    set_sample_favorite,
    workbench_library_db_path,
)
from src.workbench_library_navigation import (
    LibraryNodeKind,
    LibraryScopeKind,
    WorkbenchLibraryNavigation,
)
from src.workbench_qml import QML_SOURCE
from src.workbench_qml_library import WorkbenchLibraryTreeState
from src.workbench_qml_runtime import Screen1QmlRuntimeComposition


PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


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


def test_docs_gate_bottom_icon_presentation_authority() -> None:
    tree = Path("docs/WORKBENCH_QML_LIBRARY_TREE_CONTRACT.md").read_text(encoding="utf-8")
    nav = Path("docs/WORKBENCH_LIBRARY_NAVIGATION_CONTRACT.md").read_text(encoding="utf-8")
    hint = Path("docs/WORKBENCH_CONTEXT_HINT_CONTRACT.md").read_text(encoding="utf-8")
    assert "#837" in tree
    assert "bottom of the left Library/Browser pane" in tree
    assert "above the" in tree.lower() and "footer" in tree.lower()
    assert "scope:recordings" in tree
    assert "visible Catalog" in tree or "Catalog / Katalog" in tree
    assert "Catalog data ownership" in tree or "Catalog loaders" in tree
    assert "scope:recordings" in nav
    assert "LibraryScopeKind.RECORDINGS" in nav or "RECORDINGS" in nav
    assert "library.scope.recordings" in hint
    assert "library.scope.catalog" not in hint.split("### V1 semantic IDs", 1)[1].split(
        "`library.add_source`", 1
    )[0]


def test_secondary_nodes_bottom_bar_taxonomy_without_visible_catalog(
    library_db: Path,
) -> None:
    navigation = WorkbenchLibraryNavigation(library_db_path=library_db)
    assert [(node.node_id, node.kind) for node in navigation.top_level_nodes()] == [
        ("container:sample-sources", LibraryNodeKind.SAMPLE_SOURCES),
    ]
    assert [(node.node_id, node.kind) for node in navigation.secondary_nodes()] == [
        ("scope:all-library", LibraryNodeKind.ALL_SAMPLES),
        ("container:collections", LibraryNodeKind.COLLECTIONS),
        ("scope:favorites", LibraryNodeKind.FAVORITES),
        ("scope:recordings", LibraryNodeKind.RECORDINGS),
    ]
    assert "scope:catalog-readonly" not in [
        node.node_id for node in navigation.secondary_nodes()
    ]
    # Catalog core remains resolvable even without a visible navigation entry.
    catalog = navigation.resolve_scope("scope:catalog-readonly")
    assert catalog is not None
    assert catalog.kind is LibraryScopeKind.CATALOG
    recordings = navigation.resolve_scope("scope:recordings")
    assert recordings is not None
    assert recordings.kind is LibraryScopeKind.RECORDINGS


def test_qml_bottom_icon_bar_contract_and_accessible_names() -> None:
    source = QML_SOURCE
    assert 'objectName: "libraryScopeBar"' in source
    assert 'objectName: "librarySourcesScopeButton"' in source
    assert 'objectName: "libraryAllSamplesScopeButton"' in source
    assert 'objectName: "libraryCollectionsScopeButton"' in source
    assert 'objectName: "libraryFavoritesScopeButton"' in source
    assert 'objectName: "libraryRecordingsScopeButton"' in source
    assert 'objectName: "libraryCatalogScopeButton"' not in source
    assert 'Accessible.name: "Sample Sources"' in source
    assert 'Accessible.name: "All Samples"' in source
    assert 'Accessible.name: "Collections"' in source
    assert 'Accessible.name: "Favorites"' in source
    assert 'Accessible.name: "Recordings"' in source
    assert 'Accessible.name: "Catalog"' not in source
    assert 'selectLibraryNode("scope:favorites")' in source
    assert 'selectLibraryNode("scope:recordings")' in source
    assert 'selectLibraryNode("scope:all-library")' in source
    assert 'libraryScopeBar.mode = "recordings"' in source
    assert 'library.scope.recordings' in source
    assert "lokale Aufnahmen" in source
    # Add Source remains in the Library header, not relocated into the icon bar.
    header = source.split('id: libraryHeaderRow', 1)[1].split(
        'objectName: "libraryContentHost"', 1
    )[0]
    assert 'text: "Add Source"' in header
    # Favorites uses a geometric star canvas path, not emoji glyphs.
    favorites_block = source.split('objectName: "libraryFavoritesScopeButton"', 1)[1].split(
        'objectName: "libraryRecordingsScopeButton"', 1
    )[0]
    assert "★" not in favorites_block
    assert "⭐" not in favorites_block
    assert "for (var i = 0; i < 5; i++)" in favorites_block
    # Scope bar is Library-pane chrome after the content host, not ApplicationWindow footer.
    pane_block = source.split('id: libraryPane', 1)[1].split(
        'objectName: "elasticHandleAfterLibrary"', 1
    )[0]
    host_pos = pane_block.find('objectName: "libraryContentHost"')
    bar_pos = pane_block.find('objectName: "libraryScopeBar"')
    assert host_pos >= 0 and bar_pos >= 0
    assert host_pos < bar_pos, "libraryScopeBar must sit below libraryContentHost"
    footer_block = source.split("footer:", 1)[1].split("header:", 1)[0]
    assert 'objectName: "libraryScopeBar"' not in footer_block
    assert 'objectName: "contextHintPlacement"' in footer_block
    # Icon bar must not depend on classic ToolTips for discoverability.
    scope_block = source.split('objectName: "libraryScopeBar"', 1)[1].split(
        'objectName: "elasticHandleAfterLibrary"', 1
    )[0]
    assert "ToolTip." not in scope_block
    assert "contextHintState.reportHover" in scope_block
    assert "contextHintState.reportFocus" in scope_block


def test_recordings_loader_projects_existing_playlist_not_collections_dummy(
    library_db: Path, tmp_path: Path
) -> None:
    take = tmp_path / "recording_take.wav"
    other = tmp_path / "collection_only.wav"
    take.write_bytes(b"RIFF....WAVE")
    other.write_bytes(b"RIFF....WAVE")
    recordings = get_or_create_playlist(RECORDINGS_PLAYLIST_NAME, db_path=library_db)
    song = create_playlist("Song Pack", db_path=library_db)
    add_sample_to_playlist(recordings.id, take, db_path=library_db)
    add_sample_to_playlist(song.id, other, db_path=library_db)

    rows = load_recording_workbench_rows(library_db_path=library_db)
    assert [Path(row.path).name for row in rows] == ["recording_take.wav"]
    playlist_rows = load_playlist_workbench_rows(
        RECORDINGS_PLAYLIST_NAME, library_db_path=library_db
    )
    assert [row.path for row in rows] == [row.path for row in playlist_rows]
    # Empty when playlist absent in a fresh DB clone.
    empty_db = tmp_path / "empty.db"
    init_workbench_library(empty_db)
    assert load_recording_workbench_rows(library_db_path=empty_db) == []


def test_recordings_scope_selection_is_typed_and_distinct_from_favorites(
    library_db: Path, tmp_path: Path
) -> None:
    fav = tmp_path / "fav.wav"
    rec = tmp_path / "rec.wav"
    fav.write_bytes(b"wav")
    rec.write_bytes(b"wav")
    set_sample_favorite(fav, True, db_path=library_db)
    recordings = get_or_create_playlist(RECORDINGS_PLAYLIST_NAME, db_path=library_db)
    add_sample_to_playlist(recordings.id, rec, db_path=library_db)

    navigation = WorkbenchLibraryNavigation(library_db_path=library_db)
    state = WorkbenchLibraryTreeState(navigation)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=library_db,
        tree_state=state,
    )
    fav_intent = composition.library_tree.select("scope:favorites")
    assert fav_intent is not None
    fav_state = composition.dispatch_selection(fav_intent)
    assert composition.browser_state.scope is not None
    assert composition.browser_state.scope.kind is LibraryScopeKind.FAVORITES
    assert [Path(row.path).name for row in fav_state.rows] == ["fav.wav"]
    assert all(row.path.endswith("fav.wav") for row in load_favorite_workbench_rows(
        library_db_path=library_db
    ))

    rec_intent = composition.library_tree.select("scope:recordings")
    assert rec_intent is not None
    rec_state = composition.dispatch_selection(rec_intent)
    assert composition.browser_state.scope is not None
    assert composition.browser_state.scope.kind is LibraryScopeKind.RECORDINGS
    assert [Path(row.path).name for row in rec_state.rows] == ["rec.wav"]
    assert composition.browser_state.scope.kind is not LibraryScopeKind.COLLECTION
    assert composition.browser_state.scope.kind is not LibraryScopeKind.FAVORITES


def test_view_switch_does_not_auto_select_or_preview(
    library_db: Path, tmp_path: Path
) -> None:
    sample = tmp_path / "one.wav"
    sample.write_bytes(b"wav")
    set_sample_favorite(sample, True, db_path=library_db)
    navigation = WorkbenchLibraryNavigation(library_db_path=library_db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=library_db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    for node_id in (
        "scope:all-library",
        "scope:favorites",
        "scope:recordings",
    ):
        intent = composition.library_tree.select(node_id)
        assert intent is not None
        state = composition.dispatch_selection(intent)
        assert state.selected_index == -1
        assert state.error is None
    # Collections container is not a sample scope; selecting it must not invent a browser selection.
    assert composition.library_tree.select("container:collections") is None


def test_catalog_python_core_still_present() -> None:
    from src import workbench_catalog
    from src.workbench_controller import load_catalog_rows
    from src.workbench_library_navigation import LibraryScopeKind

    assert hasattr(workbench_catalog, "catalog_available")
    assert callable(load_catalog_rows)
    assert LibraryScopeKind.CATALOG.value == "catalog"
    source = QML_SOURCE
    assert "load_catalog_rows" in Path("src/workbench_qml_runtime.py").read_text(
        encoding="utf-8"
    )
    assert 'objectName: "libraryCatalogScopeButton"' not in source


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_bottom_icon_bar_above_footer_not_in_footer(tmp_path: Path) -> None:
    """Runtime geometry: icon bar in library pane bottom, above app footer."""
    from PySide6.QtCore import QPointF
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml import (
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_spike import _settle_qml_frame

    db = tmp_path / "library.db"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    init_workbench_library(db)
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
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
    apply_clean_start_launch(view_model, composition, state_dir=state_dir)
    view_model.set_library_revealed(True)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )

    evidence_dir = tmp_path / "visual"
    evidence_dir.mkdir()
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    try:
        for width, height, tag in ((1400, 900, "normal"), (1100, 720, "small")):
            window.resize(width, height)
            window.show()
            engine._screen1_interaction_bridge.refreshState()
            engine._screen1_layout_model.syncFromInteraction()
            _settle_qml_frame(app)

            pane = window.findChild(QQuickItem, "libraryPane")
            host = window.findChild(QQuickItem, "libraryContentHost")
            bar = window.findChild(QQuickItem, "libraryScopeBar")
            footer = window.findChild(QQuickItem, "contextHintPlacement")
            catalog = window.findChild(QQuickItem, "libraryCatalogScopeButton")
            favorites = window.findChild(QQuickItem, "libraryFavoritesScopeButton")
            collections = window.findChild(QQuickItem, "libraryCollectionsScopeButton")
            recordings = window.findChild(QQuickItem, "libraryRecordingsScopeButton")
            all_samples = window.findChild(QQuickItem, "libraryAllSamplesScopeButton")
            sources = window.findChild(QQuickItem, "librarySourcesScopeButton")
            assert pane is not None and host is not None and bar is not None
            assert footer is not None
            assert catalog is None
            assert favorites is not None and favorites.isVisible()
            assert collections is not None and collections.isVisible()
            assert recordings is not None and recordings.isVisible()
            assert all_samples is not None and all_samples.isVisible()
            assert sources is not None and sources.isVisible()

            # Geometry: content host above bar; bar above footer; bar inside pane.
            host_bottom = float(host.mapToItem(pane, QPointF(0, host.height())).y())
            bar_top = float(bar.mapToItem(pane, QPointF(0, 0)).y())
            bar_bottom_global = float(bar.mapToItem(window.contentItem(), QPointF(0, bar.height())).y())
            footer_top_global = float(
                footer.mapToItem(window.contentItem(), QPointF(0, 0)).y()
            )
            assert bar_top >= host_bottom - 1.0, (
                f"{tag}: scope bar must sit below content host "
                f"(host_bottom={host_bottom}, bar_top={bar_top})"
            )
            assert bar_bottom_global <= footer_top_global + 1.0, (
                f"{tag}: scope bar must remain above app footer "
                f"(bar_bottom={bar_bottom_global}, footer_top={footer_top_global})"
            )
            assert float(bar.y()) > 80.0, (
                f"{tag}: bottom icon bar must not remain under the header (y={bar.y()})"
            )

            # Activate each secondary control; tree retreats except Sources.
            bridge = engine._screen1_library_bridge
            for mode, node_id in (
                ("all", "scope:all-library"),
                ("favorites", "scope:favorites"),
                ("recordings", "scope:recordings"),
                ("collections", None),
                ("sources", None),
            ):
                bar.setProperty("mode", mode)
                if node_id:
                    bridge.selectLibraryNode(node_id)
                app.processEvents()
                _settle_qml_frame(app)
                tree = window.findChild(QQuickItem, "libraryTree")
                coll = window.findChild(QQuickItem, "libraryCollectionList")
                assert tree is not None and coll is not None
                if mode == "sources":
                    assert tree.isVisible()
                    assert not coll.isVisible()
                elif mode == "collections":
                    assert coll.isVisible()
                    assert not tree.isVisible()
                else:
                    assert not tree.isVisible()
                    assert not coll.isVisible()
                # Mode switches must not relocate the bar into the footer.
                bar2 = window.findChild(QQuickItem, "libraryScopeBar")
                assert bar2 is not None
                assert float(bar2.mapToItem(pane, QPointF(0, 0)).y()) >= host_bottom - 1.0

            grab = window.grabWindow()
            out = evidence_dir / f"library_bottom_icons_{tag}.png"
            assert grab.save(str(out)), f"failed to save {out}"
            assert out.is_file() and out.stat().st_size > 0
    finally:
        window.close()
        app.processEvents()
