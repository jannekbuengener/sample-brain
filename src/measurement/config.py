"""Measurement mode and sidecar path resolution (ADR-0006)."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional


class MeasurementMode(str, Enum):
    OFF = "off"
    LOCAL = "local"
    LOCAL_EXPORT = "local+export"


ENV_MODE = "SAMPLE_BRAIN_MEASUREMENT_MODE"
ENV_DB_PATH = "SAMPLE_BRAIN_MEASUREMENT_DB_PATH"


def resolve_measurement_mode(
    *,
    config: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> MeasurementMode:
    env = env if env is not None else os.environ
    raw = env.get(ENV_MODE)
    if raw is None and config is not None:
        measurement = config.get("measurement")
        if isinstance(measurement, Mapping):
            raw = measurement.get("mode")
    if raw is None or str(raw).strip() == "":
        return MeasurementMode.OFF
    normalized = str(raw).strip().lower()
    try:
        return MeasurementMode(normalized)
    except ValueError:
        # Unknown mode → fail closed to off (privacy-conservative).
        return MeasurementMode.OFF


def default_measurement_db_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        base = Path(xdg) if xdg else Path.home() / ".cache"
    return (base / "sample-brain" / "measurement" / "measurement.db").resolve()


def resolve_measurement_db_path(
    *,
    config: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
    explicit: Optional[Path] = None,
) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = env if env is not None else os.environ
    raw = env.get(ENV_DB_PATH)
    if raw is None and config is not None:
        measurement = config.get("measurement")
        if isinstance(measurement, Mapping):
            raw = measurement.get("db_path")
    if raw:
        return Path(str(raw)).expanduser().resolve()
    return default_measurement_db_path()
