"""Python-owned Live Kit Edit workspace helpers (#1077).

Coordinates visible-only projection, #1070 materialization, #1072 target keys,
and workspace visibility preference. Does not own musical assignments, QML
drag visuals (#1073), or Arrangement step UI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .workbench_controller import workbench_state_dir
from .workbench_edit_docking import EditDockingMaterialization
from .workbench_live_kit import LIVE_KIT_SLOT_MAPPING

LIVE_KIT_VISIBILITY_PREF_KEY = "live_kit_visible"
_LIVE_KIT_VISIBILITY_FILENAME = "live_kit_edit_visibility.json"
_VISIBILITY_SCHEMA_VERSION = 1


def visible_live_kit_slot_keys(*, live_kit_visible: bool) -> tuple[tuple[str, str], ...]:
    """Canonical assignment targets only while Live Kit is visibly open."""
    if not live_kit_visible:
        return ()
    return tuple(
        (group, slot) for group, slots in LIVE_KIT_SLOT_MAPPING for slot in slots
    )


def edit_docking_materialization_for_live_kit(
    live_kit_visible: bool,
    *,
    library: bool = True,
    browser: bool = True,
    harmony: bool = False,
) -> EditDockingMaterialization:
    """Map visible Live Kit state into #1070 materialization (no phantoms)."""
    return EditDockingMaterialization(
        library=bool(library),
        browser=bool(browser),
        harmony=bool(harmony),
        live_kit=bool(live_kit_visible),
    )


def live_kit_visibility_preference_path(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / _LIVE_KIT_VISIBILITY_FILENAME


def load_live_kit_visibility_preference(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Workspace UI preference; default hidden. Corrupt/missing → False."""
    path_file = live_kit_visibility_preference_path(state_dir=state_dir, env=env)
    if not path_file.is_file():
        return False
    try:
        raw = json.loads(path_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(raw, dict):
        return False
    if raw.get("schema_version") != _VISIBILITY_SCHEMA_VERSION:
        return False
    value = raw.get(LIVE_KIT_VISIBILITY_PREF_KEY)
    return value is True


def save_live_kit_visibility_preference(
    visible: bool,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Persist Live Kit Edit visibility preference (not musical state)."""
    path_file = live_kit_visibility_preference_path(state_dir=state_dir, env=env)
    path_file.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": _VISIBILITY_SCHEMA_VERSION,
        LIVE_KIT_VISIBILITY_PREF_KEY: bool(visible),
    }
    path_file.write_text(
        json.dumps(body, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path_file


def try_save_live_kit_visibility_preference(
    visible: bool,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Best-effort visibility persistence; OSError must not abort UI flows."""
    try:
        save_live_kit_visibility_preference(
            visible, state_dir=state_dir, env=env
        )
    except OSError:
        return False
    return True


__all__ = [
    "LIVE_KIT_VISIBILITY_PREF_KEY",
    "edit_docking_materialization_for_live_kit",
    "live_kit_visibility_preference_path",
    "load_live_kit_visibility_preference",
    "save_live_kit_visibility_preference",
    "try_save_live_kit_visibility_preference",
    "visible_live_kit_slot_keys",
]
