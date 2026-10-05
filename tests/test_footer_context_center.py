"""Footer context info centering + Hover > Selection priority.

TEST_GATE / TEST_FREEZE — geometric center on full footer width, priority,
stability/non-overlap, and chrome regressions (#770/#837/#880).
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
    "library.scope.sources": ("Sample Sources", "analysierte Sample-Quellen"),
    "library.scope.all_samples": ("All Samples", "alle Samples im Workspace"),
    "library.scope.collections": ("Collections", "gespeicherte Sample-Sammlungen"),
    "library.scope.favorites": ("Favorites", "markierte Samples"),
    "library.scope.recordings": ("Recordings", "lokale Aufnahmen"),
    "library.add_source": ("Add Source", "lokalen Sample-Ordner hinzufügen"),
}


def _display(label: str, help_text: str) -> str:
    return f"{label} — {help_text}"


def _footer_block() -> str:
    return QML_SOURCE.split("footer:", 1)[1].split("header:", 1)[0]


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


def test_contract_docs_require_full_footer_centering_and_priority() -> None:
    hint = Path("docs/WORKBENCH_CONTEXT_HINT_CONTRACT.md").read_text(encoding="utf-8")
    chrome = Path("docs/PROGRAM_CHROME_CONTRACT.md").read_text(encoding="utf-8")
    assert "full footer width" in hint.lower() or "full footer midpoint" in hint.lower()
    assert "geometrically centered" in hint.lower() or "true center" in hint.lower()
    assert "RowLayout" in hint
    assert "HOVER" in hint and "SELECTION" in hint and "DEFAULT" in hint
    assert "selectedBrowserIndex" in hint or "browser sample selection" in hint.lower()
    assert "·" in hint  # sample selection compact separator
    assert "true center" in chrome.lower() or "full-width center" in chrome.lower()
    assert "Pattern" in hint or "Pattern/Bars/Song" in hint


def test_selected_sample_context_hint_formats_existing_projection_fields() -> None:
    projected = _qml_row(
        _sample_row(name="pad_soft.wav", bpm=140.0, key="Fm", pred_type="Pad")
    )
    assert format_selected_sample_context_hint(projected) == "pad_soft.wav · 140 · Fm · Pad"
    assert format_selected_sample_context_hint(None) == ""
    missing = _qml_row(_sample_row(name="raw.wav", bpm=None, key=None, pred_type=None))
    assert format_selected_sample_context_hint(missing) == "raw.wav · — · — · —"


def test_qml_encodes_true_center_layer_not_rowlayout_leftover() -> None:
    footer = _footer_block()
    assert 'objectName: "programFooterBand"' in footer
    assert 'objectName: "libraryScopeBar"' in footer
    assert 'objectName: "footerContextCenterLayer"' in footer
    assert 'objectName: "contextHintDisplay"' in footer
    assert 'objectName: "footerStatusZone"' in footer

    hint_block = footer.split('objectName: "contextHintDisplay"', 1)[1]
    # Close at the Label's end — look for elide/focus guard markers then outer close.
    hint_snip = hint_block.split("Accessible.ignored", 1)[0]
    assert "horizontalCenter" in hint_snip or "parent.width / 2" in hint_snip or "mid -" in hint_snip
    assert "AlignRight" not in hint_snip
    assert "Layout.fillWidth" not in hint_snip

    # Center layer must be a sibling overlay, not a RowLayout stretch child.
    center_owner = footer.split('objectName: "footerContextCenterLayer"', 1)[0]
    # The center layer declaration should not sit inside a RowLayout fill chain
    # after a fillWidth spacer as the sole positioning strategy.
    assert "Item { Layout.fillWidth: true }" not in footer.split(
        'objectName: "contextHintDisplay"', 1
    )[0][-200:]


def test_priority_resolve_order_is_hover_then_selection_then_empty() -> None:
    resolve_match = re.search(
        r"function resolveActiveId\(\)\s*\{(?P<body>.*?)\n\s*\}",
        QML_SOURCE,
        flags=re.DOTALL,
    )
    assert resolve_match is not None
    body = resolve_match.group("body")
    hover_pos = body.find("hoveredId")
    selection_pos = body.find("focusedId")
    assert hover_pos >= 0 and selection_pos >= 0
    assert hover_pos < selection_pos
    assert 'property string hoveredId' in QML_SOURCE
    assert 'property string focusedId' in QML_SOURCE
    # Sample selection is a display fallback after control hover/focus, not a
    # parallel selection owner — must reuse selectedSampleContextHint / index.
    state_block = QML_SOURCE.split('objectName: "contextHintState"', 1)[1].split(
        "onFocusedIdChanged", 1
    )[0]
    assert "selectedSampleContextHint" in state_block or "selectedSampleContextHint" in QML_SOURCE
    display_bind = QML_SOURCE.split('objectName: "contextHintDisplay"', 1)[1].split(
        "Accessible.ignored", 1
    )[0]
    assert "contextHintState.displayText" in display_bind


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


def _center_x(item) -> float:
    return float(item.x()) + float(item.width()) / 2.0


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
@pytest.mark.parametrize("size", [(1600, 900), (1120, 640)])
def test_runtime_context_text_centered_on_full_footer_width(tmp_path: Path, size) -> None:
    from PySide6.QtCore import QObject

    width, height = size
    app, _engine, window, _vm, settle, QQuickItem = _open_screen1(
        tmp_path / f"{width}x{height}", width=width, height=height
    )
    try:
        footer = window.findChild(QQuickItem, "programFooterBand")
        display = window.findChild(QQuickItem, "contextHintDisplay")
        state = window.findChild(QObject, "contextHintState")
        left = window.findChild(QQuickItem, "libraryScopeBar")
        right = window.findChild(QQuickItem, "footerStatusZone")
        assert footer and display and state and left and right

        state.setProperty("focusedId", "library.scope.favorites")
        settle(app)
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["library.scope.favorites"]
        )
        settle(app)

        mid = float(footer.width()) / 2.0
        assert abs(_center_x(display) - mid) <= 2.0

        # Left/right zones must not pull the optical center.
        left_right = float(left.x()) + float(left.width())
        right_left = float(right.x())
        assert left_right < mid - 4.0
        assert right_left > mid + 4.0 or float(right.width()) <= 2.0
        assert float(display.x()) >= left_right - 1.0
        assert float(display.x()) + float(display.width()) <= right_left + 1.0 or float(
            right.width()
        ) <= 2.0
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_left_right_width_changes_do_not_shift_center(tmp_path: Path) -> None:
    from PySide6.QtCore import QObject

    app, _engine, window, _vm, settle, QQuickItem = _open_screen1(tmp_path)
    try:
        footer = window.findChild(QQuickItem, "programFooterBand")
        display = window.findChild(QQuickItem, "contextHintDisplay")
        state = window.findChild(QObject, "contextHintState")
        left = window.findChild(QQuickItem, "libraryScopeBar")
        assert footer and display and state and left

        state.setProperty("hoveredId", "library.scope.collections")
        settle(app)
        mid = float(footer.width()) / 2.0
        center_before = _center_x(display)
        assert abs(center_before - mid) <= 2.0

        # Simulate asymmetric left growth without changing footer midpoint.
        left.setWidth(float(left.width()) + 48.0)
        settle(app)
        center_after = _center_x(display)
        assert abs(center_after - mid) <= 2.0
        assert abs(center_after - center_before) <= 2.0
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_priority_hover_over_selection_restore_and_default(tmp_path: Path) -> None:
    from PySide6.QtCore import QObject
    from PySide6.QtTest import QTest

    app, _engine, window, _vm, settle, QQuickItem = _open_screen1(tmp_path)
    try:
        state = window.findChild(QObject, "contextHintState")
        fav = window.findChild(QQuickItem, "libraryFavoritesScopeButton")
        coll = window.findChild(QQuickItem, "libraryCollectionsScopeButton")
        display = window.findChild(QQuickItem, "contextHintDisplay")
        footer = window.findChild(QQuickItem, "programFooterBand")
        assert state and fav and coll and display and footer
        _enable_control_hover(fav)
        _enable_control_hover(coll)

        assert state.property("displayText") in ("", None)

        fav.forceActiveFocus()
        settle(app)
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["library.scope.favorites"]
        )

        def scene_point(item):
            return item.mapToScene(item.boundingRect().center()).toPoint()

        QTest.mouseMove(window, scene_point(coll))
        settle(app)
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["library.scope.collections"]
        )
        # Selection identity must survive temporary hover.
        assert state.property("focusedId") == "library.scope.favorites"

        QTest.mouseMove(window, scene_point(footer))
        settle(app)
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["library.scope.favorites"]
        )

        state.setProperty("focusedId", "")
        settle(app)
        assert state.property("displayText") in ("", None)
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_sample_selection_hover_override_restore_and_clear(
    tmp_path: Path,
) -> None:
    """Owner finding: selected sample must drive footer center when not hovering."""
    from PySide6.QtCore import QObject
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
        display = window.findChild(QQuickItem, "contextHintDisplay")
        footer = window.findChild(QQuickItem, "programFooterBand")
        coll = window.findChild(QQuickItem, "libraryCollectionsScopeButton")
        assert state and display and footer and coll
        _enable_control_hover(coll)

        # 1) Sample selected + no hover → Selection-Context visible
        assert view_model.selected_browser_index == 0
        assert state.property("hoveredId") in ("", None)
        assert state.property("focusedId") in ("", None)
        assert state.property("displayText") == expected_selection
        assert display.property("text") == expected_selection

        # 2) Sample selected + hover on another contextual element → Hover
        def scene_point(item):
            return item.mapToScene(item.boundingRect().center()).toPoint()

        QTest.mouseMove(window, scene_point(coll))
        settle(app)
        assert state.property("displayText") == _display(
            *EXPECTED_DESCRIPTORS["library.scope.collections"]
        )
        # Existing browser selection identity must survive temporary hover.
        assert view_model.selected_browser_index == 0

        # 3) Hover ends → Selection-Context returns
        QTest.mouseMove(window, scene_point(footer))
        settle(app)
        assert state.property("displayText") == expected_selection
        assert display.property("text") == expected_selection

        # 4) Selection cleared + no hover → Default/empty
        view_model.selected_browser_index = -1
        engine._screen1_screen_data_bridge.refresh()
        settle(app)
        assert state.property("displayText") in ("", None)
        assert display.property("text") in ("", None)
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_long_sample_selection_elides_without_overlap_or_jump(
    tmp_path: Path,
) -> None:
    from PySide6.QtCore import QObject

    long_name = "very_long_sample_name_for_footer_elide_" + ("x" * 80) + ".wav"
    rows = (_sample_row(name=long_name, bpm=128.0, key="Am", pred_type="Kick"),)
    app, _engine, window, _vm, settle, QQuickItem = _open_screen1(
        tmp_path / "long",
        width=1120,
        height=640,
        sample_rows=rows,
        selected_browser_index=0,
    )
    try:
        footer = window.findChild(QQuickItem, "programFooterBand")
        display = window.findChild(QQuickItem, "contextHintDisplay")
        state = window.findChild(QObject, "contextHintState")
        left = window.findChild(QQuickItem, "libraryScopeBar")
        right = window.findChild(QQuickItem, "footerStatusZone")
        assert footer and display and state and left and right

        footer_h = float(footer.height())
        settle(app)
        assert long_name.split(".")[0][:20] in str(state.property("displayText") or "")
        assert float(footer.height()) == footer_h
        left_right = float(left.x()) + float(left.width())
        right_left = (
            float(right.x())
            if float(right.width()) > 2.0
            else float(footer.width()) - 8.0
        )
        assert float(display.x()) >= left_right - 1.0
        assert float(display.x()) + float(display.width()) <= right_left + 1.0
        assert abs(_center_x(display) - float(footer.width()) / 2.0) <= 2.0
    finally:
        window.close()
        app.processEvents()


def test_source_long_text_elide_and_non_overlap_guards() -> None:
    footer = _footer_block()
    hint = footer.split('objectName: "contextHintDisplay"', 1)[1].split(
        "Accessible.ignored", 1
    )[0]
    assert "ElideRight" in hint
    assert "maxHalf" in hint or "Math.min" in hint
    assert "implicitWidth" in hint


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_hint_does_not_overlap_left_right_or_jump_footer_height(
    tmp_path: Path,
) -> None:
    from PySide6.QtCore import QObject

    app, _engine, window, _vm, settle, QQuickItem = _open_screen1(tmp_path)
    try:
        footer = window.findChild(QQuickItem, "programFooterBand")
        display = window.findChild(QQuickItem, "contextHintDisplay")
        state = window.findChild(QObject, "contextHintState")
        left = window.findChild(QQuickItem, "libraryScopeBar")
        right = window.findChild(QQuickItem, "footerStatusZone")
        assert footer and display and state and left and right

        footer_h_before = float(footer.height())
        assert state.property("displayText") in ("", None)

        state.setProperty("hoveredId", "library.scope.favorites")
        settle(app)
        assert float(footer.height()) == footer_h_before

        left_right = float(left.x()) + float(left.width())
        right_left = (
            float(right.x())
            if float(right.width()) > 2.0
            else float(footer.width()) - 8.0
        )
        assert float(display.x()) >= left_right - 1.0
        assert float(display.x()) + float(display.width()) <= right_left + 1.0
        assert abs(_center_x(display) - float(footer.width()) / 2.0) <= 2.0

        state.setProperty("hoveredId", "")
        settle(app)
        assert float(footer.height()) == footer_h_before
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_regressions_scope_nav_transport_slim_chrome(tmp_path: Path) -> None:
    app, engine, window, view_model, settle, QQuickItem = _open_screen1(tmp_path)
    try:
        footer = window.findChild(QQuickItem, "programFooterBand")
        header = window.findChild(QQuickItem, "screen1Header")
        bar = window.findChild(QQuickItem, "libraryScopeBar")
        fav = window.findChild(QQuickItem, "libraryFavoritesScopeButton")
        nav = window.findChild(QQuickItem, "headerNavZone")
        transport = window.findChild(QQuickItem, "headerTransportZone")
        assert footer and header and bar and fav and nav and transport

        # #880 slim chrome corridors
        assert 26.0 <= float(header.height()) <= 34.0
        assert 18.0 <= float(footer.height()) <= 26.0

        bar.setProperty("mode", "favorites")
        engine._screen1_library_bridge.selectLibraryNode("scope:favorites")
        settle(app)
        assert view_model.browser_context == "Favorites"
        assert fav.isVisible() and bar.isVisible()
        assert nav.isVisible() and transport.isVisible()

        # Pattern/Bars/Song must remain out of this footer slice.
        assert window.findChild(QQuickItem, "patternBarsSongRow") is None
        source = QML_SOURCE
        footer_src = _footer_block()
        assert "BARS" not in footer_src
        assert "Song" not in footer_src
        assert 'objectName: "patternBarsSongRow"' not in source or "patternBarsSongRow" not in footer_src
    finally:
        window.close()
        app.processEvents()
