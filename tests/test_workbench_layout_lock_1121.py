"""#1121 Orphaned Layout Lock control removal — regression test gate.

Verifies that the orphaned Program-Chrome layout-lock toggle control and its
presentation bridge properties are completely removed from QML/Python bridges
following the docking UX cancellation in #1069.
Verifies that historical persisted docking state loads safely without error or layout
disruption.
"""

from __future__ import annotations

from pathlib import Path

from src.workbench_edit_docking import (
    CANONICAL_PANEL_ORDER,
    LOCK_LOCKED,
    LOCK_UNLOCKED,
    EditDockingState,
    load_edit_docking_state,
    save_edit_docking_state,
)
from src.workbench_feature_settings import (
    WorkbenchFeatureSettings,
    save_workbench_feature_settings,
)
from src.workbench_qml import (
    Screen1QmlInteractionAdapter,
    Screen1QmlViewModel,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
QML_SOURCE = (REPO_ROOT / "src" / "workbench_qml.py").read_text(encoding="utf-8")


def _adapter() -> Screen1QmlInteractionAdapter:
    return Screen1QmlInteractionAdapter(
        view_model=Screen1QmlViewModel.baseline("screen1-default-3panel"),
        on_preview_requested=lambda *_a, **_k: None,
        on_preview_stopped=lambda: None,
    )


def test_qml_source_no_longer_contains_layout_lock_control() -> None:
    start = QML_SOURCE.index('objectName: "displayPreferencesPopover"')
    end = QML_SOURCE.index("workspaceRow", start)
    prefs = QML_SOURCE[start:end]

    assert 'objectName: "workspaceLayoutLockToggle"' not in prefs
    assert "workspaceLayoutLockToggle" not in QML_SOURCE
    assert "workspaceLayoutLocked" not in QML_SOURCE
    assert "setWorkspaceLayoutLocked" not in QML_SOURCE
    assert "Layout · Locked" not in QML_SOURCE
    assert "Layout · Unlocked" not in QML_SOURCE


def test_adapter_and_bridge_have_no_layout_lock_presentation_properties() -> None:
    adapter = _adapter()
    assert not hasattr(adapter, "workspace_layout_locked")
    assert not hasattr(adapter, "set_workspace_layout_locked")


def test_historical_persisted_layout_lock_state_loads_safely(tmp_path: Path) -> None:
    save_workbench_feature_settings(
        WorkbenchFeatureSettings(workspace_panel_docking_enabled=True),
        state_dir=tmp_path,
    )
    persisted = EditDockingState(
        panel_order=CANONICAL_PANEL_ORDER,
        lock_state=LOCK_UNLOCKED,
    )
    assert save_edit_docking_state(persisted, state_dir=tmp_path) is True

    adapter = _adapter()
    loaded_state = adapter.load_workspace_layout_state(state_dir=tmp_path)

    # Dormant state loads cleanly without failure
    assert loaded_state.panel_order == CANONICAL_PANEL_ORDER
    assert loaded_state.lock_state == LOCK_UNLOCKED
    assert load_edit_docking_state(state_dir=tmp_path) == persisted
