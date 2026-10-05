"""#910 Workbench functional feature settings — TEST_GATE (frozen after RED)."""

from __future__ import annotations

import inspect
import json
from dataclasses import fields
from pathlib import Path

import pytest

from src.workbench_controller import (
    WorkbenchViewSettings,
    load_workbench_view_settings,
    save_workbench_view_settings,
    workbench_view_settings_file,
)
from src.workbench_display_preferences import (
    load_display_preferences,
    save_display_preferences,
)
from src.workbench_feature_settings import (
    FEATURE_SETTINGS_SCHEMA_VERSION,
    WorkbenchFeatureSettings,
    load_workbench_feature_settings,
    replace_workbench_feature_settings,
    save_workbench_feature_settings,
    workbench_feature_settings_path,
)
from src.workbench_qml import Screen1QmlInteractionAdapter, Screen1QmlViewModel

REPO_ROOT = Path(__file__).resolve().parents[1]
QML_SOURCE = (REPO_ROOT / "src" / "workbench_qml.py").read_text(encoding="utf-8")
CONTRACT_DOC = REPO_ROOT / "docs" / "WORKBENCH_FEATURE_SETTINGS.md"
SLICE8_DOC = (
    REPO_ROOT / "docs" / "GESTURE_RACK_CONTROLLER_APPLY_RND_SLICE8.md"
)


def test_contract_doc_freezes_canonical_owner_and_default_disabled():
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    assert "WorkbenchFeatureSettings" in text
    assert "gesture_rack_apply_enabled" in text
    assert "workbench_feature_settings.json" in text
    assert "False" in text or "disabled" in text.lower()
    assert "CANONICAL_FUNCTIONAL_SETTINGS_OWNER_VIABLE" in text
    assert "apply_gesture_integration_plan" in text
    assert "Do **not** implement" in text or "does **not** implement" in text.lower()


def test_default_settings_object_has_gesture_rack_apply_disabled():
    settings = WorkbenchFeatureSettings()
    assert settings.gesture_rack_apply_enabled is False
    assert settings.schema_version == FEATURE_SETTINGS_SCHEMA_VERSION
    assert {f.name for f in fields(WorkbenchFeatureSettings)} == {
        "gesture_rack_apply_enabled",
        "schema_version",
    }


def test_serialized_default_is_deterministic_and_versioned(tmp_path: Path):
    settings = WorkbenchFeatureSettings()
    assert save_workbench_feature_settings(settings, state_dir=tmp_path) is True
    path = workbench_feature_settings_path(state_dir=tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw == {
        "schema_version": FEATURE_SETTINGS_SCHEMA_VERSION,
        "gesture_rack_apply_enabled": False,
    }
    assert path.name == "workbench_feature_settings.json"


def test_enable_save_load_round_trip(tmp_path: Path):
    enabled = replace_workbench_feature_settings(
        WorkbenchFeatureSettings(),
        gesture_rack_apply_enabled=True,
    )
    assert enabled.gesture_rack_apply_enabled is True
    assert save_workbench_feature_settings(enabled, state_dir=tmp_path) is True
    loaded = load_workbench_feature_settings(state_dir=tmp_path)
    assert loaded == enabled
    assert loaded.gesture_rack_apply_enabled is True


def test_disable_save_load_round_trip(tmp_path: Path):
    enabled = WorkbenchFeatureSettings(gesture_rack_apply_enabled=True)
    save_workbench_feature_settings(enabled, state_dir=tmp_path)
    disabled = replace_workbench_feature_settings(
        enabled, gesture_rack_apply_enabled=False
    )
    save_workbench_feature_settings(disabled, state_dir=tmp_path)
    loaded = load_workbench_feature_settings(state_dir=tmp_path)
    assert loaded.gesture_rack_apply_enabled is False


def test_malformed_file_fails_closed_to_default(tmp_path: Path):
    path = workbench_feature_settings_path(state_dir=tmp_path)
    path.write_text("{not-json", encoding="utf-8")
    loaded = load_workbench_feature_settings(state_dir=tmp_path)
    assert loaded == WorkbenchFeatureSettings()


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": FEATURE_SETTINGS_SCHEMA_VERSION},
        {
            "schema_version": FEATURE_SETTINGS_SCHEMA_VERSION,
            "gesture_rack_apply_enabled": "yes",
        },
        {
            "schema_version": FEATURE_SETTINGS_SCHEMA_VERSION,
            "gesture_rack_apply_enabled": 1,
        },
        {
            "schema_version": 999,
            "gesture_rack_apply_enabled": True,
        },
        ["not", "a", "mapping"],
    ],
)
def test_invalid_payload_fails_closed_without_enabling(tmp_path: Path, payload):
    path = workbench_feature_settings_path(state_dir=tmp_path)
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_workbench_feature_settings(state_dir=tmp_path)
    assert loaded.gesture_rack_apply_enabled is False


def test_unknown_future_keys_do_not_silently_enable(tmp_path: Path):
    path = workbench_feature_settings_path(state_dir=tmp_path)
    path.write_text(
        json.dumps(
            {
                "schema_version": FEATURE_SETTINGS_SCHEMA_VERSION,
                "gesture_rack_apply_enabled": False,
                "future_super_feature": True,
                "gesture_rack_apply": True,
            }
        ),
        encoding="utf-8",
    )
    loaded = load_workbench_feature_settings(state_dir=tmp_path)
    assert loaded.gesture_rack_apply_enabled is False
    assert not hasattr(loaded, "future_super_feature")


