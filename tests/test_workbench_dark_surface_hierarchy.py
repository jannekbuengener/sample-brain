"""Dark workspace surface hierarchy polish — FROZEN CONTRACT.

Status: TEST_FREEZE
Canon:
  - docs/assets/themes/README.md (CURRENT→TARGET table)
  - docs/assets/themes/presets.v1.json
  - docs/WORKBENCH_VISUAL_ACCEPTANCE.md (dark surface hierarchy)
  - src/workbench_theme.py (Theme Authority sole owner)

Intent: dark app with three calm depth steps — Program Chrome darkest,
Main Workspace minimally lighter, Panels subtly separated. Semantic
relations only; screenshot pixels are not absolute truth.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import workbench_theme as theme


PRESET_ORDER = ("Blood", "Carbon", "Arctic", "Rose", "Forest")
PURE_BLACK = "#000000"


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


def test_canon_documents_surface_workspace_derivation() -> None:
    canon = _canon()
    assert "surfaceWorkspace" in canon["derivation"]
    assert canon["derivation"]["surfaceWorkspace"] == (
        "mix(background, foreground, 0.025)"
    )
    for name in PRESET_ORDER:
        derived = canon["presets"][name]["derived"]
        assert "surfaceWorkspace" in derived
        assert _normalize_hex(derived["surfaceWorkspace"]) != PURE_BLACK


def test_theme_core_exposes_surface_workspace_for_all_presets() -> None:
    for name in PRESET_ORDER:
        tokens = theme.resolve_theme(name)
        as_dict = tokens.as_dict()
        assert "surfaceWorkspace" in as_dict
        expected = theme.mix_hex(tokens.background, tokens.foreground, 0.025)
        assert _normalize_hex(as_dict["surfaceWorkspace"]) == _normalize_hex(expected)
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
