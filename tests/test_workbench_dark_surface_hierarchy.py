"""Dark workspace surface hierarchy polish — FROZEN CONTRACT.

Status: TEST_FREEZE (noir density + subliminal atmosphere + panel uniformity)
Canon:
  - docs/assets/themes/README.md (CURRENT→TARGET + atmosphere restraint)
  - docs/assets/themes/presets.v1.json
  - docs/WORKBENCH_VISUAL_ACCEPTANCE.md (dark surface hierarchy)
  - src/workbench_theme.py (Theme Authority sole owner)

Intent: cinematic noir with three calm depth steps — Program Chrome darkest
ink floor, Main Workspace barely raised, Panels subtly separated with low
mass — PLUS Theme soft-ellipse atmosphere at **subliminal** strength on the
full panel family (Library, Browser, Live Kit, Harmonic Matching) and
workspace. Glow is minimal depth only — not a visible light effect.
Superdesign cinematic-noir deep/zinc solids map via Theme bases; radial
atmosphere maps via Theme PNG overlays (not QML Gradient/RadialGradient).
Semantic relations only; screenshot pixels are not absolute truth.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import workbench_theme as theme


PRESET_ORDER = ("Blood", "Carbon", "Arctic", "Rose", "Forest")
PURE_BLACK = "#000000"

# Blood noir TARGET (docs/assets/themes/README.md) — deep/zinc solid map
BLOOD_CHROME = "#020203"
BLOOD_WORKSPACE = "#040405"
BLOOD_PANEL = "#080809"
BLOOD_DIVIDER = "#19191a"
BLOOD_TEXT_PRIMARY = "#e4e6ea"
BLOOD_TEXT_SECONDARY = "#68696b"
BLOOD_ATMOSPHERE_WORKSPACE_CORE = "#0b0608"
BLOOD_ATMOSPHERE_WORKSPACE_MID = "#040405"
BLOOD_ATMOSPHERE_WORKSPACE_EDGE = "#030304"
BLOOD_ATMOSPHERE_PANEL_CORE = "#0d090b"
BLOOD_ATMOSPHERE_PANEL_MID = "#080809"
BLOOD_ATMOSPHERE_PANEL_EDGE = "#050506"

# Previous polish values that Owner rejected as too open/gray — must stay darker.
PRIOR_OPEN_CHROME = "#050506"
PRIOR_OPEN_WORKSPACE = "#0b0b0c"
PRIOR_OPEN_PANEL = "#0f0f11"
PRIOR_OPEN_DIVIDER = "#2a2a2c"
# Mid noir pass before Superdesign deep-black floor tighten.
PRIOR_NOIR_CHROME = "#030304"
PRIOR_NOIR_WORKSPACE = "#060607"
# Visible atmosphere cores from the first atmosphere-on-both pass — must stay darker.
PRIOR_VISIBLE_ATMOSPHERE_WORKSPACE_CORE = "#1e0d11"
PRIOR_VISIBLE_ATMOSPHERE_PANEL_CORE = "#1c0d10"
PRIOR_ATMOSPHERE_WORKSPACE = "#050506"

WORKSPACE_MIX = 0.008
SURFACE_MIX = 0.028
RAISED_MIX = 0.06
HOVER_MIX = 0.075
DIVIDER_MIX = 0.10
TEXT_SECONDARY_MIX = 0.55
ATMOSPHERE_WORKSPACE_ACCENT_MIX = 0.035
ATMOSPHERE_WORKSPACE_FG_MIX = 0.008
ATMOSPHERE_PANEL_ACCENT_MIX = 0.03
ATMOSPHERE_PANEL_FG_MIX = 0.006
# Subliminal depth: core must stay close to mid (not a visible glow oval).
MAX_ATMOSPHERE_CORE_TO_MID_LUM_RATIO = 2.0


def _normalize_hex(value: str) -> str:
    token = str(value).strip().lower()
    if not token.startswith("#"):
        token = f"#{token}"
    return token


def _parse_rgb(value: str) -> tuple[int, int, int]:
    body = _normalize_hex(value)[1:]
    return int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16)


def _relative_luminance(value: str) -> float:
    """sRGB relative luminance (WCAG). Higher = lighter."""

    def _lin(channel: int) -> float:
        c = channel / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = _parse_rgb(value)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _canon() -> dict:
    root = Path(__file__).resolve().parents[1]
    return json.loads(
        (root / "docs" / "assets" / "themes" / "presets.v1.json").read_text(
            encoding="utf-8"
        )
    )


def test_canon_documents_noir_surface_workspace_derivation() -> None:
    canon = _canon()
    assert "surfaceWorkspace" in canon["derivation"]
    assert canon["derivation"]["surfaceWorkspace"] == (
        "mix(background, foreground, 0.008)"
    )
    assert canon["derivation"]["surface"] == (
        "mix(background, foreground, 0.028)"
    )
    assert canon["derivation"]["surfaceRaised"] == (
        "mix(background, foreground, 0.06)"
    )
    assert canon["derivation"]["divider"] == (
        "mix(background, foreground, 0.10)"
    )
    assert canon["derivation"]["hover"] == (
        "mix(background, foreground, 0.075)"
    )
    assert canon["derivation"]["textSecondary"] == (
        "mix(foreground, background, 0.55)"
    )
    for name in PRESET_ORDER:
        derived = canon["presets"][name]["derived"]
        assert "surfaceWorkspace" in derived
        assert _normalize_hex(derived["surfaceWorkspace"]) != PURE_BLACK


def test_theme_core_exposes_noir_surface_workspace_for_all_presets() -> None:
    for name in PRESET_ORDER:
        tokens = theme.resolve_theme(name)
        as_dict = tokens.as_dict()
        assert "surfaceWorkspace" in as_dict
        expected = theme.mix_hex(tokens.background, tokens.foreground, WORKSPACE_MIX)
        assert _normalize_hex(as_dict["surfaceWorkspace"]) == _normalize_hex(expected)
        assert _normalize_hex(as_dict["surface"]) == _normalize_hex(
            theme.mix_hex(tokens.background, tokens.foreground, SURFACE_MIX)
        )
        assert _normalize_hex(as_dict["divider"]) == _normalize_hex(
            theme.mix_hex(tokens.background, tokens.foreground, DIVIDER_MIX)
        )
        assert _normalize_hex(as_dict["textSecondary"]) == _normalize_hex(
            theme.mix_hex(tokens.foreground, tokens.background, TEXT_SECONDARY_MIX)
        )
        assert _normalize_hex(as_dict["surfaceWorkspace"]) != PURE_BLACK
        assert _normalize_hex(tokens.background) != PURE_BLACK


def test_dark_surface_hierarchy_luminance_steps_for_all_presets() -> None:
    """chrome < workspace < panels < elevated (relative luminance)."""
    for name in PRESET_ORDER:
        tokens = theme.resolve_theme(name)
        chrome = _normalize_hex(tokens.background)
        workspace = _normalize_hex(tokens.as_dict()["surfaceWorkspace"])
        panel = _normalize_hex(tokens.surface)
        elevated = _normalize_hex(tokens.surfaceRaised)

        lum_chrome = _relative_luminance(chrome)
        lum_workspace = _relative_luminance(workspace)
        lum_panel = _relative_luminance(panel)
        lum_elevated = _relative_luminance(elevated)

        assert lum_chrome < lum_workspace, f"{name}: workspace not lighter than chrome"
        assert lum_workspace < lum_panel, f"{name}: panel not lighter than workspace"
        assert lum_panel < lum_elevated, f"{name}: elevated not lighter than panel"

        # Minimally lighter workspace: stay closer to chrome than to panel.
        step_cw = lum_workspace - lum_chrome
        step_wp = lum_panel - lum_workspace
        assert step_cw > 0
        assert step_wp > 0
        assert step_cw <= step_wp * 1.35, (
            f"{name}: workspace step too large vs panel separation"
        )


def test_blood_noir_density_darker_than_prior_open_gray_polish() -> None:
    """Owner rejection guard: Blood must stay denser than the open-gray pass."""
    tokens = theme.resolve_theme("Blood").as_dict()
    assert _normalize_hex(tokens["background"]) == BLOOD_CHROME
    assert _normalize_hex(tokens["surfaceWorkspace"]) == BLOOD_WORKSPACE
    assert _normalize_hex(tokens["surface"]) == BLOOD_PANEL
    assert _normalize_hex(tokens["divider"]) == BLOOD_DIVIDER
    assert _normalize_hex(tokens["textPrimary"]) == BLOOD_TEXT_PRIMARY
    assert _normalize_hex(tokens["textSecondary"]) == BLOOD_TEXT_SECONDARY

    assert _relative_luminance(tokens["background"]) < _relative_luminance(
        PRIOR_OPEN_CHROME
    )
    assert _relative_luminance(tokens["background"]) < _relative_luminance(
        PRIOR_NOIR_CHROME
    )
    assert _relative_luminance(tokens["surfaceWorkspace"]) < _relative_luminance(
        PRIOR_OPEN_WORKSPACE
    )
    assert _relative_luminance(tokens["surfaceWorkspace"]) < _relative_luminance(
        PRIOR_NOIR_WORKSPACE
    )
    assert _relative_luminance(tokens["surfaceWorkspace"]) < _relative_luminance(
        PRIOR_ATMOSPHERE_WORKSPACE
    )
    assert _relative_luminance(tokens["surface"]) < _relative_luminance(PRIOR_OPEN_PANEL)
    assert _relative_luminance(tokens["divider"]) < _relative_luminance(
        PRIOR_OPEN_DIVIDER
    )
    # Superdesign deep-black floor maps short of pure black product surfaces.
    assert _normalize_hex(tokens["background"]) != PURE_BLACK
    # Panels stay near reference zinc-black (#09090b) without opening to surface-gray.
    assert _relative_luminance(tokens["surface"]) < _relative_luminance("#18181b")


def test_qml_semantics_map_hierarchy_roles() -> None:
    mapped = theme.theme_tokens_to_qml_semantics(theme.resolve_theme("Blood"))
    tokens = theme.resolve_theme("Blood").as_dict()
    assert _normalize_hex(mapped["surfaceHeader"]) == _normalize_hex(tokens["background"])
    assert _normalize_hex(mapped["surfaceRoot"]) == _normalize_hex(
        tokens["surfaceWorkspace"]
    )
    assert _normalize_hex(mapped["surfacePanel"]) == _normalize_hex(tokens["surface"])
    assert _normalize_hex(mapped["surfaceBrowser"]) == _normalize_hex(tokens["surface"])
    assert _normalize_hex(mapped["surfaceElevated"]) == _normalize_hex(
        tokens["surfaceRaised"]
    )
    assert _normalize_hex(mapped["borderSubtle"]) == _normalize_hex(tokens["divider"])
    # Chrome and workspace must not collapse.
    assert mapped["surfaceHeader"] != mapped["surfaceRoot"]
    assert mapped["surfaceRoot"] != mapped["surfacePanel"]


def test_surface_workspace_is_not_persisted_in_custom_themes(tmp_path: Path) -> None:
    theme.create_custom_theme(
        name="Hierarchy Desk",
        base_preset="Blood",
        state_dir=tmp_path,
    )
    raw = json.loads(theme.theme_preferences_path(state_dir=tmp_path).read_text())
    stored = raw["custom_themes"]["Hierarchy Desk"]
    assert "surfaceWorkspace" not in stored
    assert "surface" not in stored
    for key in ("accent", "background", "foreground"):
        assert key in stored


def test_qml_footer_chrome_uses_surface_header_fill() -> None:
    """Footer band must paint chrome darkest — not inherit workspace root."""
    from src.workbench_qml import QML_SOURCE

    footer = QML_SOURCE.split('objectName: "programFooterBand"', 1)[1][:1200]
    assert "theme.surfaceHeader" in footer
    # Geometry / context contracts stay outside this polish.
    assert "height: 22" in QML_SOURCE.split('objectName: "programFooterBand"', 1)[0][-80:] + footer


def test_qml_calm_canvas_paints_workspace_surface_root() -> None:
    """Main workspace must not bleed pure-black PNG through a transparent canvas."""
    from src.workbench_qml import QML_SOURCE

    calm = QML_SOURCE.split('objectName: "calmCanvas"', 1)[1].split(
        "ColumnLayout", 1
    )[0]
    assert "theme.surfaceRoot" in calm
    assert 'color: "transparent"' not in calm


def test_canon_documents_atmosphere_stop_derivation() -> None:
    canon = _canon()
    derivation = canon["derivation"]
    assert derivation["atmosphereWorkspaceCore"] == (
        "mix(mix(surfaceWorkspace, accent, 0.035), foreground, 0.008)"
    )
    assert derivation["atmosphereWorkspaceMid"] == "surfaceWorkspace"
    assert derivation["atmosphereWorkspaceEdge"] == (
        "mix(surfaceWorkspace, background, 0.65)"
    )
    assert derivation["atmospherePanelCore"] == (
        "mix(mix(surface, accent, 0.03), foreground, 0.006)"
    )
    assert derivation["atmospherePanelMid"] == "surface"
    assert derivation["atmospherePanelEdge"] == (
        "mix(surface, background, 0.50)"
    )


def test_theme_core_blood_atmosphere_stops_match_canon() -> None:
    stops = theme.atmosphere_stop_colors(theme.resolve_theme("Blood"))
    assert _normalize_hex(stops["workspace"]["core"]) == BLOOD_ATMOSPHERE_WORKSPACE_CORE
    assert _normalize_hex(stops["workspace"]["mid"]) == BLOOD_ATMOSPHERE_WORKSPACE_MID
    assert _normalize_hex(stops["workspace"]["edge"]) == BLOOD_ATMOSPHERE_WORKSPACE_EDGE
    assert _normalize_hex(stops["panel"]["core"]) == BLOOD_ATMOSPHERE_PANEL_CORE
    assert _normalize_hex(stops["panel"]["mid"]) == BLOOD_ATMOSPHERE_PANEL_MID
    assert _normalize_hex(stops["panel"]["edge"]) == BLOOD_ATMOSPHERE_PANEL_EDGE
    # Soft ellipse must lift the core above the edge (depth present).
    assert _relative_luminance(stops["workspace"]["core"]) > _relative_luminance(
        stops["workspace"]["edge"]
    )
    assert _relative_luminance(stops["panel"]["core"]) > _relative_luminance(
        stops["panel"]["edge"]
    )
    # Subliminal — not a visible glow oval (Owner rejection of #1e0d11 / #1c0d10).
    assert _relative_luminance(stops["workspace"]["core"]) < _relative_luminance(
        PRIOR_VISIBLE_ATMOSPHERE_WORKSPACE_CORE
    )
    assert _relative_luminance(stops["panel"]["core"]) < _relative_luminance(
        PRIOR_VISIBLE_ATMOSPHERE_PANEL_CORE
    )
    assert (
        _relative_luminance(stops["workspace"]["core"])
        / _relative_luminance(stops["workspace"]["mid"])
        <= MAX_ATMOSPHERE_CORE_TO_MID_LUM_RATIO
    )
    assert (
        _relative_luminance(stops["panel"]["core"])
        / _relative_luminance(stops["panel"]["mid"])
        <= MAX_ATMOSPHERE_CORE_TO_MID_LUM_RATIO
    )


def test_theme_core_writes_atmosphere_png_overlays(tmp_path: Path) -> None:
    tokens = theme.resolve_theme("Blood")
    paths = theme.ensure_atmosphere_overlays(tokens, cache_dir=tmp_path)
    assert paths["workspace"].is_file()
    assert paths["panel"].is_file()
    assert paths["workspace"].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert paths["panel"].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    # Distinct overlays for workspace vs panel roles.
    assert paths["workspace"].read_bytes() != paths["panel"].read_bytes()


def test_qml_panel_family_binds_atmosphere_overlays() -> None:
    """Library, Browser, Live Kit, Harmonic Matching share Theme panel atmosphere."""
    from src.workbench_qml import QML_SOURCE

    assert "readonly property url atmosphereWorkspace: themeAuthority.atmosphereWorkspaceUrl" in QML_SOURCE
    assert "readonly property url atmospherePanel: themeAuthority.atmospherePanelUrl" in QML_SOURCE
    # Keep Screen-1 background contract: no QML gradient element types.
    assert "\n    Gradient" not in QML_SOURCE
    assert "RadialGradient" not in QML_SOURCE
    assert "LinearGradient" not in QML_SOURCE

    library = QML_SOURCE.split('objectName: "libraryPane"', 1)[1][:1600]
    assert 'objectName: "libraryNoirAtmosphere"' in library
    assert "theme.atmospherePanel" in library

    calm = QML_SOURCE.split('objectName: "calmCanvas"', 1)[1][:1600]
    assert 'objectName: "workspaceNoirAtmosphere"' in calm
    assert "theme.atmosphereWorkspace" in calm

    browser = QML_SOURCE.split('objectName: "browserPane"', 1)[1][:1600]
    assert 'objectName: "browserNoirAtmosphere"' in browser
    assert "theme.atmospherePanel" in browser

    harmony = QML_SOURCE.split('objectName: "harmonyPane"', 1)[1][:1600]
    assert 'objectName: "harmonyNoirAtmosphere"' in harmony
    assert "theme.atmospherePanel" in harmony

    live_kit = QML_SOURCE.split('objectName: "liveKitPane"', 1)[1][:1600]
    assert 'objectName: "liveKitNoirAtmosphere"' in live_kit
    assert "theme.atmospherePanel" in live_kit


def test_theme_authority_bridge_exposes_hierarchy(tmp_path: Path) -> None:
    pytest.importorskip("PySide6")
    from src.workbench_qml import _qml_theme_authority_bridge

    bridge = _qml_theme_authority_bridge(state_dir=tmp_path)
    blood = theme.resolve_theme("Blood")
    assert bridge.surfaceHeader.lower() == blood.background.lower()
    assert bridge.surfaceRoot.lower() == blood.as_dict()["surfaceWorkspace"].lower()
    assert bridge.surfacePanel.lower() == blood.surface.lower()
    assert bridge.surfaceHeader.lower() != bridge.surfaceRoot.lower()
    assert bridge.surfaceRoot.lower() != bridge.surfacePanel.lower()
    assert bridge.surfaceRoot.lower() != PURE_BLACK
    assert bridge.surfaceHeader.lower() != PURE_BLACK
    assert bridge.surfaceRoot.lower() == BLOOD_WORKSPACE
    assert bridge.textPrimary.lower() == BLOOD_TEXT_PRIMARY
    assert bridge.textSecondary.lower() == BLOOD_TEXT_SECONDARY
    workspace_url = str(bridge.atmosphereWorkspaceUrl)
    panel_url = str(bridge.atmospherePanelUrl)
    assert workspace_url.startswith("file:")
    assert panel_url.startswith("file:")
    assert workspace_url != panel_url