def test_functional_settings_are_separate_from_view_settings(tmp_path: Path):
    feature_names = {f.name for f in fields(WorkbenchFeatureSettings)}
    view_names = {f.name for f in fields(WorkbenchViewSettings)}
    assert feature_names.isdisjoint(view_names)
    assert "gesture_rack_apply_enabled" not in view_names
    assert all(name.startswith("show_") for name in view_names)

    save_workbench_feature_settings(
        WorkbenchFeatureSettings(gesture_rack_apply_enabled=True),
        state_dir=tmp_path,
    )
    save_workbench_view_settings(
        WorkbenchViewSettings(show_search=False),
        state_dir=tmp_path,
    )
    assert workbench_feature_settings_path(state_dir=tmp_path) != workbench_view_settings_file(
        state_dir=tmp_path
    )
    assert load_workbench_feature_settings(state_dir=tmp_path).gesture_rack_apply_enabled is True
    assert load_workbench_view_settings(state_dir=tmp_path).show_search is False


def test_changing_functional_settings_does_not_mutate_display_or_view(tmp_path: Path):
    save_display_preferences(
        {"density_mode": "compact", "motion_mode": "reduced"},
        state_dir=tmp_path,
    )
    save_workbench_view_settings(
        WorkbenchViewSettings(show_filters=True),
        state_dir=tmp_path,
    )
    save_workbench_feature_settings(
        WorkbenchFeatureSettings(gesture_rack_apply_enabled=True),
        state_dir=tmp_path,
    )
    assert load_display_preferences(state_dir=tmp_path).motion_mode == "reduced"
    assert load_workbench_view_settings(state_dir=tmp_path).show_filters is True


def test_changing_view_display_settings_does_not_mutate_functional(tmp_path: Path):
    save_workbench_feature_settings(
        WorkbenchFeatureSettings(gesture_rack_apply_enabled=True),
        state_dir=tmp_path,
    )
    save_display_preferences(
        {"density_mode": "compact", "motion_mode": "off"},
        state_dir=tmp_path,
    )
    save_workbench_view_settings(
        WorkbenchViewSettings(show_waveform_tools=True),
        state_dir=tmp_path,
    )
    assert load_workbench_feature_settings(state_dir=tmp_path).gesture_rack_apply_enabled is True


def test_adapter_exposes_persisted_gesture_rack_apply_flag(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_feature_settings(
        WorkbenchFeatureSettings(gesture_rack_apply_enabled=True),
        state_dir=tmp_path,
    )
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        on_preview_requested=lambda *_a, **_k: None,
        on_preview_stopped=lambda: None,
    )
    adapter.load_feature_settings(state_dir=tmp_path)
    assert adapter.gesture_rack_apply_enabled is True

    adapter.set_gesture_rack_apply_enabled(False, state_dir=tmp_path)
    assert adapter.gesture_rack_apply_enabled is False
    assert load_workbench_feature_settings(state_dir=tmp_path).gesture_rack_apply_enabled is False

    adapter.set_gesture_rack_apply_enabled(True, state_dir=tmp_path)
    assert adapter.gesture_rack_apply_enabled is True
    reloaded = load_workbench_feature_settings(state_dir=tmp_path)
    assert reloaded.gesture_rack_apply_enabled is True


def test_settings_change_does_not_mutate_rack_or_call_apply_seam(tmp_path: Path):
    from src.workbench_channel_rack import ChannelRackController

    assert not hasattr(ChannelRackController, "apply_gesture_integration_plan")
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        on_preview_requested=lambda *_a, **_k: None,
        on_preview_stopped=lambda: None,
    )
    before = inspect.getsource(Screen1QmlInteractionAdapter.set_gesture_rack_apply_enabled)
    assert "apply_gesture_integration_plan" not in before
    assert "restore_state" not in before
    adapter.set_gesture_rack_apply_enabled(True, state_dir=tmp_path)
    # No channel rack controller is attached; settings persist alone.
    assert load_workbench_feature_settings(state_dir=tmp_path).gesture_rack_apply_enabled is True


def test_qml_hosts_functional_section_distinct_from_appearance():
    start = QML_SOURCE.index('objectName: "displayPreferencesPopover"')
    end = QML_SOURCE.index("workspaceRow", start)
    prefs = QML_SOURCE[start:end]
    assert "Functional" in prefs
    assert 'objectName: "gestureRackApplyToggle"' in prefs
    assert "gestureRackApplyEnabled" in prefs
    assert "setGestureRackApplyEnabled" in prefs
    # Appearance / Motion remain present and labeled separately.
    assert "Appearance" in prefs
    assert "Motion" in prefs
    assert prefs.index("Appearance") < prefs.index("Functional")


def test_no_direct_gesture_module_json_ownership():
    gesture_integration = (
        REPO_ROOT / "src" / "gesture_rack_integration.py"
    ).read_text(encoding="utf-8")
    assert "workbench_feature_settings" not in gesture_integration
    assert "workbench_feature_settings.json" not in gesture_integration


def test_historical_904_blocker_doc_preserved():
    text = SLICE8_DOC.read_text(encoding="utf-8")
    assert "FEATURE_SETTINGS_OWNER_BLOCKED" in text
    assert "No product mutation" in text or "no product mutation" in text.lower()
