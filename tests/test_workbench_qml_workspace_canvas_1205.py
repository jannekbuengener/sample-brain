"""#1205 Screen-1 calm near-black workspace/canvas base authority.

FROZEN CONTRACT (test-first):
  - one Theme Core semantic owns the Screen-1 base workspace/canvas
  - Clean Start, residual/collapsed gaps, and empty center share that authority
  - MagicPath convergence visual target for default Blood canvas is ``#0d0f12``
  - panels may stay elevated; Blood/Accent never owns the canvas
  - no decorative Gradient/Glow/Shader on the base surface
  - no scattered ``#0A0E0F`` / ``#0d0f12`` QML literals

Canon:
  - issue #1205 (+ Owner MagicPath convergence note)
  - docs/assets/themes/presets.v1.json + src/workbench_theme.py
  - docs/WORKBENCH_VISUAL_ACCEPTANCE.md (Screen-1 color contract)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src import workbench_theme as theme
from src.workbench_qml import QML_SOURCE


BLOOD_CANVAS_TARGET = "#0d0f12"
BLOOD_CHROME_TARGET = "#0b0d10"
HISTORICAL_SCREENSHOT_REF = "#0a0e0f"
PURE_BLACK = "#000000"
PURE_WHITE = "#ffffff"


def _normalize_hex(value: str) -> str:
    token = str(value).strip().lower()
    if not token.startswith("#"):
        token = f"#{token}"
    return token


def _qml_root_window_block() -> str:
    root_start = QML_SOURCE.index("ApplicationWindow {")
    root_end = QML_SOURCE.index("QtObject {", root_start)
    return QML_SOURCE[root_start:root_end]


def _qml_named_block(object_name: str, *, size: int = 1200) -> str:
    marker = f'objectName: "{object_name}"'
    start = QML_SOURCE.index(marker)
    return QML_SOURCE[start : start + size]


def test_theme_core_blood_canvas_matches_magicpath_convergence_target() -> None:
    """Default Blood workspace lands on the Owner MagicPath canvas target."""
    tokens = theme.resolve_theme("Blood").as_dict()
    assert _normalize_hex(tokens["background"]) == BLOOD_CHROME_TARGET
    assert _normalize_hex(tokens["surfaceWorkspace"]) == BLOOD_CANVAS_TARGET
    mapped = theme.theme_tokens_to_qml_semantics(theme.resolve_theme("Blood"))
    assert _normalize_hex(mapped["surfaceRoot"]) == BLOOD_CANVAS_TARGET
    assert _normalize_hex(mapped["surfaceHeader"]) == BLOOD_CHROME_TARGET
    assert _normalize_hex(mapped["surfaceRoot"]) != _normalize_hex(mapped["actionActive"])
    assert _normalize_hex(mapped["surfaceRoot"]) != PURE_BLACK
    assert _normalize_hex(mapped["surfaceRoot"]) != PURE_WHITE
    # Historical screenshot ~#0A0E0F remains directional evidence, not a second API.
    assert _normalize_hex(mapped["surfaceRoot"]) != HISTORICAL_SCREENSHOT_REF


def test_screen1_application_window_uses_canvas_surface_root_authority() -> None:
    """Outer window fill is the canvas authority so residual collapse cannot flash chrome."""
    root = _qml_root_window_block()
    assert "color: theme.surfaceRoot" in root
    assert "color: theme.surfaceHeader" not in root
    assert "color: theme.actionActive" not in root
    assert re.search(r'color:\s*"#', root) is None


def test_clean_start_and_analysis_surfaces_share_canvas_authority() -> None:
    calm = _qml_named_block("calmCanvas", size=900)
    analysis = _qml_named_block("analysisWorkingSurface", size=900)
    assert "color: theme.surfaceRoot" in calm
    assert "color: theme.surfaceRoot" in analysis
    assert re.search(r'color:\s*"#0[Aa]0[Ee]0[Ff]"', calm) is None
    assert re.search(r'color:\s*"#0[Dd]0[Ff]12"', calm) is None
    assert "Gradient" not in calm
    assert "Glow" not in calm
    assert "ShaderEffect" not in calm


def test_active_playlist_viewport_reuses_same_canvas_authority() -> None:
    viewport = _qml_named_block("browserListViewport", size=400)
    assert "color: theme.surfaceRoot" in viewport
    assert "theme.surfaceHeader" not in viewport
    assert "theme.actionActive" not in viewport
    assert re.search(r'color:\s*"#', viewport) is None


def test_panel_surfaces_remain_elevated_above_canvas() -> None:
    """#1205 is canvas authority only — do not flatten panels to the workspace fill."""
    library = _qml_named_block("libraryPane", size=240)
    browser = _qml_named_block("browserPane", size=240)
    harmony = _qml_named_block("harmonyPane", size=500)
    bottom = _qml_named_block("bottomRackPane", size=4500)
    assert "color: theme.surfaceLibrary" in library
    assert "color: theme.surfaceBrowser" in browser
    assert "color: theme.surfacePanel" in harmony
    assert "color: theme.surfacePanel" in bottom

    blood = theme.resolve_theme("Blood")
    mapped = theme.theme_tokens_to_qml_semantics(blood)
    assert mapped["surfaceRoot"] != mapped["surfacePanel"]
    assert mapped["surfaceRoot"] != mapped["surfaceLibrary"]
    assert mapped["surfaceRoot"] != mapped["surfaceBrowser"]


