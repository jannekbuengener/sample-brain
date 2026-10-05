"""Canonical Workbench functional feature settings (#910).

Owns reusable product behavior toggles. Distinct from view/display/theme/layout
preferences. Does not mutate Rack, Pattern, or musical session state.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
import json
from pathlib import Path
from typing import Any, Mapping

from .workbench_controller import workbench_state_dir

FEATURE_SETTINGS_SCHEMA_VERSION = 1
_FEATURE_SETTINGS_FILENAME = "workbench_feature_settings.json"
_FEATURE_SETTINGS_BOOL_FIELDS = ("gesture_rack_apply_enabled",)


@dataclass(frozen=True)
class WorkbenchFeatureSettings:
    """Immutable functional feature-toggle snapshot."""

    gesture_rack_apply_enabled: bool = False
    schema_version: int = FEATURE_SETTINGS_SCHEMA_VERSION


DEFAULT_WORKBENCH_FEATURE_SETTINGS = WorkbenchFeatureSettings()


def workbench_feature_settings_path(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / _FEATURE_SETTINGS_FILENAME


def replace_workbench_feature_settings(
    settings: WorkbenchFeatureSettings,
    /,
    **changes: Any,
) -> WorkbenchFeatureSettings:
    """Return a new frozen settings object with validated field changes."""
    if not isinstance(settings, WorkbenchFeatureSettings):
        raise TypeError("settings must be WorkbenchFeatureSettings")
    unknown = set(changes) - {f.name for f in fields(WorkbenchFeatureSettings)}
    if unknown:
        raise TypeError(f"unknown feature settings fields: {sorted(unknown)}")
    if "gesture_rack_apply_enabled" in changes:
        value = changes["gesture_rack_apply_enabled"]
        if type(value) is not bool:
            raise TypeError("gesture_rack_apply_enabled must be bool")
    if "schema_version" in changes:
        version = changes["schema_version"]
        if type(version) is not int:
            raise TypeError("schema_version must be int")
    return replace(settings, **changes)


def save_workbench_feature_settings(
    settings: WorkbenchFeatureSettings,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Persist functional feature settings to user-local state."""
    if not isinstance(settings, WorkbenchFeatureSettings):
        raise TypeError("settings must be WorkbenchFeatureSettings")
    path_file = workbench_feature_settings_path(state_dir=state_dir, env=env)
    body = {
        "schema_version": FEATURE_SETTINGS_SCHEMA_VERSION,
        "gesture_rack_apply_enabled": bool(settings.gesture_rack_apply_enabled),
    }
    try:
        path_file.parent.mkdir(parents=True, exist_ok=True)
        path_file.write_text(
            json.dumps(body, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def load_workbench_feature_settings(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> WorkbenchFeatureSettings:
    """Load functional settings; invalid/unknown payloads fail closed to defaults."""
    defaults = DEFAULT_WORKBENCH_FEATURE_SETTINGS
    path_file = workbench_feature_settings_path(state_dir=state_dir, env=env)
    if not path_file.is_file():
        return defaults
    try:
        raw = json.loads(path_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return defaults
    if not isinstance(raw, dict):
        return defaults
    version = raw.get("schema_version")
    if type(version) is not int or version != FEATURE_SETTINGS_SCHEMA_VERSION:
        return defaults
    if not _feature_payload_is_valid(raw):
        return defaults
    return WorkbenchFeatureSettings(
        gesture_rack_apply_enabled=raw["gesture_rack_apply_enabled"],
        schema_version=FEATURE_SETTINGS_SCHEMA_VERSION,
    )


def _feature_payload_is_valid(raw: Mapping[str, Any]) -> bool:
    for key in _FEATURE_SETTINGS_BOOL_FIELDS:
        if key not in raw or type(raw[key]) is not bool:
            return False
    return True


__all__ = [
    "DEFAULT_WORKBENCH_FEATURE_SETTINGS",
    "FEATURE_SETTINGS_SCHEMA_VERSION",
    "WorkbenchFeatureSettings",
    "load_workbench_feature_settings",
    "replace_workbench_feature_settings",
    "save_workbench_feature_settings",
    "workbench_feature_settings_path",
]
