"""#770 bottom-center context hint for icon-only Screen-1 controls.

TEST_GATE / TEST_FREEZE — descriptor contract, hover, focus, priority,
placement, accessibility, and automated runtime visual acceptance.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from src.workbench_qml import QML_SOURCE


PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

EXPECTED_DESCRIPTORS: dict[str, tuple[str, str]] = {
    "library.scope.sources": ("Sample Sources", "analysierte Sample-Quellen"),
    "library.scope.all_samples": ("All Samples", "alle Samples im Workspace"),
    "library.scope.collections": ("Collections", "gespeicherte Sample-Sammlungen"),
    "library.scope.favorites": ("Favorites", "markierte Samples"),
    "library.scope.recordings": ("Recordings", "lokale Aufnahmen"),
    "library.add_source": ("Add Source", "lokalen Sample-Ordner hinzufügen"),
}

SCOPE_BUTTON_HINT_IDS: dict[str, str] = {
    "librarySourcesScopeButton": "library.scope.sources",
    "libraryAllSamplesScopeButton": "library.scope.all_samples",
    "libraryCollectionsScopeButton": "library.scope.collections",
    "libraryFavoritesScopeButton": "library.scope.favorites",
    "libraryRecordingsScopeButton": "library.scope.recordings",
}


def _display(label: str, help_text: str) -> str:
    return f"{label} — {help_text}"


def test_context_hint_contract_doc_exists() -> None:
    path = Path("docs/WORKBENCH_CONTEXT_HINT_CONTRACT.md")
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "hover" in text.lower()
    assert "keyboard" in text.lower()
    assert "bottom" in text.lower()
    assert "library.scope.favorites" in text
    assert "library.scope.collections" in text
    assert "library.scope.recordings" in text
    assert "markierte Samples" in text
    assert "gespeicherte Sample-Sammlungen" in text
    assert "lokale Aufnahmen" in text


def test_descriptor_seam_is_shared_and_placement_decoupled() -> None:
    source = QML_SOURCE
    assert 'objectName: "contextHintState"' in source
    assert 'objectName: "contextHintPlacement"' in source
    assert 'objectName: "contextHintDisplay"' in source
    # Content state must not hard-wire placement coordinates into descriptors.
    state_block = source.split('objectName: "contextHintState"', 1)[1].split(
        "Thin aliases for runtime property reads", 1
    )[0]
    assert '"library.scope.favorites"' in state_block
    assert "anchors." not in state_block
    assert re.search(r"\bx:\s*", state_block) is None
    assert re.search(r"\by:\s*", state_block) is None
    # #830: the hint lives in the footer band. Horizontal centering is not the rule.
    place_block = source.split('objectName: "contextHintPlacement"', 1)[1].split(
        "header:", 1
    )[0]
    assert "contextHintDisplay" in place_block
    assert "focus: false" in place_block
    assert "footer:" in source.split('objectName: "contextHintPlacement"', 1)[0][-80:]
    hint_doc = Path("docs/WORKBENCH_CONTEXT_HINT_CONTRACT.md").read_text(encoding="utf-8")
    assert "bottom-center" not in hint_doc.lower()
    assert "right side" in hint_doc or "on the right" in hint_doc


def test_supported_controls_register_stable_distinct_descriptors() -> None:
    source = QML_SOURCE
    for hint_id, (label, help_text) in EXPECTED_DESCRIPTORS.items():
        assert hint_id in source
        assert label in source
        assert help_text in source

    fav_help = EXPECTED_DESCRIPTORS["library.scope.favorites"][1]
    coll_help = EXPECTED_DESCRIPTORS["library.scope.collections"][1]
    rec_help = EXPECTED_DESCRIPTORS["library.scope.recordings"][1]
    assert fav_help != coll_help != rec_help
    assert source.count(fav_help) == 1
    assert source.count(coll_help) == 1
    assert source.count(rec_help) == 1

    for object_name, hint_id in SCOPE_BUTTON_HINT_IDS.items():
        assert f'objectName: "{object_name}"' in source
        assert hint_id in source
        # Accessible names remain required for icon-only controls.
        button_block = source.split(f'objectName: "{object_name}"', 1)[1].split(
            "ToolButton {", 1
        )[0]
        assert "Accessible.name:" in button_block

    assert 'Accessible.name: "Favorites"' in source
    assert 'Accessible.name: "Collections"' in source
    assert 'Accessible.name: "Recordings"' in source
    assert 'objectName: "libraryCatalogScopeButton"' not in source
    # Scope controls must not depend on classic ToolTip for discoverability.
    scope_block = source.split('objectName: "libraryScopeBar"', 1)[1].split(
        'objectName: "elasticHandleAfterLibrary"', 1
    )[0]
    assert "ToolTip." not in scope_block


def test_hint_priority_and_focus_guard_are_encoded() -> None:
    source = QML_SOURCE
    assert "reportHover" in source
    assert "clearHover" in source
    assert "reportFocus" in source
    assert "clearFocus" in source
    assert "reconcile" in source
    # Hover must win over focus in resolve order.
    resolve_match = re.search(
        r"function resolveActiveId\(\)\s*\{(?P<body>.*?)\n\s*\}",
        source,
        flags=re.DOTALL,
    )
    assert resolve_match is not None
    body = resolve_match.group("body")
    hover_pos = body.find("hoveredId")
    focus_pos = body.find("focusedId")
    assert hover_pos >= 0 and focus_pos >= 0
    assert hover_pos < focus_pos
    display_block = source.split('objectName: "contextHintDisplay"', 1)[1].split(
        "}", 1
    )[0]
    assert "activeFocusOnTab: false" in display_block or "focusPolicy" in source


def _open_screen1(tmp_path: Path, *, width: int = 1600, height: int = 900):
    from PySide6.QtQuick import QQuickItem

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
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
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
    window.resize(width, height)
    window.show()
    engine._screen1_interaction_bridge.refreshState()
    engine._screen1_layout_model.syncFromInteraction()
    _settle_qml_frame(app)
    return app, engine, window, view_model, _settle_qml_frame, QQuickItem


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_hint_state_priority_hover_over_focus_over_neutral(tmp_path: Path) -> None:
    app, engine, window, _view_model, settle, QQuickItem = _open_screen1(tmp_path)
    try:
        from PySide6.QtCore import QObject

        state = window.findChild(QObject, "contextHintState")
        assert state is not None

        def set_ids(*, hovered: str | None = None, focused: str | None = None) -> None:
            if hovered is not None:
                state.setProperty("hoveredId", hovered)
            if focused is not None:
                state.setProperty("focusedId", focused)
            app.processEvents()
            settle(app)

        assert state.property("displayText") in ("", None)

        set_ids(focused="library.scope.favorites")
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["library.scope.favorites"]
        )

        set_ids(hovered="library.scope.collections")
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["library.scope.collections"]
        )

        set_ids(hovered="")
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["library.scope.favorites"]
        )

        set_ids(focused="")
        assert state.property("displayText") in ("", None)

        set_ids(hovered="library.scope.favorites")
        set_ids(hovered="library.scope.collections")
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["library.scope.collections"]
        )
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_scope_button_hover_and_focus_drive_shared_hint(tmp_path: Path) -> None:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    app, engine, window, view_model, settle, QQuickItem = _open_screen1(tmp_path)
    try:
        from PySide6.QtCore import QObject

        state = window.findChild(QObject, "contextHintState")
        fav = window.findChild(QQuickItem, "libraryFavoritesScopeButton")
        coll = window.findChild(QQuickItem, "libraryCollectionsScopeButton")
        display = window.findChild(QQuickItem, "contextHintDisplay")
        assert state is not None and fav is not None and coll is not None
        assert display is not None

        def scene_point(item: QQuickItem) -> QPoint:
            center = item.mapToScene(item.boundingRect().center())
            return center.toPoint()

        QTest.mouseMove(window, scene_point(fav))
        settle(app)
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["library.scope.favorites"]
        )
        assert display.property("text") == state.property("displayText")

        QTest.mouseMove(window, scene_point(coll))
        settle(app)
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["library.scope.collections"]
        )

        coll.forceActiveFocus()
        settle(app)
        assert coll.hasActiveFocus()
        # Leave hover while Collections keeps focus → focus hint remains.
        # Move to a neutral chrome area below the scope bar.
        placement = window.findChild(QQuickItem, "contextHintPlacement")
        assert placement is not None
        QTest.mouseMove(window, scene_point(placement))
        settle(app)
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["library.scope.collections"]
        )

        # Hint must never steal focus via normal pointer interaction / tab order.
        assert display.property("activeFocusOnTab") is False
        fav.forceActiveFocus()
        settle(app)
        assert fav.hasActiveFocus()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, scene_point(display))
        settle(app)
        assert not display.hasActiveFocus()

        # Library scope navigation remains operable.
        bar = window.findChild(QQuickItem, "libraryScopeBar")
        assert bar is not None
        bar.setProperty("mode", "favorites")
        engine._screen1_library_bridge.selectLibraryNode("scope:favorites")
        settle(app)
        assert view_model.browser_context == "Favorites"
        bar.setProperty("mode", "collections")
        settle(app)
        coll_list = window.findChild(QQuickItem, "libraryCollectionList")
        assert coll_list is not None and coll_list.isVisible()
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_automated_runtime_visual_acceptance_context_hint(tmp_path: Path) -> None:
    """AUTOMATED_RUNTIME_VISUAL_ACCEPTANCE for #770 context hint."""
    from PySide6.QtCore import QObject, QPoint, Qt
    from PySide6.QtTest import QTest

    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()

    for width, height, tag in ((1600, 900, "1600x900"), (1120, 640, "1120x640")):
        app, engine, window, view_model, settle, QQuickItem = _open_screen1(
            tmp_path / tag, width=width, height=height
        )
        try:
            state = window.findChild(QObject, "contextHintState")
            placement = window.findChild(QQuickItem, "contextHintPlacement")
            display = window.findChild(QQuickItem, "contextHintDisplay")
            fav = window.findChild(QQuickItem, "libraryFavoritesScopeButton")
            coll = window.findChild(QQuickItem, "libraryCollectionsScopeButton")
            browser = window.findChild(QQuickItem, "browserPane")
            bar = window.findChild(QQuickItem, "libraryScopeBar")
            search = window.findChild(QQuickItem, "browserSearch")
            assert state is not None and placement is not None and display is not None
            assert fav is not None and coll is not None and bar is not None
            assert placement.isVisible()
            assert float(placement.height()) > 0
            assert float(placement.height()) <= 28

            # Bottom-aligned within the window content area.
            win_h = float(window.height())
            place_bottom = float(placement.y()) + float(placement.height())
            assert place_bottom >= win_h - float(placement.height()) - 4

            # Horizontally centered display.
            display_center_x = float(display.x()) + float(display.width()) / 2.0
            place_center_x = float(placement.width()) / 2.0
            assert abs(display_center_x - place_center_x) <= 8.0

            # Does not cover Browser actionable area (footer sits below panes).
            if browser is not None and browser.isVisible():
                browser_bottom = float(browser.y()) + float(browser.height())
                assert float(placement.y()) >= browser_bottom - 1.0

            def scene_point(item: QQuickItem) -> QPoint:
                return item.mapToScene(item.boundingRect().center()).toPoint()

            QTest.mouseMove(window, scene_point(fav))
            settle(app)
            assert state.property("displayText") == _display(
                *EXPECTED_DESCRIPTORS["library.scope.favorites"]
            )

            fav.forceActiveFocus()
            settle(app)
            QTest.mouseMove(window, scene_point(coll))
            settle(app)
            assert state.property("displayText") == _display(
                *EXPECTED_DESCRIPTORS["library.scope.collections"]
            )
            # Hover wins over Favorites focus.
            assert state.property("hoveredId") == "library.scope.collections"

            QTest.mouseMove(window, scene_point(placement))
            settle(app)
            # After hover ends, focused Favorites hint returns.
            assert state.property("displayText") == _display(
                *EXPECTED_DESCRIPTORS["library.scope.favorites"]
            )

            display.forceActiveFocus()
            settle(app)
            # forceActiveFocus can target any Item; product contract is tab-order
            # exclusion + pointer interaction must not keep the hint focused.
            assert display.property("activeFocusOnTab") is False
            fav.forceActiveFocus()
            settle(app)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, scene_point(display))
            settle(app)
            assert not display.hasActiveFocus()

            # Library + Browser/Search remain usable.
            assert bar.isVisible() and fav.isVisible() and coll.isVisible()
            if search is not None and search.isVisible():
                search.forceActiveFocus()
                settle(app)
                assert search.hasActiveFocus()
            bar.setProperty("mode", "sources")
            settle(app)
            tree = window.findChild(QQuickItem, "libraryTree")
            assert tree is not None and tree.isVisible()

            grab = window.grabWindow()
            assert not grab.isNull()
            evidence_path = evidence_dir / f"context_hint_{tag}.png"
            assert grab.save(str(evidence_path))
            assert evidence_path.is_file() and evidence_path.stat().st_size > 0
            # No obvious zero-size overflow of the hint strip.
            assert float(placement.width()) >= float(window.width()) - 2
            assert float(display.y()) >= 0
            assert float(display.y()) + float(display.height()) <= float(
                placement.height()
            ) + 1
        finally:
            window.close()
            app.processEvents()
