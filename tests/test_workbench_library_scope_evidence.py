"""Fail-closed capture + bottom scope-bar pin contracts for #837."""

from __future__ import annotations

import importlib.util

import pytest

from src.workbench_library_scope_evidence import (
    EVIDENCE_FILENAMES,
    SCOPE_ALL,
    SCOPE_COLLECTIONS,
    SCOPE_FAVORITES,
    SCOPE_RECORDINGS,
    SCOPE_SOURCES,
    ScopeCaptureError,
    assert_distinct_secondary_scope_hashes,
    assert_presentation_matches,
    expected_presentation,
    sha256_bytes,
)


def test_capture_helper_rejects_mislabeled_all_samples_as_favorites() -> None:
    observed = expected_presentation(
        SCOPE_ALL,
        browser_title="All Samples",
        tree_visible=False,
        collections_visible=False,
        scope_bar_y=40.0,
        header_bottom_y=23.0,
    )
    with pytest.raises(ScopeCaptureError, match="scope mode mismatch"):
        assert_presentation_matches(SCOPE_FAVORITES, observed)


def test_capture_helper_rejects_hidden_tree_for_primary_scopes() -> None:
    observed = expected_presentation(
        SCOPE_ALL,
        browser_title="All Samples",
        tree_visible=False,
        collections_visible=False,
        scope_bar_y=40.0,
        header_bottom_y=23.0,
    )
    with pytest.raises(ScopeCaptureError, match="visible Source Tree"):
        assert_presentation_matches(SCOPE_ALL, observed)


def test_capture_helper_rejects_footer_scope_bar() -> None:
    observed = expected_presentation(
        SCOPE_FAVORITES,
        browser_title="Favorites",
        tree_visible=False,
        collections_visible=False,
        scope_bar_y=568.0,
        header_bottom_y=23.0,
    )
    with pytest.raises(ScopeCaptureError, match="must follow the Library title row"):
        assert_presentation_matches(SCOPE_FAVORITES, observed)


def test_capture_helper_rejects_scope_bar_outside_header_bounds() -> None:
    for scope_bar_y in (22.0, 120.0):
        observed = expected_presentation(
            SCOPE_ALL,
            browser_title="All Samples",
            tree_visible=True,
            collections_visible=False,
            scope_bar_y=scope_bar_y,
            header_bottom_y=23.0,
        )
        with pytest.raises(ScopeCaptureError, match="must follow the Library title row"):
            assert_presentation_matches(SCOPE_ALL, observed)


def test_capture_helper_accepts_distinct_presentation_states() -> None:
    cases = (
        (
            SCOPE_SOURCES,
            expected_presentation(
                SCOPE_SOURCES,
                browser_title="Samples",
                tree_visible=True,
                collections_visible=False,
                scope_bar_y=40.0,
                header_bottom_y=23.0,
            ),
        ),
        (
            SCOPE_ALL,
            expected_presentation(
                SCOPE_ALL,
                browser_title="All Samples",
                tree_visible=True,
                collections_visible=False,
                scope_bar_y=40.0,
                header_bottom_y=23.0,
            ),
        ),
        (
            SCOPE_FAVORITES,
            expected_presentation(
                SCOPE_FAVORITES,
                browser_title="Favorites",
                tree_visible=True,
                collections_visible=False,
                scope_bar_y=40.0,
                header_bottom_y=23.0,
            ),
        ),
        (
            SCOPE_RECORDINGS,
            expected_presentation(
                SCOPE_RECORDINGS,
                browser_title="Records",
                tree_visible=True,
                collections_visible=False,
                scope_bar_y=40.0,
                header_bottom_y=23.0,
            ),
        ),
        (
            SCOPE_COLLECTIONS,
            expected_presentation(
                SCOPE_COLLECTIONS,
                browser_title="Collections",
                tree_visible=True,
                collections_visible=True,
                scope_bar_y=40.0,
                header_bottom_y=23.0,
            ),
        ),
    )
    for scope, presentation in cases:
        assert_presentation_matches(scope, presentation)


