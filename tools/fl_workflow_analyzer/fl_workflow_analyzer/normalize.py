"""Normalization layer: raw recorder events → stable internal normal form."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .privacy import safe_props

# action_class buckets for normalized events
_ACTION_CLASS = {
    "FOCUS_SURFACE": "focus",
    "FOCUS_FORM": "focus",
    "FOCUS_PLUGIN": "focus",
    "TRANSPORT": "transport",
    "UNDO": "edit_signal",
    "HINT": "hint",
    "REFRESH": "edit_signal",
    "DIRTY_MIXER": "edit_signal",
    "DIRTY_CHANNEL": "edit_signal",
    "BEAT_INDICATOR": "meta",
    "CLOCK_MARKER": "meta",
    "CLICK": "input",
    "DRAG": "input",
    "WHEEL": "input",
    "KEY_CMD": "input",
    "TEXT_ENTRY": "input",
    "FG": "foreground",
    "SESSION_OPEN": "meta",
    "SESSION_CLOSE": "meta",
    "SESSION_RECOVER": "meta",
    "ACTIVITY": "meta",
    "FL_PROCESS": "meta",
    "HEALTH": "meta",
    "MIDI_STATUS": "meta",
    "RECORDER_INIT": "meta",
    "RECORDER_DEINIT": "meta",
    "PROBE_INIT": "meta",
    "PROBE_DEINIT": "meta",
    "IDLE_STATS": "meta",
    "PROBE_WARN": "meta",
}


@dataclass(frozen=True)
class NormalizedEvent:
    session_id: str
    event_id: int
    source: str
    source_seq: int
    t_wall_ns: int
    t_utc: str
    event_type: str
    action_class: str
    surface: str | None
    truth_level: str  # always "measured" for normalized raw projections
    props: dict[str, Any] = field(default_factory=dict)
    quality_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["quality_flags"] = list(self.quality_flags)
        return d


def _surface_from_props(props: dict) -> str | None:
    s = props.get("surface")
    if isinstance(s, str) and s.strip() and s.strip().lower() not in ("none", "null", ""):
        return s.strip()
    return None


def normalize_raw_row(row: Any) -> NormalizedEvent:
    """Normalize one sqlite Row / mapping from events table."""
    props_raw: dict
    raw_json = row["props_json"] if "props_json" in row.keys() else row.get("props_json", "{}")
    try:
        props_raw = json.loads(raw_json) if isinstance(raw_json, str) else (raw_json or {})
    except json.JSONDecodeError:
        props_raw = {}
        quality = ("props_json_invalid",)
    else:
        quality = ()

    etype = str(row["event_type"])
    source = str(row["source"]).lower()
    if source in ("fl_script",):
        source = "fl"
    if source in ("windows",):
        source = "win"

    props = safe_props(props_raw, event_type=etype)
    surface = _surface_from_props(props_raw) or _surface_from_props(props)
    flags = list(quality)
    if etype == "FOCUS_PLUGIN" and not props.get("plugin_present"):
        flags.append("blind_spot_plugin_identity")
    if etype == "FOCUS_SURFACE" and surface is None:
        flags.append("surface_unknown")
    if etype == "HINT" and "hint_class" not in props:
        flags.append("hint_unclassified")

    return NormalizedEvent(
        session_id=str(row["session_id"]),
        event_id=int(row["id"]),
        source=source,
        source_seq=int(row["source_seq"]),
        t_wall_ns=int(row["t_wall_ns"]),
        t_utc=str(row["t_utc"] or ""),
        event_type=etype,
        action_class=_ACTION_CLASS.get(etype, "unknown"),
        surface=surface,
        truth_level="measured",
        props=props,
        quality_flags=tuple(flags),
    )


def normalize_events(rows: Iterable[Any]) -> list[NormalizedEvent]:
    events = [normalize_raw_row(r) for r in rows]
    events.sort(key=lambda e: (e.t_wall_ns, e.source, e.source_seq, e.event_id))
    return events
