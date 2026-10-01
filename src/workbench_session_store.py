"""Local Workbench musical session persistence (#809).

Versioned JSON under ``workbench_state_dir()`` resumes Live Kit path refs and
Channel Rack channels/triggers across restarts. Fail-closed, all-or-nothing,
atomic writes. Never stores playback/loop/audition/QML runtime.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from .channel_rack import ChannelRackState
from .pattern_core import (
    CHANNEL_ID_BY_LIVE_KIT_SLOT,
    Channel,
    Pattern,
    Trigger,
)
from .workbench_controller import WorkbenchRow, workbench_state_dir
from .workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState

SCHEMA_VERSION = 1
WORKBENCH_SESSION_FILENAME = "workbench_session.json"

__all__ = [
    "SCHEMA_VERSION",
    "WORKBENCH_SESSION_FILENAME",
    "WorkbenchSessionSnapshot",
    "apply_snapshot_to_live_kit",
    "channel_rack_state_from_snapshot",
    "load_workbench_session_snapshot",
    "save_workbench_session_snapshot",
    "snapshot_from_musical_state",
    "workbench_row_from_sample_ref",
    "workbench_session_path",
]


@dataclass(frozen=True)
class WorkbenchSessionSnapshot:
    """Validated musical resume snapshot (kit refs + optional rack)."""

    live_kit: Mapping[str, Mapping[str, str | None]]
    channel_rack: ChannelRackState | None


def workbench_session_path(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / WORKBENCH_SESSION_FILENAME


def workbench_row_from_sample_ref(path: str) -> WorkbenchRow:
    """Deterministic minimal WorkbenchRow from a durable sample path ref."""
    text = str(path)
    name = Path(text).name or text
    return WorkbenchRow(
        display_name=name,
        relative_path=name,
        path=text,
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=None,
        pred_type=None,
        status="ok",
        details={},
    )


def _reject_unknown_keys(
    payload: Mapping[object, object],
    allowed: set[str],
    *,
    name: str,
) -> None:
    extra = {key for key in payload.keys() if key not in allowed}
    if extra:
        raise ValueError(f"Unsupported {name} keys: {sorted(extra)}")


def _exact_int(value: object, *, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an exact int (got {type(value).__name__})")
    return value


def _fraction_from_payload(payload: object, *, name: str) -> Fraction:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{name} must be an object with numerator/denominator")
    _reject_unknown_keys(
        payload, {"numerator", "denominator"}, name=name
    )
    numerator = _exact_int(payload.get("numerator"), name=f"{name}.numerator")
    denominator = _exact_int(payload.get("denominator"), name=f"{name}.denominator")
    if denominator == 0:
        raise ValueError(f"{name}.denominator must not be 0")
    return Fraction(numerator, denominator)


def _fraction_to_payload(value: Fraction) -> dict[str, int]:
    return {"numerator": int(value.numerator), "denominator": int(value.denominator)}


def _empty_live_kit_paths() -> dict[str, dict[str, str | None]]:
    return {group: {slot: None for slot in slots} for group, slots in LIVE_KIT_SLOT_MAPPING}


def _parse_live_kit(payload: object) -> dict[str, dict[str, str | None]]:
    if not isinstance(payload, Mapping):
        raise ValueError("live_kit must be an object")
    result = _empty_live_kit_paths()
    known = {(group, slot) for group, slots in LIVE_KIT_SLOT_MAPPING for slot in slots}
    for group, slots_payload in payload.items():
        if not isinstance(group, str) or not isinstance(slots_payload, Mapping):
            raise ValueError("live_kit entries must map group -> slot object")
        for slot, slot_payload in slots_payload.items():
            if not isinstance(slot, str):
                raise ValueError("live_kit slot keys must be strings")
            if (group, slot) not in known:
                raise ValueError(f"Unknown Live Kit slot: {group!r} -> {slot!r}")
            if slot_payload is None:
                result[group][slot] = None
                continue
            if not isinstance(slot_payload, Mapping):
                raise ValueError("live_kit slot value must be null or {path}")
            _reject_unknown_keys(slot_payload, {"path"}, name="live_kit slot")
            path = slot_payload.get("path")
            if path is not None and not isinstance(path, str):
                raise ValueError("live_kit path must be a string")
            if path is not None and path == "":
                raise ValueError("live_kit path must be non-empty when present")
            result[group][slot] = path
    return result


def _parse_channel(payload: object) -> Channel:
    if not isinstance(payload, Mapping):
        raise ValueError("channel entry must be an object")
    _reject_unknown_keys(
        payload,
        {"channel_id", "live_kit_group", "live_kit_slot", "sample_path"},
        name="channel",
    )
    channel_id = payload.get("channel_id")
    if not isinstance(channel_id, str) or channel_id == "":
        raise ValueError("channel_id must be a non-empty string")
    group = payload.get("live_kit_group")
    slot = payload.get("live_kit_slot")
    if group is not None and not isinstance(group, str):
        raise ValueError("live_kit_group must be str or null")
    if slot is not None and not isinstance(slot, str):
        raise ValueError("live_kit_slot must be str or null")
    sample_path = payload.get("sample_path")
    if sample_path is not None and not isinstance(sample_path, str):
        raise ValueError("sample_path must be str or null")
    return Channel(
        channel_id=channel_id,
        live_kit_group=group,
        live_kit_slot=slot,
        sample_path=sample_path,
    )


def _parse_trigger(payload: object) -> Trigger:
    if not isinstance(payload, Mapping):
        raise ValueError("trigger entry must be an object")
    _reject_unknown_keys(payload, {"channel_id", "position"}, name="trigger")
    channel_id = payload.get("channel_id")
    if not isinstance(channel_id, str) or channel_id == "":
        raise ValueError("trigger channel_id must be a non-empty string")
    position = _fraction_from_payload(payload.get("position"), name="trigger.position")
    return Trigger(channel_id=channel_id, position=position)


def _require_complete_seed_channels(channels: tuple[Channel, ...]) -> None:
    """Canonical seed set must be present exactly once with valid provenance."""
    seed_by_id = {
        channel.channel_id: channel
        for channel in channels
        if channel.live_kit_group is not None
    }
    expected_ids = set(CHANNEL_ID_BY_LIVE_KIT_SLOT.values())
    if set(seed_by_id) != expected_ids:
        raise ValueError("channel_rack must include exactly the canonical seed channels")
    for (group, slot), channel_id in CHANNEL_ID_BY_LIVE_KIT_SLOT.items():
        channel = seed_by_id[channel_id]
        if channel.live_kit_group != group or channel.live_kit_slot != slot:
            raise ValueError(
                f"seed channel {channel_id!r} provenance mismatch for {group}/{slot}"
            )


def _parse_channel_rack(payload: object) -> ChannelRackState | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise ValueError("channel_rack must be an object or null")
    _reject_unknown_keys(
        payload,
        {
            "pattern_id",
            "length_quarter_notes",
            "step_count",
            "channels",
            "triggers",
        },
        name="channel_rack",
    )
    pattern_id = payload.get("pattern_id")
    if not isinstance(pattern_id, str) or pattern_id == "":
        raise ValueError("pattern_id must be a non-empty string")
    length = _fraction_from_payload(
        payload.get("length_quarter_notes"), name="length_quarter_notes"
    )
    step_count = payload.get("step_count")
    if type(step_count) is not int or isinstance(step_count, bool):
        raise ValueError("step_count must be an exact int")
    if step_count <= 0:
        raise ValueError("step_count must be > 0")
    raw_channels = payload.get("channels")
    raw_triggers = payload.get("triggers")
    if not isinstance(raw_channels, list):
        raise ValueError("channels must be a list")
    if not isinstance(raw_triggers, list):
        raise ValueError("triggers must be a list")
    channels = tuple(_parse_channel(item) for item in raw_channels)
    _require_complete_seed_channels(channels)
    triggers = tuple(_parse_trigger(item) for item in raw_triggers)
    pattern = Pattern(
        pattern_id=pattern_id,
        length_quarter_notes=length,
        triggers=triggers,
    )
    return ChannelRackState(channels=channels, pattern=pattern, step_count=step_count)


def _parse_snapshot(data: object) -> WorkbenchSessionSnapshot:
    if not isinstance(data, Mapping):
        raise ValueError("session root must be an object")
    _reject_unknown_keys(
        data, {"schema_version", "live_kit", "channel_rack"}, name="session root"
    )
    version = data.get("schema_version")
    if type(version) is not int or isinstance(version, bool):
        raise ValueError("schema_version must be an exact int")
    if version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {version}")
    live_kit = _parse_live_kit(data.get("live_kit"))
    channel_rack = _parse_channel_rack(data.get("channel_rack"))
    if channel_rack is not None:
        # Align seed sample_path with live_kit authority (reject drift)
        aligned: list[Channel] = []
        for channel in channel_rack.channels:
            if channel.live_kit_group is None:
                aligned.append(channel)
                continue
            kit_path = live_kit[channel.live_kit_group][channel.live_kit_slot]
            if channel.sample_path != kit_path:
                raise ValueError(
                    f"seed channel {channel.channel_id!r} sample_path must match live_kit"
                )
            aligned.append(channel)
        channel_rack = ChannelRackState(
            channels=tuple(aligned),
            pattern=channel_rack.pattern,
            step_count=channel_rack.step_count,
        )
    return WorkbenchSessionSnapshot(live_kit=live_kit, channel_rack=channel_rack)


def load_workbench_session_snapshot(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> WorkbenchSessionSnapshot | None:
    """Load and validate a snapshot, or return None for fresh empty session.

    Missing file, corrupt JSON, unknown schema, or any semantic validation
    failure → None (all-or-nothing; never a partial musical session).
    """
    path = workbench_session_path(state_dir=state_dir, env=env)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        return _parse_snapshot(data)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def snapshot_from_musical_state(
    live_kit: LiveKitState,
    channel_rack_state: ChannelRackState | None,
) -> WorkbenchSessionSnapshot:
    """Build a snapshot; seed paths come from LiveKitState (kit authority)."""
    live_paths = _empty_live_kit_paths()
    for group, slots in LIVE_KIT_SLOT_MAPPING:
        for slot in slots:
            assignment = live_kit.assignment_for(group, slot)
            live_paths[group][slot] = (
                str(assignment.path) if assignment is not None else None
            )

    if channel_rack_state is None:
        return WorkbenchSessionSnapshot(live_kit=live_paths, channel_rack=None)

    channels: list[Channel] = []
    for channel in channel_rack_state.channels:
        if channel.live_kit_group is not None and channel.live_kit_slot is not None:
            kit_path = live_paths[channel.live_kit_group][channel.live_kit_slot]
            channels.append(
                Channel(
                    channel_id=channel.channel_id,
                    live_kit_group=channel.live_kit_group,
                    live_kit_slot=channel.live_kit_slot,
                    sample_path=kit_path,
                )
            )
        else:
            channels.append(channel)

    aligned = ChannelRackState(
        channels=tuple(channels),
        pattern=channel_rack_state.pattern,
        step_count=channel_rack_state.step_count,
    )
    return WorkbenchSessionSnapshot(live_kit=live_paths, channel_rack=aligned)


def _snapshot_to_json_dict(snapshot: WorkbenchSessionSnapshot) -> dict[str, Any]:
    live_kit: dict[str, dict[str, dict[str, str] | None]] = {}
    for group, slots in LIVE_KIT_SLOT_MAPPING:
        live_kit[group] = {}
        for slot in slots:
            path = snapshot.live_kit[group][slot]
            live_kit[group][slot] = {"path": path} if path is not None else None

    if snapshot.channel_rack is None:
        channel_rack: dict[str, Any] | None = None
    else:
        state = snapshot.channel_rack
        channel_rack = {
            "pattern_id": state.pattern.pattern_id,
            "length_quarter_notes": _fraction_to_payload(state.pattern.length_quarter_notes),
            "step_count": state.step_count,
            "channels": [
                {
                    "channel_id": channel.channel_id,
                    "live_kit_group": channel.live_kit_group,
                    "live_kit_slot": channel.live_kit_slot,
                    "sample_path": channel.sample_path,
                }
                for channel in state.channels
            ],
            "triggers": [
                {
                    "channel_id": trigger.channel_id,
                    "position": _fraction_to_payload(trigger.position),
                }
                for trigger in state.pattern.triggers
            ],
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "live_kit": live_kit,
        "channel_rack": channel_rack,
    }


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, path)
    except Exception:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def save_workbench_session_snapshot(
    snapshot: WorkbenchSessionSnapshot,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Atomically write a validated snapshot. Raises on IO failure."""
    path = workbench_session_path(state_dir=state_dir, env=env)
    _atomic_write_json(path, _snapshot_to_json_dict(snapshot))
    return path


def apply_snapshot_to_live_kit(
    snapshot: WorkbenchSessionSnapshot, live_kit: LiveKitState
) -> None:
    """Assign restored path refs onto an empty LiveKitState (no save side effects)."""
    for group, slots in LIVE_KIT_SLOT_MAPPING:
        for slot in slots:
            path = snapshot.live_kit[group][slot]
            if path is not None:
                live_kit.assign(group, slot, workbench_row_from_sample_ref(path))


def channel_rack_state_from_snapshot(
    snapshot: WorkbenchSessionSnapshot,
) -> ChannelRackState | None:
    return snapshot.channel_rack
