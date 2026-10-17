"""Review regressions for #1080 C2a accessibility wiring."""

from src.workbench_qml import QML_SOURCE


def test_group_block_accessible_press_routes_same_c1_intent():
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split(
        'id: arrangementStageHeader', 1
    )[0]
    assert stage.count('Accessible.role: Accessible.Button') == 1
    assert stage.count('Accessible.onPressAction:') == 1
    access_region = stage.split('Accessible.onPressAction:', 1)[1].split(
        'Label {', 1
    )[0]
    assert 'if (cell.interactive)' in access_region
    assert (
        'window.arrangement.toggleArrangementGroupBlock('
        'arrangementGroupRow.groupId, arrangementGroupBlock.blockIndex)'
    ) in access_region
    # Accessibility must invoke the same Python-routed intent as pointer/keyboard,
    # never mutate local musical truth.
    assert 'enabled = !enabled' not in stage