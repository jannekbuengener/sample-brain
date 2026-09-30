"""Screen-1 display preferences / workspace presets (#696).

Thin product façade over #693 startup and #694 layout seams.
Does not own playback, catalog, or session restore.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .workbench_controller import workbench_state_dir
from .workbench_layout_solver import (
    CANONICAL_DEFAULT_RATIOS,
    PANEL_IDS,
    normalize_ratios,
    save_layout_preferences,
)
from .workbench_qml_startup import (
    SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
    LaunchWorkspace,
    WorkspaceMode,
    workbench_startup_preset_file,
)

DISPLAY_PREFERENCES_SCHEMA_VERSION = 1
WORKSPACE_PRESET_SCHEMA_VERSION = SCREEN1_STARTUP_PRESET_SCHEMA_VERSION

MOTION_ON = "on"
MOTION_REDUCED = "reduced"
MOTION_OFF = "off"
MOTION_MODES = (MOTION_ON, MOTION_REDUCED, MOTION_OFF)

DENSITY_COMPACT = "compact"
DENSITY_MODES = (DENSITY_COMPACT,)

_DISPLAY_PREFERENCES_FILENAME = "screen1_display_preferences.json"
_WORKSPACE_PRESET_FILENAME = "screen1_workspace_preset.json"

_FORBIDDEN_PRESET_KEYS = frozenset(
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


@dataclass(frozen=True)
class DisplayPreferences:
    density_mode: str = DENSITY_COMPACT
    motion_mode: str = MOTION_ON
    schema_version: int = DISPLAY_PREFERENCES_SCHEMA_VERSION


@dataclass(frozen=True)
class WorkspacePreset:
    version: int
    panel_ratios: Mapping[str, float] | None = None
    panel_visibility: Mapping[str, bool] | None = None
    density_mode: str = DENSITY_COMPACT
    motion_mode: str = MOTION_ON
    startup_source_node_id: str | None = None


def normalize_motion_mode(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token == "full":
        return MOTION_ON
    if token in MOTION_MODES:
        return token
    return MOTION_ON


def normalize_density_mode(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token == DENSITY_COMPACT:
        return DENSITY_COMPACT
    # Comfortable and any unknown token fail closed to Compact in this slice.
    return DENSITY_COMPACT


def display_preferences_path(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / _DISPLAY_PREFERENCES_FILENAME


def workspace_preset_path(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / _WORKSPACE_PRESET_FILENAME


def save_display_preferences(
    payload: Mapping[str, Any],
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    prefs = DisplayPreferences(
        density_mode=normalize_density_mode(payload.get("density_mode")),
        motion_mode=normalize_motion_mode(payload.get("motion_mode")),
        schema_version=DISPLAY_PREFERENCES_SCHEMA_VERSION,
    )
    path = display_preferences_path(state_dir=state_dir, env=env)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": prefs.schema_version,
        "density_mode": prefs.density_mode,
        "motion_mode": prefs.motion_mode,
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_display_preferences(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> DisplayPreferences:
    defaults = DisplayPreferences()
    path = display_preferences_path(state_dir=state_dir, env=env)
    if not path.is_file():
        return defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return defaults
    if not isinstance(raw, dict):
        return defaults
    version = raw.get("schema_version")
    if type(version) is not int or version != DISPLAY_PREFERENCES_SCHEMA_VERSION:
        return defaults
    if not _display_payload_is_valid(raw):
        return defaults
    return DisplayPreferences(
        density_mode=normalize_density_mode(raw.get("density_mode")),
        motion_mode=normalize_motion_mode(raw.get("motion_mode")),
        schema_version=DISPLAY_PREFERENCES_SCHEMA_VERSION,
    )


def save_workspace_preset(
    payload: Mapping[str, Any],
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    sanitized = _sanitize_workspace_preset_payload(payload)
    path = workspace_preset_path(state_dir=state_dir, env=env)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_workspace_preset(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> WorkspacePreset | None:
    path = workspace_preset_path(state_dir=state_dir, env=env)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return _workspace_preset_from_mapping(raw)
    except (TypeError, ValueError):
        return None


def set_as_startup(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Explicitly designate the saved workspace preset as the Startup Preset."""
    preset = load_workspace_preset(state_dir=state_dir, env=env)
    path = workbench_startup_preset_file(state_dir=state_dir, env=env)
    if preset is None:
        clear_startup_designation(state_dir=state_dir, env=env)
        return path
    body = _startup_payload_from_workspace_preset(preset)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def clear_startup_designation(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    path = workbench_startup_preset_file(state_dir=state_dir, env=env)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        return


def reset_layout(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Restore canonical panel ratios without touching Sources/presets/catalog."""
    return save_layout_preferences(
        dict(CANONICAL_DEFAULT_RATIOS),
        state_dir=state_dir,
        env=env,
    )


def return_to_clean_start(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> LaunchWorkspace:
    """Return Clean Start workspace semantics without deleting presets/Sources."""
    _ = state_dir, env  # prefs/presets intentionally retained
    return LaunchWorkspace(
        mode=WorkspaceMode.CLEAN_START,
        source_node_id=None,
        browser_materialized=False,
        live_kit_materialized=False,
        calm_canvas_visible=True,
        harmonic_visible=False,
    )


def _display_payload_is_valid(raw: Mapping[str, Any]) -> bool:
    if "panel_ratios" in raw:
        ratios = raw.get("panel_ratios")
        if not isinstance(ratios, Mapping):
            return False
        try:
            normalize_ratios(ratios)
        except (TypeError, ValueError):
            return False
    if "panel_visibility" in raw:
        visibility = raw.get("panel_visibility")
        if not isinstance(visibility, Mapping):
            return False
        for key, value in visibility.items():
            if not isinstance(key, str) or key not in PANEL_IDS or not isinstance(value, bool):
                return False
    return True


def _sanitize_workspace_preset_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    version = payload.get("version", payload.get("schema_version", WORKSPACE_PRESET_SCHEMA_VERSION))
    if type(version) is not int:
        version = WORKSPACE_PRESET_SCHEMA_VERSION
    density = normalize_density_mode(payload.get("density_mode"))
    motion = normalize_motion_mode(payload.get("motion_mode"))

    ratios_raw = payload.get("panel_ratios")
    ratios: dict[str, float] | None = None
    if isinstance(ratios_raw, Mapping):
        try:
            ratios = normalize_ratios(ratios_raw)
        except (TypeError, ValueError):
            ratios = dict(CANONICAL_DEFAULT_RATIOS)

    visibility_raw = payload.get("panel_visibility")
    visibility: dict[str, bool] | None = None
    if isinstance(visibility_raw, Mapping):
        visibility = {}
        for key, value in visibility_raw.items():
            if isinstance(key, str) and key in PANEL_IDS and isinstance(value, bool):
                visibility[key] = value
        if not visibility:
            visibility = None

    source = payload.get("startup_source_node_id")
    source_id: str | None = None
    if isinstance(source, str):
        cleaned = source.strip()
        if cleaned and not _looks_like_filesystem_path(cleaned):
            source_id = cleaned

    body: dict[str, Any] = {
        "schema_version": int(version),
        "version": int(version),
        "density_mode": density,
        "motion_mode": motion,
        "startup_source_node_id": source_id,
    }
    if ratios is not None:
        body["panel_ratios"] = ratios
    if visibility is not None:
        body["panel_visibility"] = visibility
    for key in _FORBIDDEN_PRESET_KEYS:
        body.pop(key, None)
    return body


def _workspace_preset_from_mapping(raw: Mapping[str, Any]) -> WorkspacePreset:
    version = raw.get("version", raw.get("schema_version"))
    if type(version) is not int or version != WORKSPACE_PRESET_SCHEMA_VERSION:
        raise ValueError("invalid workspace preset version")
    sanitized = _sanitize_workspace_preset_payload(raw)
    return WorkspacePreset(
        version=int(sanitized["version"]),
        panel_ratios=sanitized.get("panel_ratios"),
        panel_visibility=sanitized.get("panel_visibility"),
        density_mode=str(sanitized["density_mode"]),
        motion_mode=str(sanitized["motion_mode"]),
        startup_source_node_id=sanitized.get("startup_source_node_id"),
    )


def _startup_payload_from_workspace_preset(preset: WorkspacePreset) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
        "density_mode": normalize_density_mode(preset.density_mode),
        "motion_mode": normalize_motion_mode(preset.motion_mode),
    }
    if preset.panel_ratios is not None:
        body["panel_ratios"] = dict(preset.panel_ratios)
    if preset.panel_visibility is not None:
        body["panel_visibility"] = dict(preset.panel_visibility)
    if preset.startup_source_node_id:
        body["startup_source_node_id"] = preset.startup_source_node_id
    for key in _FORBIDDEN_PRESET_KEYS:
        body.pop(key, None)
    return body


def _looks_like_filesystem_path(value: str) -> bool:
    if "://" in value and not value.startswith("root:"):
        return True
    if len(value) >= 3 and value[1] == ":" and value[2] in {"/", "\\"}:
        return True
    if value.startswith("\\\\") or value.startswith("/Users/") or value.startswith("/home/"):
        return True
    return False


__all__ = [
    "DISPLAY_PREFERENCES_SCHEMA_VERSION",
    "DENSITY_COMPACT",
    "DENSITY_MODES",
    "DisplayPreferences",
    "MOTION_MODES",
    "MOTION_OFF",
    "MOTION_ON",
    "MOTION_REDUCED",
    "WORKSPACE_PRESET_SCHEMA_VERSION",
    "WorkspacePreset",
    "clear_startup_designation",
    "display_preferences_path",
    "load_display_preferences",
    "load_workspace_preset",
    "normalize_density_mode",
    "normalize_motion_mode",
    "reset_layout",
    "return_to_clean_start",
    "save_display_preferences",
    "save_workspace_preset",
    "set_as_startup",
    "workspace_preset_path",
]
