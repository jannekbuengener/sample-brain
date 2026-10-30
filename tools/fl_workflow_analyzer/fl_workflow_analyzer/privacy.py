"""Derived-data privacy: never restore information the recorder discarded."""

from __future__ import annotations

import re
from typing import Any

_FORBIDDEN_KEYS = frozenset(
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
        "argv",
        "x",  # mouse coords not needed for flow reconstruction
        "y",
    }
)

_PATH_LIKE = re.compile(
    r"(?i)([a-z]:\\|\\\\|/users/|/home/|%userprofile%|%localappdata%|\.flp\b|\.wav\b|\.mp3\b)"
)

# Safe keys allowed into derived evidence props.
_SAFE_KEYS = frozenset(
    {
        "surface",
        "prev",
        "playing",
        "event",
        "button",
        "phase",
        "redacted",
        "mods",
        "horizontal",
        "delta",
        "via",
        "form_id",
        "undo_count",
        "undo_pos",
        "plugin_present",
        "hint_class",
        "hint_present",
        "distance",
        "duration_ms",
        "fl_foreground",
        "marker",
        "blind_spot",
        "quality",
    }
)


def _scrub_str(value: str) -> str:
    if _PATH_LIKE.search(value):
        return "[redacted_path_like]"
    return value


def classify_hint(text: Any) -> str | None:
    """Map FL hint text to a coarse token class; never store free typed text."""
    if not isinstance(text, str) or not text.strip():
        return None
    low = text.strip().lower()
    from .rules import HINT_EDIT_TOKENS

    for tok in HINT_EDIT_TOKENS:
        if tok in low:
            return tok
    # Keep a short non-path token for provenance; truncate aggressively.
    cleaned = _scrub_str(text.strip())
    if cleaned == "[redacted_path_like]":
        return None
    return cleaned[:40].lower()


def safe_props(raw: dict | None, *, event_type: str | None = None) -> dict:
    """Project raw props into a privacy-safe derived subset."""
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        lk = str(key).lower()
        if lk in _FORBIDDEN_KEYS:
            continue
        if lk == "text" and event_type == "HINT":
            hc = classify_hint(value)
            out["hint_present"] = True
            if hc:
                out["hint_class"] = hc
            continue
        if lk == "hint" and event_type == "UNDO":
            hc = classify_hint(value)
            if hc:
                out["hint_class"] = hc
            continue
        if lk == "plugin":
            if isinstance(value, str) and value.strip():
                scrubbed = _scrub_str(value.strip())
                out["plugin_present"] = scrubbed != "[redacted_path_like]"
            else:
                out["plugin_present"] = False
            continue
        if lk == "caption":
            if isinstance(value, str) and value.strip():
                scrubbed = _scrub_str(value.strip())
                if scrubbed != "[redacted_path_like]":
                    # Form captions can contain project names — keep only emptiness flag.
                    out["caption_present"] = True
            continue
        if lk not in _SAFE_KEYS and lk not in {"undo_last", "undo_level_hint", "items"}:
            continue
        if lk in {"undo_last", "undo_level_hint"}:
            # May contain descriptive strings; keep presence only.
            out[f"{lk}_present"] = value is not None and str(value) != ""
            continue
        if lk == "items":
            out["items_count"] = len(value) if isinstance(value, list) else 0
            continue
        if isinstance(value, str):
            out[key] = _scrub_str(value)
        elif isinstance(value, (bool, int, float)) or value is None:
            out[key] = value
        elif isinstance(value, dict) and lk == "mods":
            # Only boolean modifier flags.
            out["mods"] = {
                str(mk): bool(mv)
                for mk, mv in value.items()
                if isinstance(mv, (bool, int))
            }
    return out