def test_qml_source_introduces_no_hardcoded_canvas_literals_or_effects() -> None:
    source = QML_SOURCE
    assert "#0a0e0f" not in source.casefold()
    assert "#0d0f12" not in source.casefold()
    # Base canvas path must stay solid fills — no decorative workspace treatment.
    assert "ShaderEffect" not in source
    assert "RectangularGlow" not in source
    assert "FastBlur" not in source
    root = _qml_root_window_block()
    assert "gradient:" not in root.casefold()


def test_presets_canon_records_blood_canvas_target() -> None:
    canon = theme._load_canon()
    blood = canon["presets"]["Blood"]
    assert _normalize_hex(blood["base"]["background"]) == BLOOD_CHROME_TARGET
    assert _normalize_hex(blood["derived"]["surfaceWorkspace"]) == BLOOD_CANVAS_TARGET
    assert blood["derived"]["surfaceWorkspace"] == theme.mix_hex(
        blood["base"]["background"],
        blood["base"]["foreground"],
        0.008,
    )


@pytest.mark.skipif(
    not __import__("src.workbench_qml", fromlist=["qml_runtime_available"]).qml_runtime_available(),
    reason="PySide6 unavailable",
)
def test_runtime_clean_start_window_and_calm_canvas_share_theme_canvas(
    tmp_path: Path,
) -> None:
    from PySide6.QtGui import QColor
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml import Screen1QmlInteractionAdapter, Screen1QmlViewModel
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        apply_screen1_visual_state_v2,
    )
    from src.workbench_visual_acceptance import (
        build_screen1_visual_fixture_v2,
        resolve_screen1_visual_state_v2,
    )

    fixture = build_screen1_visual_fixture_v2()
    clean = resolve_screen1_visual_state_v2(fixture, "screen1-clean-start")
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    adapter = Screen1QmlInteractionAdapter(view_model=view_model)
    apply_screen1_visual_state_v2(view_model, adapter, fixture, clean)
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    try:
        _settle_qml_frame(app)
        expected = QColor(theme.resolve_theme("Blood").as_dict()["surfaceWorkspace"])
        assert QColor(window.property("color")).name() == expected.name()
        calm = window.findChild(QQuickItem, "calmCanvas")
        assert calm is not None
        assert QColor(calm.property("color")).name() == expected.name()
        assert expected.name().lower() == BLOOD_CANVAS_TARGET
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(
    not __import__("src.workbench_qml", fromlist=["qml_runtime_available"]).qml_runtime_available(),
    reason="PySide6 unavailable",
)
def test_runtime_browser_collapse_residual_keeps_canvas_not_chrome_fallback(
    tmp_path: Path,
) -> None:
    """#1204 residual geometry must reveal surfaceRoot, not a mismatched chrome/black."""
    from PySide6.QtGui import QColor
    from PySide6.QtQuick import QQuickItem

    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml import Screen1QmlInteractionAdapter
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-harmonic-4panel")
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(
            finder=lambda *_a, **_k: ([], None)
        ),
    )
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    try:
        _settle_qml_frame(app)
        blood = theme.resolve_theme("Blood")
        canvas = QColor(blood.as_dict()["surfaceWorkspace"])
        chrome = QColor(blood.background)
        assert QColor(window.property("color")).name() == canvas.name()
        assert canvas.name() != chrome.name()

        interaction = window.property("interaction")
        assert interaction is not None
        assert adapter.browser_collapsed is False
        interaction.toggleBrowserCollapsed()
        _settle_qml_frame(app)
        assert adapter.browser_collapsed is True
        # Residual is transparent Item space; window canvas must remain the fill.
        assert QColor(window.property("color")).name() == canvas.name()
        browser = window.findChild(QQuickItem, "browserPane")
        assert browser is not None
        assert float(browser.property("width") or 0) == 0.0

        interaction.toggleBrowserCollapsed()
        _settle_qml_frame(app)
        assert adapter.browser_collapsed is False
        assert QColor(window.property("color")).name() == canvas.name()
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()


@pytest.mark.skipif(
    not __import__("src.workbench_qml", fromlist=["qml_runtime_available"]).qml_runtime_available(),
    reason="PySide6 unavailable",
)
def test_runtime_theme_switch_updates_canvas_binding(tmp_path: Path) -> None:
    from PySide6.QtGui import QColor
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml import Screen1QmlInteractionAdapter, Screen1QmlViewModel
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        apply_screen1_visual_state_v2,
    )
    from src.workbench_visual_acceptance import (
        build_screen1_visual_fixture_v2,
        resolve_screen1_visual_state_v2,
    )

    fixture = build_screen1_visual_fixture_v2()
    clean = resolve_screen1_visual_state_v2(fixture, "screen1-clean-start")
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    adapter = Screen1QmlInteractionAdapter(view_model=view_model)
    apply_screen1_visual_state_v2(view_model, adapter, fixture, clean)
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    bridge = getattr(engine, "_screen1_theme_authority", None)
    assert bridge is not None
    window.show()
    try:
        _settle_qml_frame(app)
        blood_canvas = QColor(theme.resolve_theme("Blood").as_dict()["surfaceWorkspace"])
        assert QColor(window.property("color")).name() == blood_canvas.name()

        bridge.selectTheme("Carbon")
        _settle_qml_frame(app)
        carbon_canvas = QColor(theme.resolve_theme("Carbon").as_dict()["surfaceWorkspace"])
        assert QColor(window.property("color")).name() == carbon_canvas.name()
        calm = window.findChild(QQuickItem, "calmCanvas")
        if calm is not None and bool(calm.property("visible")):
            assert QColor(calm.property("color")).name() == carbon_canvas.name()
        assert carbon_canvas.name() != blood_canvas.name()
    finally:
        window.close()
        app.processEvents()
