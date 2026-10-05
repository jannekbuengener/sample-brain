"""V7 Asset Foundation: global Workbench background/depth freeze (#929)."""

from __future__ import annotations

import re
from pathlib import Path

from src import workbench_theme as theme
from src.workbench_qml import QML_SOURCE


V7_TOKENS = {
    "chrome": "#020203",
    "workspace": "#040405",
    "surface": "#080809",
    "raised": "#101011",
    "hover": "#131314",
    "hairline": "#19191a",
    "accent": "#8f0e24",
    "selected": "#21050a",
    "foreground": "#e4e6ea",
    "muted": "#68696b",
}


def _qml_block(object_name: str, *, size: int = 1400) -> str:
    marker = f'objectName: "{object_name}"'
    start = QML_SOURCE.index(marker)
    return QML_SOURCE[start : start + size]


def test_v7_canon_records_the_approved_traceability_and_exact_tokens() -> None:
    canon = (
        Path(__file__).resolve().parents[1] / "docs" / "assets" / "themes" / "README.md"
    ).read_text(encoding="utf-8")

    assert "TOKEN_FREEZE_PASS" in canon
    assert "47e8bb1a-efce-43bd-a97f-c05c9750d726" in canon
    assert "2fa91842-f07f-4d70-9d12-de9622744191" in canon
    assert "Accepted version: `7`" in canon
    assert "solid fills only" in canon.lower()
    assert "not** authorized by #929/#930" in canon
    assert "linear-gradient" not in canon.lower()
    for token in V7_TOKENS.values():
        assert token in canon


def test_v7_default_blood_theme_tokens_remain_exact() -> None:
    tokens = theme.resolve_theme("Blood").as_dict()
    actual = {
        "chrome": tokens["background"].lower(),
        "workspace": tokens["surfaceWorkspace"].lower(),
        "surface": tokens["surface"].lower(),
        "raised": tokens["surfaceRaised"].lower(),
        "hover": tokens["hover"].lower(),
        "hairline": tokens["divider"].lower(),
        "accent": tokens["accent"].lower(),
        "selected": tokens["selected"].lower(),
        "foreground": tokens["foreground"].lower(),
        "muted": tokens["textSecondary"].lower(),
    }

    assert actual == V7_TOKENS


def test_v7_root_uses_chrome_while_workspace_uses_workspace_depth() -> None:
    root_start = QML_SOURCE.index("ApplicationWindow {")
    root_end = QML_SOURCE.index("QtObject {", root_start)
    root = QML_SOURCE[root_start:root_end]

    assert "color: theme.surfaceHeader" in root
    assert "color: theme.surfaceRoot" not in root

    background_match = re.search(
        r'Image\s*\{[^}]*objectName:\s*"screen1Background".*?\}',
        QML_SOURCE,
        re.DOTALL,
    )
    assert background_match is not None
    historical_background = background_match.group(0)
    assert "visible: false" in historical_background
    assert "opacity:" not in historical_background.casefold()

    assert "color: theme.surfaceRoot" in _qml_block("calmCanvas")
    assert "color: theme.surfaceRoot" in _qml_block("analysisWorkingSurface")
    assert "color: theme.surfacePanel" in _qml_block("libraryPane")
    assert "color: theme.surfaceBrowser" in _qml_block("browserPane")
    assert "color: theme.surfacePanel" in _qml_block("harmonyPane")
    assert "color: theme.surfacePanel" in _qml_block("bottomRackPane")


def test_v7_touched_qml_style_has_no_foreign_or_unapproved_fallback_colors() -> None:
    source = QML_SOURCE.casefold()

    assert "#6f9fbf" not in source
    assert "rgba(0,0,0" not in source
    assert "lineargradient" not in source
    assert "radialgradient" not in source


def test_v7_background_slice_keeps_single_workspace_pane_geometry_contracts() -> None:
    """Background token changes must not alter the four protected pane geometries."""
    library = _qml_block("libraryPane")
    browser = _qml_block("browserPane")
    harmony = _qml_block("harmonyPane")
    bottom_rack = _qml_block("bottomRackPane")

    assert "width: layoutModel.libraryWidth" in library
    assert "height: parent.height" in library
    assert "width: visible ? layoutModel.browserWidth : 0" in browser
    assert "height: parent.height" in browser
    assert "width: layoutModel.harmonyWidth" in harmony
    assert "height: parent.height" in harmony
    assert "width: parent.width" in bottom_rack
    assert "height: bottomExpanded" in bottom_rack
    assert "bottomRackHeightRatio" in bottom_rack
