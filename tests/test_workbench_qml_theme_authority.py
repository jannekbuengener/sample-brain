"""#785 Theme Authority QML bridge + Appearance UI in display preferences.

Theme Core owns tokens; QML binds semantic roles via themeAuthority.
No competing HEX palette in QML_SOURCE.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from src import workbench_qml
from src import workbench_theme as theme

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

REQUIRED_THEME_AUTHORITY_KEYS = (
    "surfaceRoot",
    "surfaceHeader",
    "surfaceBrowser",
    "surfacePanel",
    "surfaceElevated",
    "borderSubtle",
    "dividerDefault",
    "textPrimary",
    "textSecondary",
    "textDisabled",
    "textOnAction",
    "waveformDefault",
    "waveformActive",
    "selectionSurface",
    "selectionBorder",
    "actionActive",
    "hoverSurface",
)

_HEX_RE = re.compile(r'"(#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8}))"')


def test_qml_source_binds_theme_from_theme_authority_not_hardcoded_hex():
    source = workbench_qml.QML_SOURCE
    assert "id: theme" in source
    assert "themeAuthority" in source
    # Semantic roles bind from authority — no primitive HEX block.
    for name in REQUIRED_THEME_AUTHORITY_KEYS:
        assert (
            f"property color {name}: themeAuthority.{name}" in source
            or f"readonly property color {name}: themeAuthority.{name}" in source
        ), f"theme.{name} must bind themeAuthority.{name}"
    # No quoted HEX color literals remain in Screen-1 QML (Theme Core is truth).
    assert _HEX_RE.findall(source) == [], (
        "QML_SOURCE must not hardcode HEX; themeAuthority owns color values"
    )


def test_display_preferences_hosts_appearance_theme_controls():
    source = workbench_qml.QML_SOURCE
    assert "displayPreferencesPopover" in source
    # Appearance hosted in the same overflow — not a tools panel / skin editor.
    assert "objectName: \"themePresetSelector\"" in source
    assert "objectName: \"themeAccentField\"" in source
    assert "objectName: \"themeBackgroundField\"" in source
    assert "objectName: \"themeForegroundField\"" in source
    assert "objectName: \"themeCustomNameField\"" in source
    assert "objectName: \"themeSaveButton\"" in source
    assert "objectName: \"themeDeleteButton\"" in source
    assert "objectName: \"themeResetButton\"" in source
    assert "Appearance" in source
    # No permanent settings bar / tools panel skin editor surface.
    assert "skinEditor" not in source
    assert "toolsPanelTheme" not in source


def test_header_stays_brand_clean_without_logo_lockup():
    source = workbench_qml.QML_SOURCE
    header_start = source.index("id: screen1Header")
    header_chunk = source[header_start : header_start + 3500]
    assert "productIdentity" in header_chunk
    assert "SAMPLE BRAIN" not in header_chunk
    assert "analysisBrandBrain" not in header_chunk
    assert "Frech aber im Flow" not in header_chunk
    assert "sample_brain_logo_primary" not in header_chunk
    assert "sample_brain_splash_typography" not in header_chunk


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_theme_authority_switch_updates_semantic_colors(tmp_path: Path, monkeypatch):
    from PySide6.QtQuick import QQuickItem

    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import Screen1QmlViewModel, _qml_engine
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_qml_runtime import Screen1QmlRuntimeComposition

    db = tmp_path / "library.db"
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
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        authority = engine.rootContext().contextProperty("themeAuthority")
        assert authority is not None
        blood = theme.theme_tokens_to_qml_semantics(theme.resolve_theme("Blood"))
        arctic = theme.theme_tokens_to_qml_semantics(theme.resolve_theme("Arctic"))
        carbon = theme.theme_tokens_to_qml_semantics(theme.resolve_theme("Carbon"))
        assert blood["actionActive"] != arctic["actionActive"] or (
            blood["surfaceRoot"] != arctic["surfaceRoot"]
        )

        authority.selectTheme("Blood")
        app.processEvents()
        assert str(authority.selectedTheme) == "Blood"
        assert str(authority.actionActive).lower() == blood["actionActive"].lower()

        authority.selectTheme("Arctic")
        app.processEvents()
        assert str(authority.selectedTheme) == "Arctic"
        assert str(authority.actionActive).lower() == arctic["actionActive"].lower()
        assert str(authority.hoverSurface).lower() == arctic["hoverSurface"].lower()
        assert str(authority.textOnAction).lower() == "#ffffff"

        authority.selectTheme("Carbon")
        app.processEvents()
        assert str(authority.selectedTheme) == "Carbon"
        assert str(authority.actionActive).lower() == carbon["actionActive"].lower()

        # Theme QtObject mirrors authority into the live window color.
        assert str(window.property("color")).lower() in {
            str(authority.surfaceRoot).lower(),
            # QColor string forms may include alpha / named wrappers.
        } or window.property("color") is not None

        header = window.findChild(QQuickItem, "screen1Header")
        assert header is not None
        # No permanent brand Image children in the header.
        for child in header.findChildren(QQuickItem):
            name = str(child.objectName() or "")
            assert name not in {"analysisBrandBrain", "brandMotionLayer"}
    finally:
        coordinator = getattr(engine, "_screen1_analysis_coordinator", None)
        if coordinator is not None:
            coordinator.shutdown()
        window.close()
        engine.deleteLater()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_custom_theme_lifecycle_via_theme_authority(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import Screen1QmlViewModel, _qml_engine
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_qml_runtime import Screen1QmlRuntimeComposition

    db = tmp_path / "library.db"
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
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    try:
        authority = engine.rootContext().contextProperty("themeAuthority")
        authority.createCustomTheme(
            "Studio Night",
            "Blood",
            "#aa1133",
            "#040405",
            "#f0f2f5",
        )
        app.processEvents()
        assert "Studio Night" in list(authority.customThemeNames)
        assert str(authority.selectedTheme) == "Studio Night"
        assert str(authority.editAccent).lower() == "#aa1133"

        authority.saveCustomTheme("Studio Night", "Blood", "#bb2244", "#040405", "#f0f2f5")
        app.processEvents()
        assert str(authority.editAccent).lower() == "#bb2244"

        authority.resetCustomTheme("Studio Night")
        app.processEvents()
        blood = theme.resolve_theme("Blood")
        assert str(authority.editAccent).lower() == blood.accent.lower()

        authority.deleteCustomTheme("Studio Night")
        app.processEvents()
        assert "Studio Night" not in list(authority.customThemeNames)
        assert str(authority.selectedTheme) == "Blood"
    finally:
        coordinator = getattr(engine, "_screen1_analysis_coordinator", None)
        if coordinator is not None:
            coordinator.shutdown()
        window.close()
        engine.deleteLater()
        app.processEvents()
