"""Preferred native audition output device preference (#1209/#1345/#1348).

Persists audio-system mode plus a WASAPI/render device id for Screen-1 Browser
audition, along with runtime sample-rate and buffer-size preferences. Empty
device id means use the OS/native default. Does not invent a second audio
engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .workbench_controller import workbench_state_dir

AUDIO_OUTPUT_SCHEMA_VERSION = 1
AUDIO_SYSTEM_SAMPLE_BRAIN_AUDIO = "sample_brain_audio"
AUDIO_SYSTEM_VENDOR_ASIO = "vendor_asio"
_ALLOWED_AUDIO_SYSTEMS = frozenset(
    {
        AUDIO_SYSTEM_SAMPLE_BRAIN_AUDIO,
        AUDIO_SYSTEM_VENDOR_ASIO,
    }
)
# Supported Sample Brain Audio (WASAPI Shared) runtime values for V1.
ALLOWED_SAMPLE_RATES = (44100, 48000, 96000)
ALLOWED_BUFFER_FRAMES = (128, 256, 512, 1024)
DEFAULT_SAMPLE_RATE = 48000
DEFAULT_BUFFER_FRAMES = 256
_AUDIO_OUTPUT_FILENAME = "workbench_audio_output.json"


@dataclass(frozen=True)
class WorkbenchAudioOutputSettings:
    preferred_output_device_id: str = ""
    preferred_output_device_name: str = ""
    audio_system: str = AUDIO_SYSTEM_SAMPLE_BRAIN_AUDIO
    sample_rate: int = DEFAULT_SAMPLE_RATE
    buffer_frames: int = DEFAULT_BUFFER_FRAMES
    schema_version: int = AUDIO_OUTPUT_SCHEMA_VERSION


DEFAULT_WORKBENCH_AUDIO_OUTPUT_SETTINGS = WorkbenchAudioOutputSettings()


def workbench_audio_output_path(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / _AUDIO_OUTPUT_FILENAME


def _normalize_audio_system(raw: Any) -> str | None:
    if raw is None:
        return AUDIO_SYSTEM_SAMPLE_BRAIN_AUDIO
    if type(raw) is not str:
        return None
    value = raw.strip()
    if not value:
        return AUDIO_SYSTEM_SAMPLE_BRAIN_AUDIO
    if value not in _ALLOWED_AUDIO_SYSTEMS:
        return None
    return value


def _normalize_sample_rate(raw: Any) -> int | None:
    if raw is None:
        return DEFAULT_SAMPLE_RATE
    if type(raw) is not int or isinstance(raw, bool):
        return None
    if raw not in ALLOWED_SAMPLE_RATES:
        return None
    return raw


def _normalize_buffer_frames(raw: Any) -> int | None:
    if raw is None:
        return DEFAULT_BUFFER_FRAMES
    if type(raw) is not int or isinstance(raw, bool):
        return None
    if raw not in ALLOWED_BUFFER_FRAMES:
        return None
    return raw


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
    audio_system = _normalize_audio_system(settings.audio_system)
    sample_rate = _normalize_sample_rate(settings.sample_rate)
    buffer_frames = _normalize_buffer_frames(settings.buffer_frames)
    if audio_system is None or sample_rate is None or buffer_frames is None:
        return False
    if "\x00" in device_id or "\x00" in device_name:
        return False
    path_file = workbench_audio_output_path(state_dir=state_dir, env=env)
    body = {
        "schema_version": AUDIO_OUTPUT_SCHEMA_VERSION,
        "audio_system": audio_system,
        "preferred_output_device_id": device_id,
        "preferred_output_device_name": device_name,
        "sample_rate": sample_rate,
        "buffer_frames": buffer_frames,
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
    audio_system = _normalize_audio_system(raw.get("audio_system"))
    if audio_system is None:
        return defaults
    # Historical v1 files without rate/buffer keys keep product defaults.
    sample_rate = _normalize_sample_rate(raw.get("sample_rate", DEFAULT_SAMPLE_RATE))
    buffer_frames = _normalize_buffer_frames(
        raw.get("buffer_frames", DEFAULT_BUFFER_FRAMES)
    )
    if sample_rate is None or buffer_frames is None:
        return defaults
    return WorkbenchAudioOutputSettings(
        preferred_output_device_id=device_id,
        preferred_output_device_name=device_name,
        audio_system=audio_system,
        sample_rate=sample_rate,
        buffer_frames=buffer_frames,
        schema_version=AUDIO_OUTPUT_SCHEMA_VERSION,
    )


__all__ = [
    "ALLOWED_BUFFER_FRAMES",
    "ALLOWED_SAMPLE_RATES",
    "AUDIO_OUTPUT_SCHEMA_VERSION",
    "AUDIO_SYSTEM_SAMPLE_BRAIN_AUDIO",
    "AUDIO_SYSTEM_VENDOR_ASIO",
    "DEFAULT_BUFFER_FRAMES",
    "DEFAULT_SAMPLE_RATE",
    "DEFAULT_WORKBENCH_AUDIO_OUTPUT_SETTINGS",
    "WorkbenchAudioOutputSettings",
    "load_workbench_audio_output_settings",
    "save_workbench_audio_output_settings",
    "workbench_audio_output_path",
]
