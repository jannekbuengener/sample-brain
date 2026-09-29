"""Pure-Python Screen-1 elastic layout solver (#694).

QML projects widths/handles; this module owns ratios, drag, clamp, fallback,
and layout-preference persistence. See docs/WORKBENCH_ELASTIC_LAYOUT.md.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Mapping

from .workbench_controller import workbench_state_dir

PANEL_IDS: tuple[str, ...] = ("library", "browser", "harmony", "livekit")

CANONICAL_DEFAULT_RATIOS: dict[str, float] = {
    "library": 0.18,
    "browser": 0.50,
    "harmony": 0.18,
    "livekit": 0.14,
}

HANDLE_WIDTH_PX = 6.0
DEFAULT_DECAY = 0.55
LAYOUT_PREFERENCES_SCHEMA_VERSION = 1
_LAYOUT_PREFERENCES_FILENAME = "screen1_layout_preferences.json"

PANEL_MIN_WIDTH: dict[str, float] = {
    "library": 230.0,
    "browser": 480.0,
    "harmony": 280.0,
    "livekit": 220.0,
}

# Higher = more protected against crush. Browser is highest.
PANEL_PRIORITY: dict[str, int] = {
    "browser": 100,
    "library": 50,
    "harmony": 40,
    "livekit": 30,
}


@dataclass(frozen=True)
class LayoutSolution:
    widths: Mapping[str, float]
    ratios: Mapping[str, float]
    available_width: float
    handle_width: float
    fallback: str | None


@dataclass(frozen=True)
class LayoutPreferencesLoadResult:
    ratios: Mapping[str, float]
    schema_version: int
    persistable: bool


def normalize_ratios(ratios: Mapping[str, float]) -> dict[str, float]:
    if set(ratios) != set(PANEL_IDS):
        raise ValueError("panel_ratios must contain exactly the canonical panel IDs")
    values: dict[str, float] = {}
    for panel_id in PANEL_IDS:
        value = float(ratios[panel_id])
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"ratio for {panel_id!r} must be finite and > 0")
        values[panel_id] = value
    total = sum(values.values())
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError("ratio sum must be finite and > 0")
    return {panel_id: values[panel_id] / total for panel_id in PANEL_IDS}


def visible_panel_ids(*, harmony_open: bool, has_active_source: bool) -> tuple[str, ...]:
    # Clean Start: calm canvas is not a weighted panel; elastic is inactive.
    if not has_active_source:
        return ()
    if harmony_open:
        return ("library", "browser", "harmony", "livekit")
    return ("library", "browser", "livekit")


def set_harmony_open(ratios: Mapping[str, float], _open: bool) -> dict[str, float]:
    """Keep stored ratios stable across open/close; visibility is a solve input."""
    return normalize_ratios(ratios)


def solve_widths(
    ratios: Mapping[str, float],
    *,
    available_width: float,
    harmony_open: bool,
    has_active_source: bool,
    handle_width: float = HANDLE_WIDTH_PX,
) -> LayoutSolution:
    stored = normalize_ratios(ratios)
    visible = visible_panel_ids(
        harmony_open=harmony_open, has_active_source=has_active_source
    )
    if available_width <= 0 or not math.isfinite(available_width):
        raise ValueError("available_width must be finite and > 0")
    if not visible:
        return LayoutSolution(
            widths={},
            ratios=stored,
            available_width=available_width,
            handle_width=handle_width,
            fallback=None,
        )
    handle_budget = handle_width * max(0, len(visible) - 1)
    content = available_width - handle_budget
    if content <= 0:
        raise ValueError("available_width too small for handles")

    mins = {panel_id: PANEL_MIN_WIDTH[panel_id] for panel_id in visible}
    min_sum = sum(mins.values())
    fallback: str | None = None
    if content + 1e-9 < min_sum:
        fallback = "proportional_min_overflow"
        scale = content / min_sum
        widths = {panel_id: mins[panel_id] * scale for panel_id in visible}
    else:
        shares = _visible_shares(stored, visible)
        widths = {panel_id: shares[panel_id] * content for panel_id in visible}
        widths = _enforce_minima(widths, mins, content)

    return LayoutSolution(
        widths=widths,
        ratios=stored,
        available_width=available_width,
        handle_width=handle_width,
        fallback=fallback,
    )


def apply_divider_drag(
    ratios: Mapping[str, float],
    *,
    divider_after: str,
    delta_px: float,
    available_width: float,
    harmony_open: bool,
    has_active_source: bool,
    decay: float = DEFAULT_DECAY,
    handle_width: float = HANDLE_WIDTH_PX,
) -> dict[str, float]:
    stored = normalize_ratios(ratios)
    if not math.isfinite(delta_px):
        raise ValueError("delta_px must be finite")
    if abs(delta_px) < 1e-12:
        return stored

    visible = list(
        visible_panel_ids(harmony_open=harmony_open, has_active_source=has_active_source)
    )
    if divider_after not in visible:
        raise ValueError(f"divider_after {divider_after!r} is not visible")
    index = visible.index(divider_after)
    if index >= len(visible) - 1:
        raise ValueError("divider_after must have a right-hand neighbour")

    left = visible[: index + 1]
    right = visible[index + 1 :]
    solution = solve_widths(
        stored,
        available_width=available_width,
        harmony_open=harmony_open,
        has_active_source=has_active_source,
        handle_width=handle_width,
    )
    if solution.fallback is not None:
        # No ratio mutation while in overflow fallback; keep stored truth stable.
        return stored

    widths = {panel_id: float(solution.widths[panel_id]) for panel_id in visible}
    mins = {panel_id: PANEL_MIN_WIDTH[panel_id] for panel_id in visible}
    content = available_width - handle_width * max(0, len(visible) - 1)

    left_weights = _distance_weights(len(left), decay, closest_last=True)
    right_weights = _distance_weights(len(right), decay, closest_last=False)

    # Apply the same absorbed magnitude on both sides so undoing a drag without
    # saturation returns to the prior ratios (no ratchet drift).
    max_grow_left = _max_absorbable(widths, left, mins, direction=+1)
    max_shrink_right = _max_absorbable(widths, right, mins, direction=-1)
    max_shrink_left = _max_absorbable(widths, left, mins, direction=-1)
    max_grow_right = _max_absorbable(widths, right, mins, direction=+1)
    if delta_px >= 0:
        absorbed = min(delta_px, max_grow_left, max_shrink_right)
    else:
        absorbed = -min(-delta_px, max_shrink_left, max_grow_right)
    if abs(absorbed) < 1e-12:
        return stored

    widths = _apply_side_delta(widths, left, left_weights, +absorbed, mins)
    widths = _apply_side_delta(widths, right, right_weights, -absorbed, mins)
    widths = _enforce_minima(widths, mins, content)

    return _ratios_from_visible_widths(stored, widths, visible)


def layout_preferences_path(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / _LAYOUT_PREFERENCES_FILENAME


def save_layout_preferences(
    ratios: Mapping[str, float],
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    normalized = normalize_ratios(ratios)
    path = layout_preferences_path(state_dir=state_dir, env=env)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": LAYOUT_PREFERENCES_SCHEMA_VERSION,
        "panel_ratios": {panel_id: normalized[panel_id] for panel_id in PANEL_IDS},
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load_layout_preferences(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> LayoutPreferencesLoadResult:
    path = layout_preferences_path(state_dir=state_dir, env=env)
    defaults = dict(CANONICAL_DEFAULT_RATIOS)
    if not path.is_file():
        return LayoutPreferencesLoadResult(
            ratios=defaults,
            schema_version=LAYOUT_PREFERENCES_SCHEMA_VERSION,
            persistable=True,
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return LayoutPreferencesLoadResult(
            ratios=defaults,
            schema_version=LAYOUT_PREFERENCES_SCHEMA_VERSION,
            persistable=False,
        )
    if not isinstance(raw, dict):
        return LayoutPreferencesLoadResult(
            ratios=defaults,
            schema_version=LAYOUT_PREFERENCES_SCHEMA_VERSION,
            persistable=False,
        )
    version = raw.get("schema_version")
    if type(version) is not int or version != LAYOUT_PREFERENCES_SCHEMA_VERSION:
        return LayoutPreferencesLoadResult(
            ratios=defaults,
            schema_version=LAYOUT_PREFERENCES_SCHEMA_VERSION,
            persistable=False,
        )
    panel_ratios = raw.get("panel_ratios")
    if not isinstance(panel_ratios, dict):
        return LayoutPreferencesLoadResult(
            ratios=defaults,
            schema_version=LAYOUT_PREFERENCES_SCHEMA_VERSION,
            persistable=False,
        )
    try:
        normalized = normalize_ratios(panel_ratios)
    except (TypeError, ValueError):
        return LayoutPreferencesLoadResult(
            ratios=defaults,
            schema_version=LAYOUT_PREFERENCES_SCHEMA_VERSION,
            persistable=False,
        )
    return LayoutPreferencesLoadResult(
        ratios=normalized,
        schema_version=version,
        persistable=True,
    )


def _visible_shares(
    stored: Mapping[str, float], visible: tuple[str, ...] | list[str]
) -> dict[str, float]:
    weights = {panel_id: float(stored[panel_id]) for panel_id in visible}
    total = sum(weights.values())
    if total <= 0 or not math.isfinite(total):
        equal = 1.0 / len(visible)
        return {panel_id: equal for panel_id in visible}
    return {panel_id: weights[panel_id] / total for panel_id in visible}


def _distance_weights(
    count: int, decay: float, *, closest_last: bool
) -> list[float]:
    if count <= 0:
        return []
    if closest_last:
        # left side: last index is adjacent to divider
        return [decay ** (count - 1 - index) for index in range(count)]
    return [decay**index for index in range(count)]


def _max_absorbable(
    widths: Mapping[str, float],
    side: list[str],
    mins: Mapping[str, float],
    *,
    direction: int,
) -> float:
    if direction < 0:
        return sum(max(0.0, widths[panel_id] - mins[panel_id]) for panel_id in side)
    # No max caps in v1 — growth limited by the opposite side's shrink budget.
    return float("inf")


def _apply_side_delta(
    widths: dict[str, float],
    side: list[str],
    weights: list[float],
    delta: float,
    mins: Mapping[str, float],
) -> dict[str, float]:
    if not side or abs(delta) < 1e-12:
        return widths
    remaining = float(delta)
    flexible = list(side)
    for _ in range(len(side) + 2):
        if abs(remaining) < 1e-9 or not flexible:
            break
        weight_map = {
            panel_id: weights[side.index(panel_id)]
            for panel_id in flexible
            if weights[side.index(panel_id)] > 0
        }
        total_w = sum(weight_map.values())
        if total_w <= 0:
            break
        next_flexible: list[str] = []
        progressed = 0.0
        for panel_id, weight in weight_map.items():
            share = remaining * (weight / total_w)
            proposed = widths[panel_id] + share
            floor = mins[panel_id]
            if proposed < floor:
                applied = floor - widths[panel_id]
                widths[panel_id] = floor
                progressed += applied
            else:
                widths[panel_id] = proposed
                progressed += share
                next_flexible.append(panel_id)
        remaining -= progressed
        if abs(remaining) < 1e-9:
            break
        # Residual after saturation: only still-flexible panels continue.
        flexible = next_flexible
        if remaining < 0 and not flexible:
            break
        if remaining > 0:
            # Growth residual: panels that hit no ceiling (none defined) keep all.
            flexible = [panel_id for panel_id in side if panel_id in weight_map]
    return widths


def _enforce_minima(
    widths: Mapping[str, float],
    mins: Mapping[str, float],
    content: float,
) -> dict[str, float]:
    result = {panel_id: float(widths[panel_id]) for panel_id in widths}
    for _ in range(len(result) + 3):
        deficit = 0.0
        flexible: list[str] = []
        for panel_id, width in result.items():
            floor = mins[panel_id]
            if width + 1e-9 < floor:
                deficit += floor - width
                result[panel_id] = floor
            elif width > floor + 1e-9:
                flexible.append(panel_id)
        if deficit <= 1e-9:
            break
        if not flexible:
            # Absolute overflow — scale after clamp (caller may already fallback).
            total = sum(result.values())
            if total <= 0:
                break
            scale = content / total
            return {panel_id: result[panel_id] * scale for panel_id in result}
        # Take deficit from lowest-priority flexible panels first (protect browser).
        flexible.sort(key=lambda panel_id: PANEL_PRIORITY[panel_id])
        remaining = deficit
        for panel_id in flexible:
            if remaining <= 1e-9:
                break
            spare = result[panel_id] - mins[panel_id]
            take = min(spare, remaining)
            result[panel_id] -= take
            remaining -= take
        if remaining > 1e-6:
            # Still short — proportional scale to content.
            total = sum(result.values())
            if total > 0:
                scale = content / total
                result = {panel_id: result[panel_id] * scale for panel_id in result}
            break
    # Final exact fit.
    total = sum(result.values())
    if total > 0 and abs(total - content) > 1e-6:
        scale = content / total
        result = {panel_id: result[panel_id] * scale for panel_id in result}
    return result


def _ratios_from_visible_widths(
    stored: Mapping[str, float],
    widths: Mapping[str, float],
    visible: list[str],
) -> dict[str, float]:
    content = sum(widths[panel_id] for panel_id in visible)
    if content <= 0:
        return normalize_ratios(stored)
    visible_set = set(visible)
    hidden = [panel_id for panel_id in PANEL_IDS if panel_id not in visible_set]
    hidden_mass = sum(float(stored[panel_id]) for panel_id in hidden)
    visible_mass = 1.0 - hidden_mass
    merged: dict[str, float] = {}
    for panel_id in visible:
        merged[panel_id] = (widths[panel_id] / content) * visible_mass
    for panel_id in hidden:
        merged[panel_id] = float(stored[panel_id])
    # Re-normalize to absorb float noise while keeping relative hidden mass.
    return normalize_ratios(merged)


__all__ = [
    "CANONICAL_DEFAULT_RATIOS",
    "HANDLE_WIDTH_PX",
    "LAYOUT_PREFERENCES_SCHEMA_VERSION",
    "PANEL_IDS",
    "PANEL_MIN_WIDTH",
    "LayoutPreferencesLoadResult",
    "LayoutSolution",
    "apply_divider_drag",
    "layout_preferences_path",
    "load_layout_preferences",
    "normalize_ratios",
    "save_layout_preferences",
    "set_harmony_open",
    "solve_widths",
    "visible_panel_ids",
]
