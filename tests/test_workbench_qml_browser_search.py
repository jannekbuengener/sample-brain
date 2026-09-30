"""#758 Screen-1 browserSearch must filter the Sample Browser."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_qml import QML_SOURCE, Screen1QmlViewModel

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


def _row(name: str, *, key: str) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=name,
        path=f"/tmp/{name}.wav",
        bpm=120.0,
        key=key,
        key_conf=0.9,
        loudness=None,
        brightness=None,
        sample_class="one_shot",
        pred_type="Kick",
        status="ok",
        details={},
    )


def test_qml_source_wires_browser_search_to_interaction() -> None:
    assert 'objectName: "browserSearch"' in QML_SOURCE
    assert "onTextChanged: window.interaction.setBrowserSearch(text)" in QML_SOURCE


def test_view_model_browser_search_filters_without_qt() -> None:
    vm = Screen1QmlViewModel.baseline("screen1-default-3panel")
    vm.set_browser_state(
        rows=(
            _row("alpha kick", key="Cmaj"),
            _row("beta snare", key="Amin"),
            _row("gamma pulse", key="Fmaj"),
        ),
        selected_index=0,
        browser_context="All Samples",
        error=None,
    )
    assert len(vm.browser_rows) == 3
    vm.set_browser_search_query("alpha")
    assert len(vm.browser_rows) == 1
    assert vm.browser_rows[0].source_row.display_name == "alpha kick"
    assert vm.selected_browser_index == 0
    vm.set_browser_search_query("")
    assert len(vm.browser_rows) == 3


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_browser_search_filters_and_clears_live(tmp_path: Path) -> None:
    from PySide6.QtCore import QObject
    from PySide6.QtQuick import QQuickItem

    from tests.test_workbench_qml_producer_flow_e2e import (
        _boot_screen1,
        _build_representative_synthetic_bank,
        _shutdown_engine,
        _wait_for_analysis,
    )

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

        bridge.setBrowserSearch("")
        app.processEvents()
        assert len(view_model.browser_rows) == before
    finally:
        _shutdown_engine(app, engine, window)
