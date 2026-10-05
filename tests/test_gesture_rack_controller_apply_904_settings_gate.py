"""#904 SETTINGS_GATE — freeze FEATURE_SETTINGS_OWNER_BLOCKED evidence.

No product mutation is authorized while this gate remains blocked.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from src.workbench_channel_rack import ChannelRackController
from src.workbench_controller import WorkbenchViewSettings
from src.workbench_display_preferences import DisplayPreferences, WorkspacePreset
from src.workbench_theme import _THEME_PREFERENCES_FILENAME

REPO_ROOT = Path(__file__).resolve().parents[1]
SLICE8_DOC = (
    REPO_ROOT / "docs" / "GESTURE_RACK_CONTROLLER_APPLY_RND_SLICE8.md"
)
DISPLAY_PREFS_DOC = REPO_ROOT / "docs" / "WORKBENCH_DISPLAY_PREFERENCES.md"
CANON_INDEX = REPO_ROOT / "docs" / "CANON_INDEX.md"

VIEW_SETTINGS_FIELD_NAMES = frozenset(
    {
        "show_view_toolbar",
        "show_search",
        "show_filters",
        "show_library_manage",
        "show_waveform_tools",
    }
)
DISPLAY_PREFERENCES_FIELD_NAMES = frozenset(
    {"density_mode", "motion_mode", "schema_version"}
)
WORKSPACE_PRESET_FIELD_NAMES = frozenset(
    {
        "version",
        "panel_ratios",
        "panel_visibility",
        "density_mode",
        "motion_mode",
        "startup_source_node_id",
    }
)
FORBIDDEN_FUNCTIONAL_KEYS = frozenset(
    {
        "gesture_rack_apply",
        "gesture_rack_apply_enabled",
        "gesture_apply_enabled",
        "feature_gesture_rack_apply",
        "enable_gesture_rack_apply",
        "vocal_gesture_apply",
        "beatbox_apply",
    }
)


def test_slice8_doc_records_feature_settings_owner_blocked():
    text = SLICE8_DOC.read_text(encoding="utf-8")
    assert "FEATURE_SETTINGS_OWNER_BLOCKED" in text
    assert "SETTINGS_GATE" in text
    assert "No product mutation" in text or "no product mutation" in text.lower()
    assert "WorkbenchViewSettings" in text
    assert "DisplayPreferences" in text
    assert "do not invent a second ad-hoc settings subsystem" in text.lower() or (
        "Do not invent a second ad-hoc settings subsystem" in text
    )


def test_workbench_view_settings_remain_view_visibility_only():
    names = {f.name for f in fields(WorkbenchViewSettings)}
    assert names == VIEW_SETTINGS_FIELD_NAMES
    assert names.isdisjoint(FORBIDDEN_FUNCTIONAL_KEYS)
    assert all(name.startswith("show_") for name in names)


def test_display_preferences_remain_density_motion_only():
    names = {f.name for f in fields(DisplayPreferences)}
    assert names == DISPLAY_PREFERENCES_FIELD_NAMES
    assert names.isdisjoint(FORBIDDEN_FUNCTIONAL_KEYS)


def test_workspace_preset_remains_ui_workspace_scope_only():
    names = {f.name for f in fields(WorkspacePreset)}
    assert names == WORKSPACE_PRESET_FIELD_NAMES
    assert names.isdisjoint(FORBIDDEN_FUNCTIONAL_KEYS)


def test_display_preferences_canon_excludes_app_wide_preferences_redesign():
    text = DISPLAY_PREFS_DOC.read_text(encoding="utf-8")
    assert "General app-wide Preferences redesign" in text
    assert "header overflow" in text.lower() or "Header overflow" in text


def test_canon_index_lists_display_preferences_not_functional_feature_registry():
    text = CANON_INDEX.read_text(encoding="utf-8")
    assert "WORKBENCH_DISPLAY_PREFERENCES.md" in text
    assert "density/motion/layout" in text
    assert "functional feature-toggle" not in text.lower()


def test_theme_preferences_filename_is_appearance_scoped():
    assert _THEME_PREFERENCES_FILENAME == "screen1_theme_preferences.json"


def test_canonical_functional_settings_owner_exists_without_ad_hoc_gesture_modules():
    """#910 delivered the canonical owner; ad-hoc gesture-local stores remain forbidden."""
    canonical = REPO_ROOT / "src" / "workbench_feature_settings.py"
    assert canonical.is_file()
    text = canonical.read_text(encoding="utf-8")
    assert "class WorkbenchFeatureSettings" in text
    assert "gesture_rack_apply_enabled" in text
    ad_hoc = [
        REPO_ROOT / "src" / "workbench_functional_settings.py",
        REPO_ROOT / "src" / "gesture_feature_settings.py",
        REPO_ROOT / "src" / "feature_toggles.py",
        REPO_ROOT / "src" / "workbench_settings.py",
    ]
    missing = [path for path in ad_hoc if not path.is_file()]
    assert missing == ad_hoc


def test_channel_rack_controller_still_has_no_gesture_apply_seam_after_settings_owner():
    """Historical #904 meaning: settings owner alone ≠ gesture apply delivery.

    #904 stopped at FEATURE_SETTINGS_OWNER_BLOCKED. #910 later delivered the
    canonical settings owner without implementing apply mutation. #921 owns the
    separate guarded apply seam. Keep historical blocker narrative and forbid
    treating restore_state / settings I/O as live apply shortcuts.
    """
    text = SLICE8_DOC.read_text(encoding="utf-8")
    assert "FEATURE_SETTINGS_OWNER_BLOCKED" in text
    assert "No product mutation" in text or "no product mutation" in text.lower()

    settings_src = (
        REPO_ROOT / "src" / "workbench_feature_settings.py"
    ).read_text(encoding="utf-8")
    assert "apply_gesture_integration_plan" not in settings_src
    assert "ChannelRackController" not in settings_src

    public_names = {
        name
        for name in dir(ChannelRackController)
        if not name.startswith("_") and callable(getattr(ChannelRackController, name))
    }
    # restore_state remains compose/restore — not a live apply substitute.
    assert "restore_state" in public_names


def test_slice8_doc_forbids_restore_state_as_live_apply_and_external_state_writes():
    text = SLICE8_DOC.read_text(encoding="utf-8")
    assert "restore_state()" in text
    assert "live-product apply" in text or "live apply" in text
    assert "controller._state" in text
    assert "workbench_session_store" in text
    # Historical exit remains documented even after #910 unblocks the owner gap.
    assert "FEATURE_SETTINGS_OWNER_BLOCKED" in text
