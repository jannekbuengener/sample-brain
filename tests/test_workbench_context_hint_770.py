"""#770/#1210 Screen-1 context hint seam: priority, coverage, purity.

TEST_GATE / TEST_FREEZE — descriptor contract, hover, focus, selection
fallback, Screen-1 control coverage (#1210), placement, accessibility,
and automated runtime visual acceptance. Historical #770/#885 own the
shared seam; #1210 owns Screen-1 hover/focus routing completion.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_qml import QML_SOURCE, _qml_row, format_selected_sample_context_hint


PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

EXPECTED_DESCRIPTORS: dict[str, tuple[str, str]] = {
    "library.scope.sources": ("YOUR SOURCES", "registrierte Sample-Quellen"),
    "library.scope.all_samples": ("All Samples", "alle Samples im Workspace"),
    "library.scope.collections": ("Collections", "gespeicherte Sample-Sammlungen"),
    "library.scope.favorites": ("Favorites", "markierte Samples"),
    "library.scope.recordings": ("Records", "lokale Aufnahmen"),
    "library.add_source": ("Add Source", "lokalen Sample-Ordner hinzufügen"),
    "library.source": ("Source", "Sample-Quelle auswählen"),
    "library.source_actions": ("Source actions", "Quelle verwalten oder entfernen"),
    "browser.search": ("Search", "Samples im Browser filtern"),
    "browser.sample_row": ("Sample", "Sample auswählen oder Kontextmenü öffnen"),
    "browser.audition": ("Audition", "Sample-Vorschau abspielen"),
    "browser.favorite": ("Favorite", "Sample als Favorit markieren"),
    "browser.resize.waveform": ("Resize waveform", "Waveform-Spalte in der Breite anpassen"),
    "browser.resize.bpm": ("Resize BPM", "BPM-Spalte in der Breite anpassen"),
    "browser.resize.favorite": ("Resize favorite", "Favoriten-Spalte in der Breite anpassen"),
    "browser.resize.key": ("Resize Key", "Key-Spalte in der Breite anpassen"),
    "browser.resize.length": ("Resize length", "Length-Spalte in der Breite anpassen"),
    "browser.resize.type": ("Resize Type", "Type-Spalte in der Breite anpassen"),
    "browser.context.add_to_kit": (
        "Add to Kit",
        "ausgewähltes Sample zum Live Kit hinzufügen",
    ),
    "browser.context.harmonic_matches": (
        "Harmonic Matches",
        "harmonische Treffer für das Sample öffnen",
    ),
    "panel.browser.collapse": ("Collapse Browser", "Browser-Panel einklappen"),
    "panel.browser.expand": ("Expand Browser", "Browser-Panel wieder einblenden"),
    "panel.harmony.collapse": (
        "Collapse Harmonic Matches",
        "Harmonic-Matches-Panel einklappen",
    ),
    "panel.harmony.expand": (
        "Expand Harmonic Matches",
        "Harmonic-Matches-Panel einblenden",
    ),
    "panel.library.reveal": ("Reveal Library", "Library-Panel wieder einblenden"),
}

# #1210 control families that must report through contextHintState (not click-only).
HOVER_WIRED_HINT_IDS: tuple[str, ...] = (
    "library.add_source",
    "library.scope.all_samples",
    "library.scope.collections",
    "library.scope.favorites",
    "library.scope.recordings",
    "library.source",
    "library.source_actions",
    "browser.search",
    "browser.sample_row",
    "browser.audition",
    "browser.favorite",
    "browser.resize.bpm",
    "browser.resize.key",
    "browser.resize.type",
    "browser.resize.waveform",
    "browser.resize.favorite",
    "browser.resize.length",
    "browser.context.add_to_kit",
    "browser.context.harmonic_matches",
    "panel.browser.collapse",
    "panel.browser.expand",
    "panel.harmony.collapse",
    "panel.harmony.expand",
    "panel.library.reveal",
)

SCOPE_BUTTON_HINT_IDS: dict[str, str] = {
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
    assert "HOVER" in text and "FOCUS" in text and "SELECTION" in text
    assert "#1210" in text
    assert "library.scope.favorites" in text
    assert "library.scope.collections" in text
    assert "library.scope.recordings" in text
    assert "browser.search" in text
    assert "browser.resize.bpm" in text
    assert "panel.browser.collapse" in text
    assert "markierte Samples" in text
    assert "gespeicherte Sample-Sammlungen" in text
    assert "lokale Aufnahmen" in text


def test_descriptor_seam_is_shared_and_placement_decoupled() -> None:
    source = QML_SOURCE
    assert 'objectName: "contextHintState"' in source
    assert 'objectName: "programFooterBand"' in source
    assert 'objectName: "contextHintDisplay"' in source
    # Content state must not hard-wire placement coordinates into descriptors.
    state_block = source.split('objectName: "contextHintState"', 1)[1].split(
        "Thin aliases for runtime property reads", 1
    )[0]
    assert '"library.scope.favorites"' in state_block
    assert "anchors." not in state_block
    assert re.search(r"\bx:\s*", state_block) is None
    assert re.search(r"\by:\s*", state_block) is None
    # Footer-context centering: true center layer on full footer width.
    place_block = source.split('objectName: "programFooterBand"', 1)[1].split(
        "header:", 1
    )[0]
    assert "contextHintDisplay" in place_block
    assert 'objectName: "footerContextCenterLayer"' in place_block
    hint_snip = place_block.split("contextHintDisplay", 1)[1].split(
        "Accessible.ignored", 1
    )[0]
    assert (
        "horizontalCenter" in hint_snip
        or "parent.width / 2" in hint_snip
        or "mid -" in hint_snip
    )
    assert "AlignRight" not in hint_snip
    hint_doc = Path("docs/WORKBENCH_CONTEXT_HINT_CONTRACT.md").read_text(encoding="utf-8")
    assert "full footer" in hint_doc.lower()
    assert "geometrically centered" in hint_doc.lower() or "true center" in hint_doc.lower()


def test_supported_controls_register_stable_distinct_descriptors() -> None:
    source = QML_SOURCE
    state_block = source.split('objectName: "contextHintState"', 1)[1].split(
        "Thin aliases for runtime property reads", 1
    )[0]
    for hint_id, (label, help_text) in EXPECTED_DESCRIPTORS.items():
        assert f'"{hint_id}"' in state_block
        assert label in state_block
        assert help_text in state_block
        # Help strings stay unique inside the single descriptor owner.
        assert state_block.count(help_text) == 1

    fav_help = EXPECTED_DESCRIPTORS["library.scope.favorites"][1]
    coll_help = EXPECTED_DESCRIPTORS["library.scope.collections"][1]
    rec_help = EXPECTED_DESCRIPTORS["library.scope.recordings"][1]
    assert fav_help != coll_help != rec_help

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
    assert 'Accessible.name: "Records"' in source
    assert 'objectName: "libraryCatalogScopeButton"' not in source
    # Scope controls must not depend on classic ToolTip for discoverability.
    # libraryScopeBar is a Library-header child; truncate before the content host.
    scope_block = source.split('objectName: "libraryScopeBar"', 1)[1].split(
        'objectName: "libraryContentHost"', 1
    )[0]
    assert "ToolTip." not in scope_block
    assert 'objectName: "libraryFavoritesScopeButton"' in scope_block


def test_1210_screen1_controls_wire_hover_through_single_hint_owner() -> None:
    """#1210: meaningful Screen-1 controls report hover without a second footer authority."""
    source = QML_SOURCE
    assert source.count('objectName: "contextHintState"') == 1
    assert source.count('objectName: "contextHintDisplay"') == 1
    assert "footerHintText" not in source
    assert "contextHintOverride" not in source

    panel_hint_ids = {
        "panel.browser.collapse",
        "panel.browser.expand",
        "panel.harmony.collapse",
        "panel.harmony.expand",
        "panel.library.reveal",
    }
    seam_block = source.split("component PanelDisclosureSeam:", 1)[1].split(
        "title:", 1
    )[0]
    assert "contextHintState.reportHover(hintId)" in seam_block
    assert "contextHintState.clearHover(hintId)" in seam_block
    assert "contextHintState.reportFocus(hintId)" in seam_block
    assert "contextHintState.clearFocus(hintId)" in seam_block

    for hint_id in HOVER_WIRED_HINT_IDS:
        if hint_id in panel_hint_ids:
            assert f'hintId: "{hint_id}"' in source, hint_id
            continue
        assert f'contextHintState.reportHover("{hint_id}")' in source, hint_id
        assert f'contextHintState.clearHover("{hint_id}")' in source, hint_id

    # Focus where keyboard reachability is meaningful.
    for hint_id in (
        "browser.search",
        "browser.resize.bpm",
        "library.add_source",
    ):
        assert f'contextHintState.reportFocus("{hint_id}")' in source, hint_id
        assert f'contextHintState.clearFocus("{hint_id}")' in source, hint_id
    assert 'hintId: "panel.browser.collapse"' in source

    # Virtualized Browser safety + popup close must clear owned hover IDs.
    assert "ListView.onPooled" in source or "onPooled:" in source
    menu_block = source.split('objectName: "sampleContextMenu"', 1)[1].split(
        'objectName: "browserCollapseHandle"', 1
    )[0]
    assert 'clearHover("browser.context.add_to_kit")' in menu_block
    assert 'clearHover("browser.context.harmonic_matches")' in menu_block
    assert "syncContextActionFocusHint" in menu_block
    assert "onFocusedActionChanged" in menu_block
    assert "onVisibleChanged" in seam_block
    assert "clearFocus(hintId)" in seam_block

    # #1204 / #1211 interaction authority stays intact while hints are attached.
    assert "function resizeColumn(" in source
    assert 'browserPane.resizeColumn("bpm"' in source
    assert "component PanelDisclosureSeam" in source
    assert 'objectName: "browserCollapseHandle"' in source
    assert "activateAction" in source.split('objectName: "browserCollapseHandle"', 1)[1][
        :500
    ]


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


