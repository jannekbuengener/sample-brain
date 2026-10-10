"""#1121 Program-Chrome layout lock UX — TEST_GATE / TEST_FREEZE.

Small #1071 Slice A only: project #1070 feature + LOCKED/UNLOCKED state into
Program Chrome. No panel move, drop target, seam, or sample-DnD implementation.
"""

from __future__ import annotations

from pathlib import Path

from src.workbench_controller import WorkbenchRow
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
    LiveKitPresenter,
    Screen1QmlInteractionAdapter,
    Screen1QmlViewModel,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
QML_SOURCE = (REPO_ROOT / "src" / "workbench_qml.py").read_text(encoding="utf-8")


def _adapter(*, live_kit: LiveKitPresenter | None = None) -> Screen1QmlInteractionAdapter:
    return Screen1QmlInteractionAdapter(
        view_model=Screen1QmlViewModel.baseline("screen1-default-3panel"),
        live_kit=live_kit,
        on_preview_requested=lambda *_a, **_k: None,
        on_preview_stopped=lambda: None,
    )


def _load(adapter: Screen1QmlInteractionAdapter, state_dir: Path) -> None:
    adapter.load_feature_settings(state_dir=state_dir)
    adapter.load_workspace_layout_state(state_dir=state_dir)


def test_feature_off_projects_locked_and_rejects_unlock_without_mutating_topology(
    tmp_path: Path,
) -> None:
    save_workbench_feature_settings(
        WorkbenchFeatureSettings(workspace_panel_docking_enabled=False),
        state_dir=tmp_path,
    )
    persisted = EditDockingState(
        panel_order=("browser", "library", "harmony", "live_kit"),
        lock_state=LOCK_UNLOCKED,
    )
    assert save_edit_docking_state(persisted, state_dir=tmp_path) is True

    adapter = _adapter()
    _load(adapter, tmp_path)

    assert adapter.workspace_panel_docking_enabled is False
    assert adapter.workspace_layout_locked is True
    assert adapter.set_workspace_layout_locked(False, state_dir=tmp_path) == LOCK_LOCKED
    assert load_edit_docking_state(state_dir=tmp_path) == persisted


def test_feature_on_unlock_and_relock_persist_without_topology_change(
    tmp_path: Path,
) -> None:
    save_workbench_feature_settings(
        WorkbenchFeatureSettings(workspace_panel_docking_enabled=True),
        state_dir=tmp_path,
    )
    adapter = _adapter()
    _load(adapter, tmp_path)

    assert adapter.workspace_panel_docking_enabled is True
    assert adapter.workspace_layout_locked is True
    assert load_edit_docking_state(state_dir=tmp_path).panel_order == CANONICAL_PANEL_ORDER

    assert adapter.set_workspace_layout_locked(False, state_dir=tmp_path) == LOCK_UNLOCKED
    assert adapter.workspace_layout_locked is False
    unlocked = load_edit_docking_state(state_dir=tmp_path)
    assert unlocked.lock_state == LOCK_UNLOCKED
    assert unlocked.panel_order == CANONICAL_PANEL_ORDER

    assert adapter.set_workspace_layout_locked(True, state_dir=tmp_path) == LOCK_LOCKED
    assert adapter.workspace_layout_locked is True
    relocked = load_edit_docking_state(state_dir=tmp_path)
    assert relocked.lock_state == LOCK_LOCKED
    assert relocked.panel_order == CANONICAL_PANEL_ORDER


def test_restart_projection_uses_python_restored_lock_state(tmp_path: Path) -> None:
    save_workbench_feature_settings(
        WorkbenchFeatureSettings(workspace_panel_docking_enabled=True),
        state_dir=tmp_path,
    )
    assert save_edit_docking_state(
        EditDockingState(lock_state=LOCK_UNLOCKED),
        state_dir=tmp_path,
    ) is True

    first = _adapter()
    _load(first, tmp_path)
    second = _adapter()
    _load(second, tmp_path)

    assert first.workspace_layout_locked is False
    assert second.workspace_layout_locked is False


def test_repeated_lock_cycles_leave_panel_order_stable(tmp_path: Path) -> None:
    save_workbench_feature_settings(
        WorkbenchFeatureSettings(workspace_panel_docking_enabled=True),
        state_dir=tmp_path,
    )
    adapter = _adapter()
    _load(adapter, tmp_path)

    for _ in range(4):
        assert adapter.set_workspace_layout_locked(False, state_dir=tmp_path) == LOCK_UNLOCKED
        assert adapter.set_workspace_layout_locked(True, state_dir=tmp_path) == LOCK_LOCKED

    state = load_edit_docking_state(state_dir=tmp_path)
    assert state.panel_order == CANONICAL_PANEL_ORDER
    assert state.lock_state == LOCK_LOCKED


def test_layout_lock_does_not_mutate_live_kit_musical_projection(tmp_path: Path) -> None:
    save_workbench_feature_settings(
        WorkbenchFeatureSettings(workspace_panel_docking_enabled=True),
        state_dir=tmp_path,
    )
    presenter = LiveKitPresenter()
    row = WorkbenchRow(
        display_name="kick.wav",
        relative_path="synthetic/kick.wav",
        path="synthetic/kick.wav",
        bpm=132.0,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=2500.0,
        sample_class="one_shot",
        pred_type="Kick",
        status="ok",
        details={"duration_sec": "0.2"},
    )
    presenter.assign("Kick + Bass", "Kick", row)
    before = presenter.groups

    adapter = _adapter(live_kit=presenter)
    _load(adapter, tmp_path)
    adapter.set_workspace_layout_locked(False, state_dir=tmp_path)
    adapter.set_workspace_layout_locked(True, state_dir=tmp_path)

    assert presenter.groups == before


def test_failed_lock_write_reloads_persisted_python_truth(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from src import workbench_edit_docking

    save_workbench_feature_settings(
        WorkbenchFeatureSettings(workspace_panel_docking_enabled=True),
        state_dir=tmp_path,
    )
    assert save_edit_docking_state(EditDockingState(), state_dir=tmp_path) is True
    adapter = _adapter()
    _load(adapter, tmp_path)

    monkeypatch.setattr(workbench_edit_docking, "save_edit_docking_state", lambda *_a, **_k: False)
    assert adapter.set_workspace_layout_locked(False, state_dir=tmp_path) == LOCK_LOCKED
    assert adapter.workspace_layout_locked is True
    assert load_edit_docking_state(state_dir=tmp_path).lock_state == LOCK_LOCKED


def test_qml_preferences_hosts_quiet_python_owned_layout_lock_control() -> None:
    start = QML_SOURCE.index('objectName: "displayPreferencesPopover"')
    end = QML_SOURCE.index("workspaceRow", start)
    prefs = QML_SOURCE[start:end]

    assert 'objectName: "workspaceLayoutLockToggle"' in prefs
    assert "workspacePanelDockingEnabled" in prefs
    assert "workspaceLayoutLocked" in prefs
    assert "setWorkspaceLayoutLocked" in prefs
    assert "Layout · Locked" in prefs
    assert "Layout · Unlocked" in prefs
    assert "enabled: window.interaction.workspacePanelDockingEnabled" in prefs


def test_layout_lock_control_does_not_prebuild_panel_drag_or_drop_targets() -> None:
    start = QML_SOURCE.index('objectName: "workspaceLayoutLockToggle"')
    end = QML_SOURCE.index('objectName: "gestureRackApplyToggle"', start)
    block = QML_SOURCE[start:end]

    assert "Drag." not in block
    assert "panelMove" not in block
    assert "dropTarget" not in block
    assert "DropArea" not in block
