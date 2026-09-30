"""#758 Screen-1 browserSearch must filter the Sample Browser."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QObject
from PySide6.QtQuick import QQuickItem

from src.workbench_qml import QML_SOURCE
from tests.test_workbench_qml_producer_flow_e2e import (
    _boot_screen1,
    _build_representative_synthetic_bank,
    _shutdown_engine,
    _wait_for_analysis,
)

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

pytestmark = pytest.mark.skipif(
    not PY_SIDE6_AVAILABLE,
    reason="PySide6 ist nicht installiert",
)


def test_qml_source_wires_browser_search_to_interaction() -> None:
    assert 'objectName: "browserSearch"' in QML_SOURCE
    assert "onTextChanged: window.interaction.setBrowserSearch(text)" in QML_SOURCE


def test_browser_search_filters_and_clears_live(tmp_path: Path) -> None:
    db = tmp_path / "library.db"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    source = tmp_path / "bank"
    _build_representative_synthetic_bank(source)

    _mode, composition, view_model, app, engine, window = _boot_screen1(
        db=db,
        state_dir=state_dir,
    )
    library_bridge = engine._screen1_library_bridge
    coordinator = engine._screen1_analysis_coordinator
    bridge = engine.rootContext().contextProperty("interactionModel")

    try:
        library_bridge.registerSourceUrl(str(source))
        app.processEvents()
        folder_id = view_model.analysis_folder_id
        assert folder_id is not None
        assert _wait_for_analysis(app, coordinator, folder_id, view_model)
        app.processEvents()
        assert composition.has_active_source is True
        before = len(view_model.browser_rows)
        assert before >= 11

        search = window.findChild(QObject, "browserSearch")
        browser = window.findChild(QQuickItem, "browserPane")
        assert search is not None
        assert browser is not None and browser.isVisible()

        search.setProperty("text", "cmaj")
        app.processEvents()
        time.sleep(0.05)
        app.processEvents()
        assert str(search.property("text")) == "cmaj"
        assert len(view_model.browser_rows) == 1
        assert "cmaj" in view_model.browser_rows[0].source_row.display_name.casefold()

        # Direct Slot path (same as QML onTextChanged) must clear back to full scope.
        bridge.setBrowserSearch("")
        app.processEvents()
        assert len(view_model.browser_rows) == before
    finally:
        _shutdown_engine(app, engine, window)
