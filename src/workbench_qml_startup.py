"""Screen-1 startup preset resolve seam for Clean Start (#693) and #696 hook."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .workbench_controller import workbench_state_dir

SCREEN1_STARTUP_PRESET_SCHEMA_VERSION = 1
_STARTUP_PRESET_FILENAME = "screen1_startup_preset.json"


class WorkspaceMode(Enum):
    CLEAN_START = "clean_start"
    ACTIVE_SOURCE = "active_source"


@dataclass(frozen=True)
class Screen1StartupPreset:
    """Stable workspace/UI preference snapshot. Never stores transient session."""

    version: int
    panel_visibility: Mapping[str, bool] | None = None
    panel_ratios: Mapping[str, float] | None = None
    density_mode: str | None = None
    motion_mode: str | None = None
    startup_source_node_id: str | None = None


@dataclass(frozen=True)
class Screen1StartupPresetLoadResult:
    preset: Screen1StartupPreset | None
    persistable: bool


@dataclass(frozen=True)
class LaunchWorkspace:
    mode: WorkspaceMode
    source_node_id: str | None = None
    browser_materialized: bool = False
    live_kit_materialized: bool = False
    calm_canvas_visible: bool = True
    harmonic_visible: bool = False


def workbench_startup_preset_file(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / _STARTUP_PRESET_FILENAME


def load_startup_preset(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Screen1StartupPresetLoadResult:
    """Load an optional Startup Preset; corrupt/invalid fails closed."""
    path_file = workbench_startup_preset_file(state_dir=state_dir, env=env)
    if not path_file.is_file():
        return Screen1StartupPresetLoadResult(preset=None, persistable=True)
    try:
        raw = json.loads(path_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return Screen1StartupPresetLoadResult(preset=None, persistable=False)
    if not isinstance(raw, dict):
        return Screen1StartupPresetLoadResult(preset=None, persistable=False)
    version = raw.get("schema_version")
    if type(version) is not int or version != SCREEN1_STARTUP_PRESET_SCHEMA_VERSION:
        return Screen1StartupPresetLoadResult(preset=None, persistable=False)
    try:
        preset = _preset_from_mapping(raw)
    except (TypeError, ValueError):
        return Screen1StartupPresetLoadResult(preset=None, persistable=False)
    return Screen1StartupPresetLoadResult(preset=preset, persistable=True)


def resolve_launch_workspace(
    *,
    preset: Screen1StartupPreset | None,
    source_available: Callable[[str], bool] | None = None,
) -> LaunchWorkspace:
    """Resolve normal launch. Default Clean Start; valid preset Source may override."""
    if preset is None or not preset.startup_source_node_id:
        return _clean_start()
    node_id = str(preset.startup_source_node_id).strip()
    if not node_id:
        return _clean_start()
    checker = source_available or (lambda _node_id: False)
    try:
        available = bool(checker(node_id))
    except Exception:
        return _clean_start()
    if not available:
        return _clean_start()
    return LaunchWorkspace(
        mode=WorkspaceMode.ACTIVE_SOURCE,
        source_node_id=node_id,
        browser_materialized=True,
        live_kit_materialized=True,
        calm_canvas_visible=False,
        harmonic_visible=False,
    )


def save_startup_preset_for_tests(
    payload: Mapping[str, Any],
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Test-only writer for Startup Preset JSON (no product Preferences UI)."""
    path_file = workbench_startup_preset_file(state_dir=state_dir, env=env)
    path_file.parent.mkdir(parents=True, exist_ok=True)
    path_file.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")
    return path_file


def _clean_start() -> LaunchWorkspace:
    return LaunchWorkspace(mode=WorkspaceMode.CLEAN_START)


def _preset_from_mapping(raw: Mapping[str, Any]) -> Screen1StartupPreset:
    visibility = raw.get("panel_visibility")
    ratios = raw.get("panel_ratios")
    density = raw.get("density_mode")
    motion = raw.get("motion_mode")
    source = raw.get("startup_source_node_id")
    if visibility is not None:
        if not isinstance(visibility, Mapping) or any(
            not isinstance(k, str) or not isinstance(v, bool) for k, v in visibility.items()
        ):
            raise ValueError("invalid panel_visibility")
        visibility = {str(k): bool(v) for k, v in visibility.items()}
    if ratios is not None:
        if not isinstance(ratios, Mapping):
            raise ValueError("invalid panel_ratios")
        parsed: dict[str, float] = {}
        for key, value in ratios.items():
            if not isinstance(key, str):
                raise ValueError("invalid panel_ratios key")
            number = float(value)
            if number != number or number == float("inf") or number == float("-inf"):
                raise ValueError("invalid panel_ratios value")
            parsed[str(key)] = number
        ratios = parsed
    if density is not None and not isinstance(density, str):
        raise ValueError("invalid density_mode")
    if motion is not None and not isinstance(motion, str):
        raise ValueError("invalid motion_mode")
    if source is not None and not isinstance(source, str):
        raise ValueError("invalid startup_source_node_id")
    return Screen1StartupPreset(
        version=int(raw["schema_version"]),
        panel_visibility=visibility,
        panel_ratios=ratios,
        density_mode=density,
        motion_mode=motion,
        startup_source_node_id=source,
    )


__all__ = [
    "LaunchWorkspace",
    "SCREEN1_STARTUP_PRESET_SCHEMA_VERSION",
    "Screen1StartupPreset",
    "Screen1StartupPresetLoadResult",
    "WorkspaceMode",
    "load_startup_preset",
    "resolve_launch_workspace",
    "save_startup_preset_for_tests",
    "workbench_startup_preset_file",
]
