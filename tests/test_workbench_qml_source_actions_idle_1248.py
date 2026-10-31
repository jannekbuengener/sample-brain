"""#1248 reopen: selected idle source must not permanently reserve … width."""

from __future__ import annotations

import re

import pytest

from src import workbench_qml

QML = workbench_qml.QML_SOURCE


def _actions_block() -> str:
    return QML.split('objectName: "librarySourceActionsButton"', 1)[1].split(
        'objectName: "libraryContentHost"', 1
    )[0]


def _source_row_block() -> str:
    return QML.split("id: libraryDelegate", 1)[1].split(
        'objectName: "librarySourceActionsButton"', 1
    )[0]


def _metrics_block() -> str:
    return QML.split("id: libraryMetrics", 1)[1].split("// #770", 1)[0]


def _visible_expression() -> str:
    block = _actions_block()
    match = re.search(
        r"visible:\s*((?:.|\n)*?)(?=\n\s*text:)",
        block,
    )
    assert match is not None, "sourceActionsButton.visible expression missing"
    return re.sub(r"\s+", " ", match.group(1)).strip()


@pytest.mark.parametrize(
    "forbidden",
    [
        "libraryDelegate.current && libraryTree.activeFocus",
        "libraryDelegate.current",
        "selectedLibraryNodeId",
    ],
)
def test_1248_selected_idle_must_not_force_actions_visible(forbidden: str) -> None:
    """Selection/current/tree focus alone must not keep … visible."""
    visible = _visible_expression()
    assert forbidden not in visible


def test_1248_unselected_and_selected_share_idle_visibility_contract() -> None:
    visible = _visible_expression()
    assert 'model.kind === "registered_root"' in visible
    assert "sourceRowHover.hovered" in visible
    assert "activeFocus" in visible
    assert "canRemoveSource(model.nodeId)" in visible
    # No selection/current term — selected idle == unselected idle.
    assert "libraryDelegate.current" not in visible
    assert "libraryTree.activeFocus" not in visible


def test_1248_hover_or_direct_button_focus_may_reveal_actions() -> None:
    visible = _visible_expression()
    assert "sourceRowHover.hovered" in visible
    assert "activeFocus" in visible


def test_1248_narrow_hides_actions_and_gives_label_priority() -> None:
    metrics = _metrics_block()
    assert "sourceActionsWidth:" in metrics
    assert "sourceActionsGap:" in metrics
    assert "sourceLabelMinUsefulWidth:" in metrics
    assert "sourceActionsRevealMinWidth:" in metrics
    visible = _visible_expression()
    assert "sourceActionsWidthAvailable" in visible or "sourceActionsRevealMinWidth" in visible


def test_1248_hidden_actions_do_not_reserve_layout_width() -> None:
    block = _actions_block()
    # When invisible, Layout must collapse — no artificial reservation.
    assert "Layout.preferredWidth: visible ?" in block or "Layout.preferredWidth: sourceActionsButton.visible ?" in block
    assert "0" in block
    assert "Layout.maximumWidth: visible ?" in block or "Layout.maximumWidth: sourceActionsButton.visible ?" in block


def test_1248_label_action_gap_is_text_space() -> None:
    row = QML.split("id: libraryDelegate", 1)[1].split("Keys.onPressed:", 1)[0]
    assert "spacing: libraryMetrics.sourceActionsGap" in row
    metrics = _metrics_block()
    gap = re.search(r"sourceActionsGap:\s*(\d+)", metrics)
    assert gap is not None
    assert int(gap.group(1)) >= 4


def test_1248_source_row_height_density_unchanged() -> None:
    metrics = _metrics_block()
    assert "sourceRowHeight: 36" in metrics
    assert "rowPitch: 36" in metrics


def test_1248_remove_refresh_command_ownership_unchanged() -> None:
    block = _actions_block()
    assert "prepareRemoveSourceForNode(model.nodeId)" in block
    assert "librarySourceContextMenu.open()" in block
    assert "canRemoveSource(model.nodeId)" in block
