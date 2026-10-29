"""#1211 runtime geometry: independent column widths + pointer-direction.

Structural #1211 contracts live in test_workbench_qml_browser_chrome.py.
This module proves live QQuickItem boundary geometry under resizeColumn.
"""

from __future__ import annotations

import importlib.util

import pytest

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

pytestmark = pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")


def _edge_x(item) -> float:
    return float(item.mapToItem(None, item.width(), 0.0).x())


def _invoke_resize(browser, role: str, delta: float) -> None:
    from PySide6.QtCore import Q_ARG, QMetaObject, Qt

    ok = QMetaObject.invokeMethod(
        browser,
        "resizeColumn",
        Qt.DirectConnection,
        Q_ARG("QVariant", role),
        Q_ARG("QVariant", delta),
    )
    assert ok, f"resizeColumn({role!r}, {delta}) invoke failed"


@pytest.fixture
def browser_resize_runtime():
    from PySide6.QtQuick import QQuickItem

    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml import Screen1QmlInteractionAdapter, _qml_engine, _settle_qml_frame
    from src.workbench_qml_spike import build_qml_view_model_from_fixture
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.set_library_revealed(True)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    adapter.harmonic_match_open = False
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.setWidth(1600)
    window.setHeight(900)
    window.show()
    _settle_qml_frame(app)
    browser = window.findChild(QQuickItem, "browserPane")
    assert browser is not None
    assert not bool(browser.property("browserNarrowColumns"))

    def settle() -> None:
        app.processEvents()
        _settle_qml_frame(app)

    yield app, window, browser, settle
    window.close()
    app.processEvents()


def test_runtime_independent_bpm_key_type_widths_and_direction(browser_resize_runtime):
    """+Δ grows only the grabbed role; BPM right edge is not mirrored."""
    from PySide6.QtQuick import QQuickItem

    _app, window, browser, settle = browser_resize_runtime
    bpm = window.findChild(QQuickItem, "browserColumnHeader_bpm")
    key = window.findChild(QQuickItem, "browserColumnHeader_key")
    typ = window.findChild(QQuickItem, "browserColumnHeader_type")
    wf_handle = window.findChild(QQuickItem, "browserColumnResize_waveform")
    assert all(x is not None for x in (bpm, key, typ, wf_handle))
    wf = wf_handle.parentItem()

    settle()
    before = {
        "bpm_w": float(bpm.width()),
        "key_w": float(key.width()),
        "type_w": float(typ.width()),
        "bpm_right": _edge_x(bpm),
        "key_right": _edge_x(key),
        "type_right": _edge_x(typ),
        "wf_right": _edge_x(wf),
        "bpm_user": browser.property("bpmUserWidth"),
        "key_user": browser.property("keyUserWidth"),
        "type_user": browser.property("typeUserWidth"),
        "fav_user": browser.property("favoriteUserWidth"),
        "len_user": browser.property("lengthUserWidth"),
    }

    _invoke_resize(browser, "bpm", 20)
    settle()
    assert float(bpm.width()) == pytest.approx(before["bpm_w"] + 20, abs=1.0)
    assert float(key.width()) == pytest.approx(before["key_w"], abs=1.0)
    assert float(typ.width()) == pytest.approx(before["type_w"], abs=1.0)
    # Decoupled BPM: grabbed right edge must not move opposite the pointer.
    assert _edge_x(bpm) - before["bpm_right"] >= -0.5
    assert browser.property("keyUserWidth") == before["key_user"]
    assert browser.property("typeUserWidth") == before["type_user"]
    assert browser.property("favoriteUserWidth") == before["fav_user"]
    assert browser.property("lengthUserWidth") == before["len_user"]

    mid_bpm_w = float(bpm.width())
    bpm_user_after_bpm = browser.property("bpmUserWidth")
    mid_key_right = _edge_x(key)
    _invoke_resize(browser, "key", 12)
    settle()
    assert float(key.width()) == pytest.approx(before["key_w"] + 12, abs=1.0)
    assert float(bpm.width()) == pytest.approx(mid_bpm_w, abs=1.0)
    assert _edge_x(key) - mid_key_right >= -0.5
    assert browser.property("bpmUserWidth") == bpm_user_after_bpm
    assert browser.property("typeUserWidth") == before["type_user"]

    mid_type_w = float(typ.width())
    bpm_user_after_key = browser.property("bpmUserWidth")
    key_user_after_key = browser.property("keyUserWidth")
    _invoke_resize(browser, "type", 8)
    settle()
    assert float(typ.width()) == pytest.approx(mid_type_w + 8, abs=1.0)
    assert browser.property("bpmUserWidth") == bpm_user_after_key
    assert browser.property("keyUserWidth") == key_user_after_key
    assert browser.property("favoriteUserWidth") == before["fav_user"]
    assert browser.property("lengthUserWidth") == before["len_user"]

    # Waveform (left of Name absorber) right edge tracks +X.
    wf_before = _edge_x(wf)
    _invoke_resize(browser, "waveform", 16)
    settle()
    assert _edge_x(wf) - wf_before == pytest.approx(16.0, abs=1.0)

    # Repeated +/− without clamp returns to the pre-cycle width.
    cycle_w = float(bpm.width())
    _invoke_resize(browser, "bpm", 10)
    settle()
    _invoke_resize(browser, "bpm", -10)
    settle()
    assert float(bpm.width()) == pytest.approx(cycle_w, abs=1.0)


def test_runtime_clamp_does_not_mutate_foreign_user_widths(browser_resize_runtime):
    _app, _window, browser, settle = browser_resize_runtime
    _invoke_resize(browser, "key", 20)
    settle()
    key_user = browser.property("keyUserWidth")
    fav_user = browser.property("favoriteUserWidth")
    # Push BPM to max; foreign overrides must stay put.
    for _ in range(20):
        _invoke_resize(browser, "bpm", 40)
    settle()
    assert int(browser.property("effectiveBrowserBpmColumnWidth")) == 96
    assert browser.property("keyUserWidth") == key_user
    assert browser.property("favoriteUserWidth") == fav_user
