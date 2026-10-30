"""#1249: Screen-1 producer text consumes Appearance V2 typography roles."""

from __future__ import annotations

import re

import pytest

from src.workbench_qml import QML_SOURCE


def _near(marker: str, length: int = 450) -> str:
    start = QML_SOURCE.index(marker)
    return QML_SOURCE[start : start + length]


def test_bridge_projects_scaled_ui_roles_without_scaling_code_font(tmp_path):
    pytest.importorskip("PySide6")
    from src.workbench_qml import _qml_theme_authority_bridge

    bridge = _qml_theme_authority_bridge(state_dir=tmp_path)
    assert (
        bridge.typographyUiCaptionSize,
        bridge.typographyUiCaptionLineHeight,
        bridge.typographyUiStandardSize,
        bridge.typographyUiStandardLineHeight,
        bridge.typographyUiContentSize,
        bridge.typographyUiContentLineHeight,
        bridge.typographyCodeSize,
    ) == (12, 16, 14, 20, 16, 26, 12)

    bridge.setUiFontSize(18)
    assert (
        bridge.typographyUiCaptionSize,
        bridge.typographyUiCaptionLineHeight,
        bridge.typographyUiStandardSize,
        bridge.typographyUiStandardLineHeight,
        bridge.typographyUiContentSize,
        bridge.typographyUiContentLineHeight,
        bridge.typographyCodeSize,
    ) == (15.5, 20.5, 18, 25.5, 20.5, 33.5, 12)

    bridge.setCodeFontSize(16)
    assert bridge.typographyCodeSize == 16
    assert bridge.typographyUiStandardSize == 18


def test_program_chrome_consumes_standard_and_caption_roles():
    for name in ("programNavEdit", "programNavArrangement"):
        assert "font.pixelSize: themeAuthority.typographyUiStandardSize" in _near(
            f'objectName: "{name}"', 240
        )
    for label in ('text: "MASTER"', 'text: "BPM"'):
        assert "font.pixelSize: themeAuthority.typographyUiCaptionSize" in _near(
            label, 180
        )
    assert "font.pixelSize: themeAuthority.typographyUiCaptionSize" in _near(
        'text: syncButton.text', 240
    )


def test_browser_producer_text_uses_role_bindings():
    assert "font.pixelSize: themeAuthority.typographyUiContentSize" in _near(
        "text: window.screenData.browserContext", 200
    )
    assert "lineHeightMode: Text.FixedHeight" in _near(
        "text: window.screenData.browserContext", 260
    )
    assert "font.pixelSize: themeAuthority.typographyUiStandardSize" in _near(
        'objectName: "browserSearch"', 700
    )
    assert "Layout.preferredHeight: Math.max(28, implicitHeight)" in _near(
        'objectName: "browserSearch"', 700
    )
    assert "font.pixelSize: themeAuthority.typographyUiStandardSize" in _near(
        "text: modelData.name; color: theme.textPrimary", 250
    )
    for field in ("bpm", "key", "duration", "type"):
        assert "font.pixelSize: themeAuthority.typographyUiCaptionSize" in _near(
            f"text: modelData.{field}; color: theme.textSecondary", 320
        )
    for role in ("filename", "bpm", "favorite", "key", "length", "type"):
        assert "font.pixelSize: themeAuthority.typographyUiCaptionSize" in _near(
            f'objectName: "browserColumnHeader_{role}"', 950
        )


def test_footer_uses_caption_without_changing_fixed_geometry():
    for name in ("contextHintDisplay", "footerStatusLabel"):
        assert "font.pixelSize: themeAuthority.typographyUiCaptionSize" in _near(
            f'objectName: "{name}"', 800
        )
        assert "lineHeightMode: Text.FixedHeight" in _near(
            f'objectName: "{name}"', 800
        )
    assert re.search(r"height: window.programChromeVisible \? 22 : 0", QML_SOURCE)
    assert "property int densityRowHeight: 30" in QML_SOURCE
    assert "property int browserColumnReorderThreshold: 8" in QML_SOURCE


def test_footer_caption_line_height_is_fixed_in_qt_runtime(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QObject

    from src.workbench_qml import Screen1QmlViewModel, _qml_engine

    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    app, engine, window = _qml_engine(view_model)
    try:
        window.show()
        app.processEvents()
        for name in ("contextHintDisplay", "footerStatusLabel"):
            label = window.findChild(QObject, name)
            assert label is not None
            assert label.property("font").pixelSize() == 12
            assert label.property("lineHeight") == 16
            assert label.property("height") <= 22
    finally:
        window.close()
        app.processEvents()
        for attr in ("_screen1_waveform_timer", "_screen1_browser_loop_timer"):
            timer = getattr(engine, attr, None)
            if timer is not None:
                timer.stop()
        for attr in ("_screen1_waveform_loader", "_screen1_analysis_coordinator"):
            worker = getattr(engine, attr, None)
            if worker is not None:
                worker.close()
