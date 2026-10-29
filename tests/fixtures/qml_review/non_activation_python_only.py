"""Non-activation fixture: pure Python catalog helper, no QML surface."""

from __future__ import annotations


def normalize_bpm_label(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}".rstrip("0").rstrip(".")
