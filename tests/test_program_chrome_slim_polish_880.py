"""#880 slim premium program chrome — runtime geometry contract (TEST_FREEZE).

Chosen implementation values (e.g. ~36 / ~28) are design targets, not
screenshot-measured pixel truth. Gates use corridors vs the #831 mass baseline.
"""

from __future__ import annotations

import importlib.util

import pytest

from src.workbench_qml import QML_SOURCE

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

# #831 mass baseline (pre-polish). Slim polish must land clearly below these.
_PRIOR_HEADER_HEIGHT = 54.0
_PRIOR_FOOTER_HEIGHT = 40.0
_PRIOR_SYNC_W = 48.0
_PRIOR_SYNC_H = 25.0
_PRIOR_SCOPE_CONTROL = 28.0

# Chosen corridors (logical px / DIP at 100% scale baseline).
_HEADER_MIN = 24.0
_HEADER_MAX = 40.0
_FOOTER_MIN = 24.0
_FOOTER_MAX = 32.0
_MIN_HIT = 20.0


def test_identity_is_plain_product_text_without_decorative_glyph() -> None:
    start = QML_SOURCE.index('objectName: "screen1Header"')
    end = QML_SOURCE.index('objectName: "headerNavZone"', start)
    header_left = QML_SOURCE[start:end]
    assert "Sample Brain" in header_left
    assert "◉" not in header_left


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
@pytest.mark.parametrize("size", [(1120, 640), (1600, 900)])
def test_runtime_slim_header_footer_corridors(size) -> None:
    from tests.test_program_chrome_qml_831 import _build_screen1_window
    from PySide6.QtQuick import QQuickItem

    width, height = size
    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(width)
        window.setHeight(height)
        settle(app)
        settle(app)

        header = window.findChild(QQuickItem, "screen1Header")
        footer = window.findChild(QQuickItem, "programFooterBand")
        assert header is not None and footer is not None

        h = float(header.height())
        f = float(footer.height())
        assert h < _PRIOR_HEADER_HEIGHT
        assert _HEADER_MIN <= h <= _HEADER_MAX
        assert f < _PRIOR_FOOTER_HEIGHT
        assert _FOOTER_MIN <= f <= _FOOTER_MAX
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_transport_and_scope_controls_are_lighter() -> None:
    from tests.test_program_chrome_qml_831 import _build_screen1_window
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(1600)
        window.setHeight(900)
        settle(app)
        settle(app)

        sync = window.findChild(QQuickItem, "syncIndicator")
        overflow = window.findChild(QQuickItem, "displayPreferencesOverflow")
        sources = window.findChild(QQuickItem, "librarySourcesScopeButton")
        assert sync is not None and overflow is not None and sources is not None

        assert float(sync.width()) < _PRIOR_SYNC_W
        assert float(sync.height()) < _PRIOR_SYNC_H
        assert float(sync.height()) >= _MIN_HIT - 2.0

        assert float(overflow.width()) <= 28.0
        assert float(overflow.height()) <= 26.0
        assert float(overflow.height()) >= _MIN_HIT - 2.0

        assert float(sources.width()) < _PRIOR_SCOPE_CONTROL
        assert float(sources.height()) < _PRIOR_SCOPE_CONTROL
        assert float(sources.height()) >= _MIN_HIT - 2.0
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_nav_hit_areas_remain_usable_and_flat() -> None:
    from tests.test_program_chrome_qml_831 import _build_screen1_window
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(1600)
        window.setHeight(900)
        settle(app)
        settle(app)

        header = window.findChild(QQuickItem, "screen1Header")
        assert header is not None
        for name in (
            "programNavBrowser",
            "programNavLiveKit",
            "programNavStepSequencer",
            "programNavArrangement",
        ):
            btn = window.findChild(QQuickItem, name)
            assert btn is not None
            assert float(btn.height()) >= _MIN_HIT
            assert float(btn.height()) <= float(header.height()) + 1.0
            assert float(btn.width()) >= 48.0
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_visual_grab_slim_chrome_880(tmp_path) -> None:
    """Runtime evidence grab for Owner Visual Acceptance review (#880)."""
    from pathlib import Path

    from tests.test_program_chrome_qml_831 import _build_screen1_window
    from PySide6.QtQuick import QQuickItem

    evidence = Path(tmp_path) / "program_chrome_880"
    evidence.mkdir()
    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(1600)
        window.setHeight(900)
        settle(app)
        settle(app)
        header = window.findChild(QQuickItem, "screen1Header")
        footer = window.findChild(QQuickItem, "programFooterBand")
        assert header is not None and footer is not None
        assert _HEADER_MIN <= float(header.height()) <= _HEADER_MAX
        assert _FOOTER_MIN <= float(footer.height()) <= _FOOTER_MAX
        grab = window.grabWindow()
        out = evidence / "screen1_program_chrome_slim_1600x900.png"
        assert grab.save(str(out))
        assert out.stat().st_size > 0
    finally:
        window.close()
        app.processEvents()