def _sample_row(
    *,
    name: str = "kick_01.wav",
    bpm: float | None = 128.0,
    key: str | None = "Am",
    pred_type: str | None = "Kick",
) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=name,
        path=f"/synthetic/{name}",
        bpm=bpm,
        key=key,
        key_conf=0.9 if key else None,
        loudness=None,
        brightness=None,
        sample_class="one_shot",
        pred_type=pred_type,
        status="ok",
        details={},
    )


def _open_screen1(
    tmp_path: Path,
    *,
    width: int = 1600,
    height: int = 900,
    sample_rows: tuple[WorkbenchRow, ...] = (),
    selected_browser_index: int = -1,
):
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
    projected = tuple(_qml_row(row) for row in sample_rows)
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=projected,
        selected_browser_index=selected_browser_index,
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
    if sample_rows:
        # Keep the explicit selection after clean-start materialization.
        view_model.set_browser_state(
            rows=sample_rows,
            selected_index=selected_browser_index,
            browser_context="All Samples",
            error=None,
        )
    from PySide6.QtGui import QGuiApplication

    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    QGuiApplication.styleHints().setUseHoverEffects(True)
    window.resize(width, height)
    window.show()
    window.requestActivate()
    engine._screen1_interaction_bridge.refreshState()
    engine._screen1_screen_model.refresh()
    engine._screen1_screen_model.refresh_browser_rows()
    engine._screen1_layout_model.syncFromInteraction()
    _settle_qml_frame(app)
    return app, engine, window, view_model, _settle_qml_frame, QQuickItem


