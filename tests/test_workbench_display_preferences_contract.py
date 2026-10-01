"""#696 Screen-1 display preferences — FROZEN RED CONTRACT.

Status: TEST_FREEZE
Docs: docs/WORKBENCH_DISPLAY_PREFERENCES.md

These tests freeze product behaviour for #696. Implementation must satisfy them
without weakening assertions. Failures must come from missing product behaviour.

Public operations may live on any authorized seam from the contract:
- src.workbench_qml_startup (startup preset load/resolve/write)
- src.workbench_layout_solver / src.workbench_qml_elastic (ratios)
- src.workbench_qml (header overflow + preference bindings)
- optional façade module is allowed but not required
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from src.workbench_layout_solver import (
    CANONICAL_DEFAULT_RATIOS,
    load_layout_preferences,
    save_layout_preferences,
)
from src.workbench_qml import QML_SOURCE, Screen1QmlInteractionAdapter, Screen1QmlViewModel
from src.workbench_qml_startup import (
    SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
    WorkspaceMode,
    load_startup_preset,
    resolve_launch_workspace,
    save_startup_preset_for_tests,
    workbench_startup_preset_file,
)
from src.workbench_transport_ui import PreviewPlaybackSnapshot
from src.workbench_visual_acceptance import REQUIRED_STATE_IDS_V2

# Authorized seams from docs/WORKBENCH_DISPLAY_PREFERENCES.md (+ optional façade).
_AUTHORIZED_SEAMS = (
    "src.workbench_display_preferences",
    "src.workbench_qml_startup",
    "src.workbench_layout_solver",
    "src.workbench_qml_elastic",
    "src.workbench_qml",
)

# Existing #693/#694 filenames — used only to distinguish new #696 persistence files.
_KNOWN_NON_DISPLAY_JSON = frozenset(
    {
        "screen1_layout_preferences.json",
        "screen1_startup_preset.json",
    }
)

# Semantic QML affordance ids — frozen owner decision, not pixel geometry.
PREFERENCES_OVERFLOW_OBJECT_NAME = "displayPreferencesOverflow"
PREFERENCES_POPOVER_OBJECT_NAME = "displayPreferencesPopover"

FORBIDDEN_PRESET_KEYS = frozenset(
    {
        "selected_index",
        "selected_browser_index",
        "browser_selection",
        "sample_selection",
        "preview_active",
        "preview_state",
        "preview_progress",
        "transport_state",
        "harmonic_results",
        "harmonic_selection",
        "harmonic_anchor",
        "scroll_position",
        "scroll_y",
        "library_revealed",
        "audition_state",
        "live_kit_snapshot",
        "absolute_source_path",
        "private_sample_path",
    }
)


def _loaded_seams() -> list[Any]:
    modules: list[Any] = []
    for name in _AUTHORIZED_SEAMS:
        if importlib.util.find_spec(name) is None:
            continue
        modules.append(importlib.import_module(name))
    return modules


def _resolve_op(name: str) -> Callable[..., Any]:
    """Resolve a public #696 operation from any authorized seam."""
    for module in _loaded_seams():
        value = getattr(module, name, None)
        if callable(value):
            return value
    pytest.fail(
        f"EXPECTED_RED: #{696} operation {name!r} not implemented on authorized seams "
        f"{_AUTHORIZED_SEAMS}",
        pytrace=False,
    )


def _api() -> SimpleNamespace:
    """Behavioural API surface — module placement is not frozen."""
    return SimpleNamespace(
        normalize_motion_mode=_resolve_op("normalize_motion_mode"),
        normalize_density_mode=_resolve_op("normalize_density_mode"),
        save_display_preferences=_resolve_op("save_display_preferences"),
        load_display_preferences=_resolve_op("load_display_preferences"),
        save_workspace_preset=_resolve_op("save_workspace_preset"),
        load_workspace_preset=_resolve_op("load_workspace_preset"),
        set_as_startup=_resolve_op("set_as_startup"),
        clear_startup_designation=_resolve_op("clear_startup_designation"),
        reset_layout=_resolve_op("reset_layout"),
        return_to_clean_start=_resolve_op("return_to_clean_start"),
    )


