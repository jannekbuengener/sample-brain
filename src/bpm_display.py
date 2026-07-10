from __future__ import annotations

import math


def is_valid_bpm(bpm: object) -> bool:
    if bpm is None:
        return False
    try:
        value = float(bpm)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(value):
        return False
    return value > 0


def round_bpm_display(bpm: object) -> int | None:
    if not is_valid_bpm(bpm):
        return None
    value = float(bpm)
    return int(math.floor(value + 0.5))


def format_bpm_display(bpm: object, *, placeholder: str = "—") -> str:
    rounded = round_bpm_display(bpm)
    if rounded is None:
        return placeholder
    return str(rounded)


def format_bpm_tag(bpm: object) -> str | None:
    rounded = round_bpm_display(bpm)
    if rounded is None:
        return None
    return f"{rounded}BPM"
