"""Fail-closed privacy gate for recorder ingest (#1321)."""

from __future__ import annotations

import re
from typing import Any

# Event types allowed into durable store (frozen #1320 V1 + recorder lifecycle).
ALLOWED_FL_TYPES = frozenset(
    {
        "FOCUS_SURFACE",
        "FOCUS_FORM",
        "FOCUS_PLUGIN",  # may be empty; still allowed if emitted
        "TRANSPORT",
        "UNDO",
        "HINT",
        "REFRESH",
        "DIRTY_MIXER",
        "DIRTY_CHANNEL",
        "BEAT_INDICATOR",
        "CLOCK_MARKER",
        "PROBE_INIT",
        "PROBE_DEINIT",
        "RECORDER_INIT",
        "RECORDER_DEINIT",
        "IDLE_STATS",  # health/probe only; retained raw for diagnostics
    }
)

ALLOWED_WIN_TYPES = frozenset(
    {
        "FG",
        "CLICK",
        "DRAG",
        "WHEEL",
        "KEY_CMD",
        "TEXT_ENTRY",
        "CLOCK_MARKER",
        "PROBE_INIT",
        "PROBE_DEINIT",
        "RECORDER_INIT",
        "RECORDER_DEINIT",
        "PROBE_WARN",
    }
)

ALLOWED_OBSERVER_TYPES = frozenset(
    {
        "SESSION_OPEN",
        "SESSION_CLOSE",
        "SESSION_RECOVER",
        "FL_PROCESS",
        "HEALTH",
        "CLOCK_MARKER",
        "RECORDER_INIT",
        "RECORDER_DEINIT",
        "MIDI_STATUS",
        "ACTIVITY",
    }
)

# Props keys that must never survive ingest.
_FORBIDDEN_PROP_KEYS = frozenset(
    {
        "char",
        "character",
        "text_raw",
        "typed",
        "clipboard",
        "password",
        "passphrase",
        "screenshot",
        "audio",
        "sample_path",
        "project_path",
        "absolute_path",
        "argv",  # may contain machine paths
    }
)

_PATH_LIKE = re.compile(
    r"(?i)([a-z]:\\|\\\\|/users/|/home/|%userprofile%|%localappdata%|\.flp\b|\.wav\b|\.mp3\b)"
)


def is_allowed_event(source: str, event_type: str) -> bool:
    src = (source or "").lower()
    if src in ("fl", "fl_script"):
        return event_type in ALLOWED_FL_TYPES
    if src in ("win", "windows"):
        return event_type in ALLOWED_WIN_TYPES
    if src in ("observer", "recorder"):
        return event_type in ALLOWED_OBSERVER_TYPES
    return False


def _scrub_value(key: str, value: Any) -> Any:
    lk = key.lower()
    if lk in _FORBIDDEN_PROP_KEYS:
        return None
    if isinstance(value, str):
        if lk in ("text", "caption", "hint", "undo_level_hint") and _PATH_LIKE.search(value):
            return "[redacted_path_like]"
        # Cap unbounded strings.
        if len(value) > 512:
            return value[:512] + "…"
        return value
    if isinstance(value, dict):
        return scrub_props(value)
    if isinstance(value, list):
        out = []
        for item in value[:64]:
            if isinstance(item, dict):
                out.append(scrub_props(item))
            elif isinstance(item, str) and _PATH_LIKE.search(item):
                out.append("[redacted_path_like]")
            else:
                out.append(item)
        return out
    return value


def scrub_props(props: dict | None) -> dict:
    if not props:
        return {}
    out: dict[str, Any] = {}
    for key, value in props.items():
        if key.lower() in _FORBIDDEN_PROP_KEYS:
            continue
        cleaned = _scrub_value(str(key), value)
        if cleaned is None:
            continue
        out[str(key)] = cleaned
    return out


def enforce_text_entry(event_type: str, props: dict) -> dict:
    if event_type != "TEXT_ENTRY":
        return props
    # Fail-closed: only redaction markers + mods.
    mods = props.get("mods") if isinstance(props.get("mods"), dict) else None
    out: dict[str, Any] = {"redacted": True}
    if mods is not None:
        out["mods"] = {
            k: bool(v)
            for k, v in mods.items()
            if k in ("ctrl", "alt", "shift", "win")
        }
    return out


def sanitize_event(raw: dict) -> dict | None:
    """Return a privacy-safe event dict or None to drop."""
    if not isinstance(raw, dict):
        return None
    source = str(raw.get("source") or "").lower()
    # Normalize source labels.
    if source in ("windows",):
        source = "win"
    event_type = str(raw.get("type") or raw.get("event_type") or "")
    if not is_allowed_event(source, event_type):
        return None
    try:
        seq = int(raw.get("seq") if raw.get("seq") is not None else raw.get("source_seq"))
        t_wall_ns = int(raw["t_wall_ns"])
    except (KeyError, TypeError, ValueError):
        return None
    props = raw.get("props") if isinstance(raw.get("props"), dict) else {}
    props = scrub_props(props)
    props = enforce_text_entry(event_type, props)
    mono = raw.get("t_mono_ns")
    try:
        t_mono_ns = int(mono) if mono is not None else None
    except (TypeError, ValueError):
        t_mono_ns = None
    t_utc = raw.get("t_utc")
    if not isinstance(t_utc, str) or not t_utc:
        # Display-only; reconstruct later if missing.
        t_utc = ""
    return {
        "source": "fl" if source in ("fl", "fl_script") else ("win" if source == "win" else "observer"),
        "source_seq": seq,
        "t_wall_ns": t_wall_ns,
        "t_utc": t_utc,
        "t_mono_ns": t_mono_ns,
        "event_type": event_type,
        "props": props,
    }