def _json_files(state_dir: Path) -> set[Path]:
    return {p.resolve() for p in state_dir.rglob("*.json") if p.is_file()}


def _new_prefs_json_after(state_dir: Path, before: set[Path]) -> Path:
    after = _json_files(state_dir)
    created = [
        p
        for p in sorted(after - before)
        if p.name not in _KNOWN_NON_DISPLAY_JSON
    ]
    if not created:
        pytest.fail(
            "EXPECTED_RED: #696 persistence did not create a preferences/preset JSON file",
            pytrace=False,
        )
    return created[0]


def _write_corrupt_display_prefs(api: SimpleNamespace, state_dir: Path, payload: str) -> Path:
    before = _json_files(state_dir)
    api.save_display_preferences(
        {"density_mode": "compact", "motion_mode": "on"},
        state_dir=state_dir,
    )
    path = _new_prefs_json_after(state_dir, before)
    path.write_text(payload, encoding="utf-8")
    return path


# --- Baseline guards that must stay green without #696 product code ----------


def test_layout_preferences_alone_do_not_auto_resume_source(tmp_path: Path) -> None:
    """Persisted ratios alone do not invent a Source (library authority required)."""
    save_layout_preferences(
        {
            "library": 0.12,
            "browser": 0.60,
            "harmony": 0.14,
            "livekit": 0.14,
        },
        state_dir=tmp_path,
    )
    loaded = load_layout_preferences(state_dir=tmp_path)
    assert loaded.ratios["browser"] == pytest.approx(0.60, abs=1e-9)
    launch = resolve_launch_workspace(preset=None)
    assert launch.mode is WorkspaceMode.CLEAN_START
    assert launch.source_node_id is None
    assert launch.browser_materialized is False
    assert launch.harmonic_visible is False


def test_missing_startup_designation_without_persisted_sources_is_clean_start(
    tmp_path: Path,
) -> None:
    result = load_startup_preset(state_dir=tmp_path)
    assert result.preset is None
    launch = resolve_launch_workspace(preset=result.preset)
    assert launch.mode is WorkspaceMode.CLEAN_START
    assert launch.source_node_id is None


def test_v2_acceptance_state_ids_remain_authoritative() -> None:
    assert REQUIRED_STATE_IDS_V2 == (
        "screen1-clean-start",
        "screen1-active-source",
        "screen1-harmonic-open",
        "screen1-elastic-resized",
    )
    assert "screen1-preferences" not in REQUIRED_STATE_IDS_V2
    assert "screen1-display-preferences" not in REQUIRED_STATE_IDS_V2


def test_no_permanent_settings_bar_in_qml() -> None:
    source = QML_SOURCE
    assert 'objectName: "settingsBar"' not in source
    assert 'objectName: "settingsStrip"' not in source
    assert 'objectName: "toolsPanel"' not in source
    assert 'objectName: "permanentSettings"' not in source


def test_motion_off_clears_playhead_projection_without_second_clock() -> None:
    """#738 seam: Motion Off suppresses playhead presentation, not preview authority."""
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")

    def _snap() -> PreviewPlaybackSnapshot:
        return PreviewPlaybackSnapshot(
            playing=True,
            sample_path="C:/samples/kick.wav",
            position_ms=250,
            duration_ms=1000,
            progress=0.25,
            playback_instance_id=7,
        )

    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        on_preview_requested=lambda *_a, **_k: None,
        on_preview_stopped=lambda: None,
        on_preview_snapshot=_snap,
    )
    adapter._preview_active = True  # noqa: SLF001 — contract seam
    adapter.set_waveform_motion_mode("off")
    snap = adapter.preview_playback_snapshot()
    assert snap.playing is False
    assert snap.progress == 0.0
    assert snap == PreviewPlaybackSnapshot.idle()
    assert "Date.now" not in QML_SOURCE
    assert "performance.now" not in QML_SOURCE


# --- #696 product RED contracts (FROZEN) ------------------------------------


