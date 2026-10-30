"""Machine-readable local health status (no dashboard / no web server)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import RECORDER_VERSION, SCHEMA_VERSION


def write_health(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema": "sb.fl_workflow_recorder.health.v1",
        "recorder_version": RECORDER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "updated_t_wall_ns": time.time_ns(),
        "updated_t_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **payload,
    }
    path.write_text(json.dumps(body, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_health(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
