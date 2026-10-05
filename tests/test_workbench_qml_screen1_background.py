"""Historical Screen-1 background evidence and visible V7 root contracts."""

from __future__ import annotations

import hashlib
import inspect
import re
from pathlib import Path

import pytest

from src import workbench_qml
from src import workbench_qml_spike


EXPECTED_SHA256 = (
    "2c799440a7b2c9d6e20e8163378ddcbecd29478d76ad8d7ee74835d3b60a47ae"
)
REFERENCE_RELATIVE = Path(
    "docs/assets/portfolio/references/screen1_background_reference.png"
)


def test_screen1_background_reference_exists_and_matches_canonical_sha():
    path = workbench_qml.screen1_background_reference_path()
    assert path == Path(__file__).resolve().parents[1] / REFERENCE_RELATIVE
    assert path.is_file()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == EXPECTED_SHA256
    assert digest == workbench_qml.SCREEN1_BACKGROUND_REFERENCE_SHA256


def test_screen1_background_url_points_at_repo_reference():
    url = workbench_qml.screen1_background_url()
    assert url.startswith("file:")
    path = workbench_qml.screen1_background_reference_path()
    assert path.as_posix().lower() in url.replace("\\", "/").lower() or path.name in url


def test_qml_source_keeps_historical_background_non_composited_without_effects():
    source = workbench_qml.QML_SOURCE
    assert "objectName: \"screen1Background\"" in source
    assert "source: screen1BackgroundUrl" in source
    assert "Gradient" not in source
    assert "LinearGradient" not in source
    assert "RadialGradient" not in source
    # The immutable asset/URL helper stays for historical evidence, but may not
    # cover the V7 root chrome after it has loaded.
    bg_block = re.search(
        r"Image\s*\{[^}]*objectName:\s*\"screen1Background\".*?\}",
        source,
        re.DOTALL,
    )
    assert bg_block is not None
    block = bg_block.group(0)
    assert "visible: false" in block
    # No opacity/tint workaround or decorative effect may replace the explicit
    # non-composited state.
    assert "colorize" not in block.casefold()
    assert "opacity:" not in block.casefold()
    assert "layer.enabled" not in block.casefold()
    assert "FastBlur" not in block
    assert "Glow" not in block


def test_qml_palette_tokens_are_near_black_with_functional_accent_only():
    from src import workbench_theme as theme_core

    source = workbench_qml.QML_SOURCE
    # Theme Authority facade — no competing hardcoded primitive palette.
    assert "readonly property color surfaceRoot: themeAuthority.surfaceRoot" in source
    assert "readonly property color actionActive: themeAuthority.actionActive" in source
    assert "readonly property color focusRing: themeAuthority.focusRing" in source
    blood = theme_core.resolve_theme("Blood")
    mapped = theme_core.theme_tokens_to_qml_semantics(blood)
    assert blood.accent.lower() == "#8f0e24"
    assert mapped["actionActive"].lower() == "#8f0e24"
    assert mapped["surfaceRoot"].lower() == blood.as_dict()["surfaceWorkspace"].lower()
    assert mapped["surfaceHeader"].lower() == blood.background.lower()
    assert mapped["surfaceRoot"].lower() != mapped["surfaceHeader"].lower()
    # Accent stays blood-red functional; no orange / blue brand accents.
    assert "#ff4500" not in source.casefold()
    assert '"#b1122b"' not in source


def test_v7_725_capture_does_not_require_historical_background_texture():
    """Clean-start evidence remains valid with a solid Theme Core root."""
    capture_source = inspect.getsource(workbench_qml_spike.run_qml_visual_acceptance_725)

    assert "validate_capture_sanity" in capture_source
    assert "_png_center_patch_has_texture" not in capture_source


@pytest.mark.skipif(
    not workbench_qml.qml_runtime_available(),
    reason="PySide6 unavailable",
)
def test_qml_runtime_paints_v7_chrome_while_historical_background_stays_hidden():
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
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-harmonic-4panel",
    )
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(
            finder=lambda *_a, **_k: ([], None)
        ),
    )
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        background = window.findChild(QQuickItem, "screen1Background")
        assert background is not None
        source = str(background.property("source"))
        assert "screen1_background_reference.png" in source.replace("\\", "/")
        # Runtime proof: an opaque historical image cannot cover the actual V7
        # ApplicationWindow chrome layer after asynchronous loading.
        assert not background.isVisible()
        assert window.property("color").name().lower() == "#020203"
        assert window.property("accent").name() == "#8f0e24"
        assert window.property("panel").name() == "#080809"
        assert window.property("panelAlt").name() == "#101011"
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
    not workbench_qml.qml_runtime_available(),
    reason="PySide6 unavailable",
)
def test_historical_background_helper_allows_v7_capture_without_a_visible_image():
    """Legacy capture setup stays callable after the V7 root supersession."""
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml import Screen1QmlInteractionAdapter, Screen1QmlViewModel
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        _wait_for_screen1_background_ready,
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
        _wait_for_screen1_background_ready(window, app)
        background = window.findChild(QQuickItem, "screen1Background")
        assert background is not None
        assert not background.isVisible()
    finally:
        window.close()
        app.processEvents()
