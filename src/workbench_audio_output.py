"""Preferred native audition output device preference (#1209).

Persists a WASAPI/render device id for Screen-1 Browser audition. Empty id means
use the OS/native default. Does not invent a second audio engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .workbench_controller import workbench_state_dir

AUDIO_OUTPUT_SCHEMA_VERSION = 1
_AUDIO_OUTPUT_FILENAME = "workbench_audio_output.json"


@dataclass(frozen=True)
class WorkbenchAudioOutputSettings:
    preferred_output_device_id: str = ""
    preferred_output_device_name: str = ""
    schema_version: int = AUDIO_OUTPUT_SCHEMA_VERSION


DEFAULT_WORKBENCH_AUDIO_OUTPUT_SETTINGS = WorkbenchAudioOutputSettings()


def workbench_audio_output_path(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / _AUDIO_OUTPUT_FILENAME


def save_workbench_audio_output_settings(
    settings: WorkbenchAudioOutputSettings,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    if not isinstance(settings, WorkbenchAudioOutputSettings):
        raise TypeError("settings must be WorkbenchAudioOutputSettings")
    device_id = str(settings.preferred_output_device_id or "")
    device_name = str(settings.preferred_output_device_name or "")
    if "\x00" in device_id or "\x00" in device_name:
        return False
    path_file = workbench_audio_output_path(state_dir=state_dir, env=env)
    body = {
        "schema_version": AUDIO_OUTPUT_SCHEMA_VERSION,
        "preferred_output_device_id": device_id,
        "preferred_output_device_name": device_name,
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


def load_workbench_audio_output_settings(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> WorkbenchAudioOutputSettings:
    defaults = DEFAULT_WORKBENCH_AUDIO_OUTPUT_SETTINGS
    path_file = workbench_audio_output_path(state_dir=state_dir, env=env)
    if not path_file.is_file():
        return defaults
    try:
        raw: Any = json.loads(path_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return defaults
    if not isinstance(raw, dict):
        return defaults
    version = raw.get("schema_version")
    if type(version) is not int or version != AUDIO_OUTPUT_SCHEMA_VERSION:
        return defaults
    device_id = raw.get("preferred_output_device_id", "")
    device_name = raw.get("preferred_output_device_name", "")
    if type(device_id) is not str or type(device_name) is not str:
        return defaults
    if "\x00" in device_id or "\x00" in device_name:
        return defaults
    return WorkbenchAudioOutputSettings(
        preferred_output_device_id=device_id,
        preferred_output_device_name=device_name,
        schema_version=AUDIO_OUTPUT_SCHEMA_VERSION,
    )


__all__ = [
    "AUDIO_OUTPUT_SCHEMA_VERSION",
    "DEFAULT_WORKBENCH_AUDIO_OUTPUT_SETTINGS",
    "WorkbenchAudioOutputSettings",
    "load_workbench_audio_output_settings",
    "save_workbench_audio_output_settings",
    "workbench_audio_output_path",
]