def test_evidence_integrity_guard_rejects_identical_secondary_hashes() -> None:
    poison = sha256_bytes(b"all-samples-poison")
    hashes = {
        EVIDENCE_FILENAMES[SCOPE_SOURCES]: sha256_bytes(b"sources"),
        EVIDENCE_FILENAMES[SCOPE_ALL]: poison,
        EVIDENCE_FILENAMES[SCOPE_FAVORITES]: poison,
        EVIDENCE_FILENAMES[SCOPE_RECORDINGS]: poison,
        EVIDENCE_FILENAMES[SCOPE_COLLECTIONS]: poison,
    }
    with pytest.raises(ScopeCaptureError, match="byte-identical"):
        assert_distinct_secondary_scope_hashes(hashes)


def test_evidence_integrity_guard_accepts_distinct_secondary_hashes() -> None:
    hashes = {
        EVIDENCE_FILENAMES[SCOPE_SOURCES]: sha256_bytes(b"sources"),
        EVIDENCE_FILENAMES[SCOPE_ALL]: sha256_bytes(b"all"),
        EVIDENCE_FILENAMES[SCOPE_FAVORITES]: sha256_bytes(b"favorites"),
        EVIDENCE_FILENAMES[SCOPE_RECORDINGS]: sha256_bytes(b"recordings"),
        EVIDENCE_FILENAMES[SCOPE_COLLECTIONS]: sha256_bytes(b"collections"),
    }
    assert_distinct_secondary_scope_hashes(hashes)


PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_scope_bar_y_stable_across_modes(tmp_path) -> None:
    """Runtime: primary rows follow the title and Sources stays visible."""
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library import init_workbench_library
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_qml_spike import _settle_qml_frame

    db = tmp_path / "library.db"
    init_workbench_library(db)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
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
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.resize(1400, 900)
    window.show()
    engine._screen1_interaction_bridge.refreshState()
    engine._screen1_layout_model.syncFromInteraction()
    _settle_qml_frame(app)
    bridge = engine._screen1_library_bridge
    try:
        bar_ys: dict[str, float] = {}
        for mode, node_id in (
            ("sources", None),
            ("all", "scope:all-library"),
            ("favorites", "scope:favorites"),
            ("recordings", "scope:recordings"),
            ("collections", None),
        ):
            bar = window.findChild(QQuickItem, "libraryScopeBar")
            assert bar is not None
            if node_id:
                bridge.selectLibraryNode(node_id)
            elif mode == "collections":
                bridge.showLibrarySection("collections")
            app.processEvents()
            _settle_qml_frame(app)
            bar = window.findChild(QQuickItem, "libraryScopeBar")
            tree = window.findChild(QQuickItem, "libraryTree")
            coll = window.findChild(QQuickItem, "libraryCollectionList")
            footer = window.findChild(QQuickItem, "programFooterBand")
            header = window.findChild(QQuickItem, "libraryHeaderRow")
            host = window.findChild(QQuickItem, "libraryContentHost")
            fav = window.findChild(QQuickItem, "libraryFavoritesScopeButton")
            catalog = window.findChild(QQuickItem, "libraryCatalogScopeButton")
            assert bar is not None and footer is not None and header is not None and host is not None
            assert fav is not None
            assert catalog is None
            assert not footer.isAncestorOf(bar)
            pane = window.findChild(QQuickItem, "libraryPane")
            assert pane is not None and pane.isAncestorOf(bar)
            bar_in_pane = bar.mapToItem(pane, 0, 0)
            title_bottom_in_pane = header.mapToItem(
                pane, 0, float(header.height())
            ).y()
            bar_ys[mode] = float(bar_in_pane.y())
            assert bar_in_pane.y() >= title_bottom_in_pane - 1.0
            assert tree is not None and tree.isVisible()
            if mode == "sources":
                assert coll is not None and not coll.isVisible()
            elif mode == "collections":
                assert coll is not None and coll.isVisible()
            else:
                assert coll is not None and not coll.isVisible()
        assert abs(bar_ys["all"] - bar_ys["sources"]) < 1.0
        assert abs(bar_ys["favorites"] - bar_ys["sources"]) < 1.0
        assert abs(bar_ys["recordings"] - bar_ys["sources"]) < 1.0
        assert abs(bar_ys["collections"] - bar_ys["sources"]) < 1.0
    finally:
        window.close()
        app.processEvents()