def test_motion_and_density_vocabulary_is_frozen() -> None:
    api = _api()
    assert api.normalize_motion_mode("on") == "on"
    assert api.normalize_motion_mode("reduced") == "reduced"
    assert api.normalize_motion_mode("off") == "off"
    assert api.normalize_motion_mode("full") == "on"
    assert api.normalize_motion_mode("FULL") == "on"
    assert api.normalize_motion_mode("unknown") == "on"
    assert api.normalize_motion_mode("") == "on"
    assert api.normalize_density_mode("compact") == "compact"
    assert api.normalize_density_mode("comfortable") == "compact"
    assert api.normalize_density_mode("weird") == "compact"


@pytest.mark.parametrize("mode", ["on", "reduced", "off"])
def test_motion_round_trip(tmp_path: Path, mode: str) -> None:
    api = _api()
    api.save_display_preferences(
        {"motion_mode": mode, "density_mode": "compact"},
        state_dir=tmp_path,
    )
    loaded = api.load_display_preferences(state_dir=tmp_path)
    assert loaded.motion_mode == mode
    assert loaded.density_mode == "compact"


def test_legacy_motion_full_loads_as_on_and_never_rewritten(tmp_path: Path) -> None:
    api = _api()
    path = _write_corrupt_display_prefs(
        api,
        tmp_path,
        json.dumps(
            {
                "schema_version": 1,
                "density_mode": "compact",
                "motion_mode": "full",
            }
        ),
    )
    loaded = api.load_display_preferences(state_dir=tmp_path)
    assert loaded.motion_mode == "on"
    api.save_display_preferences(
        {"motion_mode": loaded.motion_mode, "density_mode": loaded.density_mode},
        state_dir=tmp_path,
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["motion_mode"] == "on"
    assert "full" not in json.dumps(raw)


@pytest.mark.parametrize("token", ["bounce", "", "teleport", "unknown"])
def test_unknown_motion_token_fails_closed_to_on(tmp_path: Path, token: str) -> None:
    api = _api()
    assert api.normalize_motion_mode(token) == "on"
    _write_corrupt_display_prefs(
        api,
        tmp_path,
        json.dumps(
            {
                "schema_version": 1,
                "density_mode": "compact",
                "motion_mode": token,
            }
        ),
    )
    loaded = api.load_display_preferences(state_dir=tmp_path)
    assert loaded.motion_mode == "on"


def test_density_compact_round_trip_excludes_comfortable_product_mode(
    tmp_path: Path,
) -> None:
    api = _api()
    api.save_display_preferences(
        {"density_mode": "compact", "motion_mode": "on"},
        state_dir=tmp_path,
    )
    assert api.load_display_preferences(state_dir=tmp_path).density_mode == "compact"
    assert api.normalize_density_mode("comfortable") == "compact"
    # Comfortable must not survive as a stored product value.
    api.save_display_preferences(
        {"density_mode": "comfortable", "motion_mode": "on"},
        state_dir=tmp_path,
    )
    assert api.load_display_preferences(state_dir=tmp_path).density_mode == "compact"


def test_workspace_preset_round_trip_stable_fields_only(tmp_path: Path) -> None:
    api = _api()
    payload = {
        "version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
        "panel_ratios": dict(CANONICAL_DEFAULT_RATIOS),
        "panel_visibility": {
            "library": True,
            "browser": True,
            "harmony": False,
            "livekit": True,
        },
        "density_mode": "compact",
        "motion_mode": "reduced",
        "startup_source_node_id": None,
    }
    api.save_workspace_preset(payload, state_dir=tmp_path)
    loaded = api.load_workspace_preset(state_dir=tmp_path)
    assert loaded is not None
    assert loaded.density_mode == "compact"
    assert loaded.motion_mode == "reduced"
    assert dict(loaded.panel_ratios) == dict(CANONICAL_DEFAULT_RATIOS)
    assert dict(loaded.panel_visibility)["harmony"] is False
    assert loaded.startup_source_node_id in (None, "")


def test_workspace_preset_never_serializes_transient_or_private_paths(
    tmp_path: Path,
) -> None:
    api = _api()
    before = _json_files(tmp_path)
    dirty = {
        "version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
        "panel_ratios": dict(CANONICAL_DEFAULT_RATIOS),
        "panel_visibility": {
            "library": True,
            "browser": True,
            "harmony": False,
            "livekit": True,
        },
        "density_mode": "compact",
        "motion_mode": "on",
        "selected_index": 3,
        "preview_active": True,
        "preview_progress": 0.4,
        "transport_state": {"playing": True},
        "harmonic_results": [{"id": "x"}],
        "harmonic_selection": 1,
        "harmonic_anchor": {"path": "C:/private/kick.wav"},
        "scroll_position": 120,
        "library_revealed": True,
        "audition_state": {"path": "C:/private/snare.wav"},
        "live_kit_snapshot": {"slots": []},
        "absolute_source_path": "C:/Users/private/Samples",
        "private_sample_path": "C:/Users/private/Samples/kick.wav",
        "startup_source_node_id": "root:42",
    }
    api.save_workspace_preset(dirty, state_dir=tmp_path)
    path = _new_prefs_json_after(tmp_path, before)
    raw = json.loads(path.read_text(encoding="utf-8"))
    leaked = FORBIDDEN_PRESET_KEYS.intersection(raw)
    assert not leaked, f"preset leaked transient/private keys: {sorted(leaked)}"
    blob = json.dumps(raw)
    assert "C:/Users/private" not in blob
    assert "C:\\Users\\private" not in blob
    assert raw.get("startup_source_node_id") == "root:42"


def test_save_workspace_preset_does_not_set_startup(tmp_path: Path) -> None:
    api = _api()
    api.save_workspace_preset(
        {
            "version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
            "panel_ratios": dict(CANONICAL_DEFAULT_RATIOS),
            "panel_visibility": {
                "library": True,
                "browser": True,
                "harmony": False,
                "livekit": True,
            },
            "density_mode": "compact",
            "motion_mode": "on",
            "startup_source_node_id": "root:99",
        },
        state_dir=tmp_path,
    )
    startup = load_startup_preset(state_dir=tmp_path)
    launch = resolve_launch_workspace(
        preset=startup.preset,
        source_available=lambda node_id: node_id == "root:99",
    )
    assert launch.mode is WorkspaceMode.CLEAN_START
    assert launch.source_node_id is None


def test_set_as_startup_is_explicit_and_opens_source_without_transient_restore(
    tmp_path: Path,
) -> None:
    api = _api()
    api.save_workspace_preset(
        {
            "version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
            "panel_ratios": dict(CANONICAL_DEFAULT_RATIOS),
            "panel_visibility": {
                "library": True,
                "browser": True,
                "harmony": True,
                "livekit": True,
            },
            "density_mode": "compact",
            "motion_mode": "reduced",
            "startup_source_node_id": "root:42",
            "selected_index": 5,
            "preview_active": True,
            "harmonic_results": [{"id": "stale"}],
            "scroll_position": 99,
        },
        state_dir=tmp_path,
    )
    api.set_as_startup(state_dir=tmp_path)
    loaded = load_startup_preset(state_dir=tmp_path)
    assert loaded.preset is not None
    assert loaded.preset.startup_source_node_id == "root:42"
    launch = resolve_launch_workspace(
        preset=loaded.preset,
        source_available=lambda node_id: node_id == "root:42",
    )
    assert launch.mode is WorkspaceMode.ACTIVE_SOURCE
    assert launch.source_node_id == "root:42"
    assert launch.browser_materialized is True
    assert launch.harmonic_visible is False
    raw = json.loads(workbench_startup_preset_file(state_dir=tmp_path).read_text(encoding="utf-8"))
    assert FORBIDDEN_PRESET_KEYS.isdisjoint(raw)


def test_clear_or_absent_startup_designation_without_persisted_list_is_clean_start(
    tmp_path: Path,
) -> None:
    api = _api()
    api.save_workspace_preset(
        {
            "version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
            "panel_ratios": dict(CANONICAL_DEFAULT_RATIOS),
            "density_mode": "compact",
            "motion_mode": "on",
            "startup_source_node_id": "root:42",
        },
        state_dir=tmp_path,
    )
    api.set_as_startup(state_dir=tmp_path)
    assert load_startup_preset(state_dir=tmp_path).preset is not None
    api.clear_startup_designation(state_dir=tmp_path)
    result = load_startup_preset(state_dir=tmp_path)
    launch = resolve_launch_workspace(
        preset=result.preset,
        source_available=lambda node_id: node_id == "root:42",
    )
    assert launch.mode is WorkspaceMode.CLEAN_START
    assert launch.source_node_id is None


def test_clear_startup_with_persisted_sources_still_returns_workspace() -> None:
    launch = resolve_launch_workspace(
        preset=None,
        source_available=lambda node_id: node_id == "root:42",
        persisted_source_node_ids=("root:42",),
    )
    assert launch.mode is WorkspaceMode.ACTIVE_SOURCE
    assert launch.source_node_id == "root:42"


@pytest.mark.parametrize(
    "payload",
    [
        "{not-json",
        json.dumps({"schema_version": 999, "motion_mode": "on", "density_mode": "compact"}),
        json.dumps(
            {
                "schema_version": 1,
                "density_mode": "compact",
                "motion_mode": "on",
                "panel_ratios": {"library": float("nan")},
            }
        ),
        json.dumps(
            {
                "schema_version": 1,
                "density_mode": "compact",
                "motion_mode": "on",
                "panel_visibility": {"unknown_panel": True},
            }
        ),
        json.dumps({"schema_version": 1, "density_mode": "banana", "motion_mode": "on"}),
        json.dumps({"schema_version": 1, "density_mode": "compact", "motion_mode": "teleport"}),
    ],
)
def test_corrupt_or_invalid_display_preferences_fail_closed(
    tmp_path: Path, payload: str
) -> None:
    api = _api()
    _write_corrupt_display_prefs(api, tmp_path, payload)
    loaded = api.load_display_preferences(state_dir=tmp_path)
    assert loaded.density_mode == "compact"
    assert loaded.motion_mode == "on"


def test_missing_offline_startup_source_fails_closed_to_clean_start(tmp_path: Path) -> None:
    api = _api()
    api.save_workspace_preset(
        {
            "version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
            "panel_ratios": dict(CANONICAL_DEFAULT_RATIOS),
            "density_mode": "compact",
            "motion_mode": "on",
            "startup_source_node_id": "root:offline",
        },
        state_dir=tmp_path,
    )
    api.set_as_startup(state_dir=tmp_path)
    loaded = load_startup_preset(state_dir=tmp_path)
    launch = resolve_launch_workspace(
        preset=loaded.preset,
        source_available=lambda _node_id: False,
    )
    assert launch.mode is WorkspaceMode.CLEAN_START
    assert launch.source_node_id is None


def test_reset_layout_restores_canonical_ratios_without_deleting_presets_or_sources(
    tmp_path: Path,
) -> None:
    api = _api()
    before = _json_files(tmp_path)
    save_layout_preferences(
        {"library": 0.10, "browser": 0.70, "harmony": 0.10, "livekit": 0.10},
        state_dir=tmp_path,
    )
    api.save_workspace_preset(
        {
            "version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
            "panel_ratios": dict(CANONICAL_DEFAULT_RATIOS),
            "density_mode": "compact",
            "motion_mode": "on",
        },
        state_dir=tmp_path,
    )
    preset_path = _new_prefs_json_after(tmp_path, before)
    marker = tmp_path / "library_sources_marker.txt"
    marker.write_text("registered-source-sentinel", encoding="utf-8")

    api.reset_layout(state_dir=tmp_path)
    assert dict(load_layout_preferences(state_dir=tmp_path).ratios) == dict(
        CANONICAL_DEFAULT_RATIOS
    )
    assert preset_path.is_file()
    assert marker.read_text(encoding="utf-8") == "registered-source-sentinel"


def test_return_to_clean_start_clears_working_context_but_keeps_presets(
    tmp_path: Path,
) -> None:
    api = _api()
    before = _json_files(tmp_path)
    api.save_display_preferences(
        {"density_mode": "compact", "motion_mode": "reduced"},
        state_dir=tmp_path,
    )
    api.save_workspace_preset(
        {
            "version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
            "panel_ratios": dict(CANONICAL_DEFAULT_RATIOS),
            "density_mode": "compact",
            "motion_mode": "reduced",
            "startup_source_node_id": "root:42",
        },
        state_dir=tmp_path,
    )
    preset_path = _new_prefs_json_after(tmp_path, before)
    api.set_as_startup(state_dir=tmp_path)
    marker = tmp_path / "library_sources_marker.txt"
    marker.write_text("registered-source-sentinel", encoding="utf-8")

    workspace = api.return_to_clean_start(state_dir=tmp_path)
    assert workspace.mode is WorkspaceMode.CLEAN_START
    assert workspace.source_node_id is None
    assert workspace.browser_materialized is False
    assert workspace.harmonic_visible is False
    assert workspace.calm_canvas_visible is True
    assert preset_path.is_file()
    assert workbench_startup_preset_file(state_dir=tmp_path).is_file()
    assert api.load_display_preferences(state_dir=tmp_path).motion_mode == "reduced"
    assert marker.read_text(encoding="utf-8") == "registered-source-sentinel"


def test_header_overflow_preferences_affordance_contract() -> None:
    source = QML_SOURCE
    assert f'objectName: "{PREFERENCES_OVERFLOW_OBJECT_NAME}"' in source
    assert f'objectName: "{PREFERENCES_POPOVER_OBJECT_NAME}"' in source
    for token in (
        "Appearance",
        "Reset Layout",
        "Save Workspace Preset",
        "Set Preset as Startup",
        "Return to Clean Start",
        "Motion",
        "Density",
    ):
        assert token in source
    assert 'objectName: "themePresetSelector"' in source
    assert 'objectName: "themeCustomizeButton"' in source
    assert 'objectName: "settingsBar"' not in source
    assert 'objectName: "toolsPanel"' not in source


def test_persisted_motion_off_drives_playhead_presentation_seam(tmp_path: Path) -> None:
    """Persisted Motion Off must be consumable by the #738 adapter seam."""
    api = _api()
    api.save_display_preferences(
        {"density_mode": "compact", "motion_mode": "off"},
        state_dir=tmp_path,
    )
    loaded = api.load_display_preferences(state_dir=tmp_path)
    assert loaded.motion_mode == "off"

    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        on_preview_requested=lambda *_a, **_k: None,
        on_preview_stopped=lambda: None,
        on_preview_snapshot=lambda: PreviewPlaybackSnapshot(
            playing=True,
            sample_path="C:/samples/kick.wav",
            position_ms=100,
            duration_ms=1000,
            progress=0.1,
            playback_instance_id=1,
        ),
    )
    adapter._preview_active = True  # noqa: SLF001
    adapter.set_waveform_motion_mode(loaded.motion_mode)
    assert adapter.waveform_motion_mode == "off"
    assert adapter.preview_playback_snapshot() == PreviewPlaybackSnapshot.idle()
    assert "waveformMotionMode" in QML_SOURCE
    assert "FrameAnimation" in QML_SOURCE


def test_product_save_and_set_startup_are_distinct_from_test_helper(tmp_path: Path) -> None:
    """Save Workspace Preset / Set as Startup are product ops, not the #693 test writer."""
    api = _api()
    assert api.set_as_startup.__name__ != "save_startup_preset_for_tests"
    assert api.save_workspace_preset.__name__ != "save_startup_preset_for_tests"
    save_startup_preset_for_tests(
        {
            "schema_version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
            "startup_source_node_id": "root:legacy-test-helper",
            "density_mode": "compact",
            "motion_mode": "on",
        },
        state_dir=tmp_path,
    )
    assert load_startup_preset(state_dir=tmp_path).preset is not None