def _enable_control_hover(item) -> None:
    """Offscreen/xvfb QPA may leave Controls without hover acceptance."""
    item.setAcceptHoverEvents(True)
    if item.property("hoverEnabled") is not None:
        item.setProperty("hoverEnabled", True)


def _find_named_item(root, object_name: str):
    """ListView delegates are often invisible to QObject.findChild; walk visuals."""
    if root is None:
        return None
    if root.objectName() == object_name:
        return root
    for child in root.childItems():
        found = _find_named_item(child, object_name)
        if found is not None:
            return found
    return None


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
        _enable_control_hover(fav)
        _enable_control_hover(coll)

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
        placement = window.findChild(QQuickItem, "programFooterBand")
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
        engine._screen1_library_bridge.selectLibraryNode("scope:favorites")
        settle(app)
        assert view_model.browser_context == "Favorites"
        assert engine._screen1_library_bridge.activeLibrarySection == "favorites"
        engine._screen1_library_bridge.showLibrarySection("collections")
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
            placement = window.findChild(QQuickItem, "programFooterBand")
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
            assert float(placement.height()) <= 48
            _enable_control_hover(fav)
            _enable_control_hover(coll)

            # Bottom-aligned within the window content area.
            win_h = float(window.height())
            place_bottom = float(placement.y()) + float(placement.height())
            assert place_bottom >= win_h - float(placement.height()) - 4

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

            # Hint is geometrically centered on the full footer width.
            display_center = float(display.x()) + float(display.width()) / 2.0
            place_mid = float(placement.width()) / 2.0
            assert abs(display_center - place_mid) <= 2.0
            left_right = float(bar.x()) + float(bar.width())
            assert float(display.x()) >= left_right - 1.0

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


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_1210_runtime_hover_focus_selection_priority_and_purity(tmp_path: Path) -> None:
    """#1210: Hover > Focus > Selection > Neutral; hover never mutates product state."""
    from PySide6.QtCore import QObject, QPoint
    from PySide6.QtTest import QTest

    rows = (
        _sample_row(name="kick_01.wav", bpm=128.0, key="Am", pred_type="Kick"),
        _sample_row(name="snare_02.wav", bpm=130.0, key="Cm", pred_type="Snare"),
    )
    expected_selection = format_selected_sample_context_hint(_qml_row(rows[0]))
    app, engine, window, view_model, settle, QQuickItem = _open_screen1(
        tmp_path,
        sample_rows=rows,
        selected_browser_index=0,
    )
    try:
        state = window.findChild(QObject, "contextHintState")
        search = window.findChild(QQuickItem, "browserSearch")
        browser_list = window.findChild(QQuickItem, "browserList")
        resize_bpm = window.findChild(QQuickItem, "browserColumnResize_bpm")
        collapse = window.findChild(QQuickItem, "browserCollapseHandle")
        add_source = window.findChild(QQuickItem, "libraryAddSourceButton")
        footer = window.findChild(QQuickItem, "programFooterBand")
        assert state and search and browser_list and resize_bpm
        assert collapse and add_source and footer
        settle(app)
        content = browser_list.property("contentItem")
        fav_btn = _find_named_item(content, "browserFavoriteButton")
        waveform = _find_named_item(content, "browserWaveformSurface")
        assert fav_btn and waveform

        def scene_point(item: QQuickItem) -> QPoint:
            return item.mapToScene(item.boundingRect().center()).toPoint()

        _enable_control_hover(search)
        _enable_control_hover(fav_btn)
        _enable_control_hover(waveform)
        _enable_control_hover(resize_bpm)
        _enable_control_hover(collapse)
        _enable_control_hover(add_source)

        # Selection fallback before pointer work.
        assert state.property("displayText") == expected_selection

        search_before = str(search.property("text") or "")
        fav_before = bool(view_model.browser_rows[0].is_favorite)
        bpm_w_before = int(resize_bpm.parentItem().width()) if resize_bpm.parentItem() else -1
        collapsed_before = bool(engine._screen1_interaction_bridge.browserCollapsed)
        preview_before = bool(engine._screen1_interaction_bridge.previewActive)

        # Focus Search → Focus hint
        search.forceActiveFocus()
        settle(app)
        assert state.property("displayText") == _display(*EXPECTED_DESCRIPTORS["browser.search"])

        # Hover Favorite while Search focused → Hover wins
        QTest.mouseMove(window, scene_point(fav_btn))
        settle(app)
        assert state.property("displayText") == _display(*EXPECTED_DESCRIPTORS["browser.favorite"])
        assert state.property("focusedId") == "browser.search"

        # Leave Favorite → Focus Search restored
        QTest.mouseMove(window, scene_point(footer))
        settle(app)
        assert state.property("displayText") == _display(*EXPECTED_DESCRIPTORS["browser.search"])

        # Clear focus → Selection restored
        state.setProperty("focusedId", "")
        search.setFocus(False)
        footer.forceActiveFocus()
        settle(app)
        assert state.property("displayText") == expected_selection

        # Browser search / resize / disclosure / audition / add-source hover purity
        for item, hint_id in (
            (search, "browser.search"),
            (resize_bpm, "browser.resize.bpm"),
            (collapse, "panel.browser.collapse"),
            (waveform, "browser.audition"),
            (add_source, "library.add_source"),
        ):
            QTest.mouseMove(window, scene_point(item))
            settle(app)
            assert state.property("displayText") == _display(*EXPECTED_DESCRIPTORS[hint_id]), hint_id

        QTest.mouseMove(window, scene_point(footer))
        settle(app)
        assert state.property("displayText") == expected_selection

        # Rapid A→B→C ends at C
        QTest.mouseMove(window, scene_point(search))
        settle(app)
        QTest.mouseMove(window, scene_point(resize_bpm))
        settle(app)
        QTest.mouseMove(window, scene_point(collapse))
        settle(app)
        assert state.property("hoveredId") == "panel.browser.collapse"
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["panel.browser.collapse"]
        )

        QTest.mouseMove(window, scene_point(footer))
        settle(app)

        # No product mutation from the hover sweep.
        assert str(search.property("text") or "") == search_before
        assert bool(view_model.browser_rows[0].is_favorite) == fav_before
        assert view_model.selected_browser_index == 0
        assert bool(engine._screen1_interaction_bridge.browserCollapsed) == collapsed_before
        assert bool(engine._screen1_interaction_bridge.previewActive) == preview_before
        if bpm_w_before >= 0 and resize_bpm.parentItem() is not None:
            assert int(resize_bpm.parentItem().width()) == bpm_w_before

        # Footer remains centered / unboxed.
        display = window.findChild(QQuickItem, "contextHintDisplay")
        assert display is not None
        mid = float(footer.width()) / 2.0
        assert abs(float(display.x()) + float(display.width()) / 2.0 - mid) <= 2.0
        footer_src = QML_SOURCE.split("footer:", 1)[1].split("header:", 1)[0]
        hint_snip = footer_src.split('objectName: "contextHintDisplay"', 1)[1].split(
            "Accessible.ignored", 1
        )[0]
        assert "Rectangle" not in hint_snip or "background" not in hint_snip.lower()
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_1210_runtime_context_menu_hover_does_not_mutate_target(tmp_path: Path) -> None:
    from PySide6.QtCore import QObject

    rows = (_sample_row(name="kick_01.wav"),)
    app, engine, window, view_model, settle, QQuickItem = _open_screen1(
        tmp_path,
        sample_rows=rows,
        selected_browser_index=0,
    )
    try:
        state = window.findChild(QObject, "contextHintState")
        menu = window.findChild(QObject, "sampleContextMenu")
        assert state is not None and menu is not None

        selected_before = view_model.selected_browser_index
        engine._screen1_interaction_bridge.openSampleContext(0)
        settle(app)

        # Menu item hover is presentation-only: selection/context target stays put.
        state.setProperty("hoveredId", "browser.context.harmonic_matches")
        settle(app)
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["browser.context.harmonic_matches"]
        )
        assert view_model.selected_browser_index == selected_before

        state.setProperty("hoveredId", "")
        engine._screen1_interaction_bridge.closeSampleContext()
        settle(app)
        assert view_model.selected_browser_index == selected_before
        assert state.property("hoveredId") in ("", None)
    finally:
        window.close()
        app.processEvents()
