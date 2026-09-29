"""RED contracts for #694 — pure-Python elastic layout solver.

Canon: docs/WORKBENCH_ELASTIC_LAYOUT.md
Frozen once implementation begins (TEST_FREEZE).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from src.workbench_layout_solver import (
    CANONICAL_DEFAULT_RATIOS,
    HANDLE_WIDTH_PX,
    LAYOUT_PREFERENCES_SCHEMA_VERSION,
    PANEL_IDS,
    apply_divider_drag,
    layout_preferences_path,
    load_layout_preferences,
    normalize_ratios,
    save_layout_preferences,
    set_harmony_open,
    solve_widths,
    visible_panel_ids,
)


def test_panel_ids_and_canonical_defaults_are_stable():
    assert PANEL_IDS == ("library", "browser", "harmony", "livekit")
    assert set(CANONICAL_DEFAULT_RATIOS) == set(PANEL_IDS)
    assert all(v > 0 and math.isfinite(v) for v in CANONICAL_DEFAULT_RATIOS.values())
    assert abs(sum(CANONICAL_DEFAULT_RATIOS.values()) - 1.0) < 1e-12


def test_normalize_ratios_rejects_non_finite_non_positive_and_unknown_ids():
    with pytest.raises(ValueError):
        normalize_ratios({"library": 0.2, "browser": float("nan"), "harmony": 0.2, "livekit": 0.2})
    with pytest.raises(ValueError):
        normalize_ratios({"library": 0.2, "browser": float("inf"), "harmony": 0.2, "livekit": 0.2})
    with pytest.raises(ValueError):
        normalize_ratios({"library": 0.2, "browser": 0.0, "harmony": 0.2, "livekit": 0.2})
    with pytest.raises(ValueError):
        normalize_ratios({"library": 0.2, "browser": 0.3, "harmony": 0.2, "livekit": 0.2, "dock": 0.1})
    with pytest.raises(ValueError):
        normalize_ratios({"library": 0.5, "browser": 0.5})  # missing ids


def test_normalize_ratios_returns_finite_positive_unit_sum():
    raw = {"library": 1.0, "browser": 2.0, "harmony": 1.0, "livekit": 1.0}
    out = normalize_ratios(raw)
    assert abs(sum(out.values()) - 1.0) < 1e-12
    assert all(v > 0 and math.isfinite(v) for v in out.values())
    assert out["browser"] > out["library"]


def test_visible_panel_ids_active_workspace_3_and_4():
    assert visible_panel_ids(harmony_open=False, has_active_source=True) == (
        "library",
        "browser",
        "livekit",
    )
    assert visible_panel_ids(harmony_open=True, has_active_source=True) == (
        "library",
        "browser",
        "harmony",
        "livekit",
    )
    assert visible_panel_ids(harmony_open=False, has_active_source=False) == ()


def test_solve_widths_sum_plus_handles_equals_available():
    ratios = dict(CANONICAL_DEFAULT_RATIOS)
    available = 1600.0
    solution = solve_widths(
        ratios,
        available_width=available,
        harmony_open=True,
        has_active_source=True,
    )
    visible = visible_panel_ids(harmony_open=True, has_active_source=True)
    handle_budget = HANDLE_WIDTH_PX * max(0, len(visible) - 1)
    assert abs(sum(solution.widths[p] for p in visible) + handle_budget - available) < 1e-6
    assert solution.fallback is None
    assert all(solution.widths[p] > 0 for p in visible)
    assert "harmony" in solution.widths


def test_direct_neighbour_reacts_stronger_than_farther_same_side():
    ratios = dict(CANONICAL_DEFAULT_RATIOS)
    available = 1600.0
    # Divider between browser and livekit in 3-panel mode (library | browser | livekit)
    before = solve_widths(
        ratios,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
    )
    after_ratios = apply_divider_drag(
        ratios,
        divider_after="browser",
        delta_px=40.0,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
    )
    after = solve_widths(
        after_ratios,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
    )
    # Rightward drag: left gains, right loses. Direct left neighbour = browser;
    # farther left = library. Direct right = livekit.
    browser_gain = after.widths["browser"] - before.widths["browser"]
    library_gain = after.widths["library"] - before.widths["library"]
    assert browser_gain > library_gain >= 0
    assert after.widths["livekit"] < before.widths["livekit"]


def test_min_saturation_redistributes_residual_delta():
    # Force livekit against its minimum so residual must go elsewhere.
    ratios = normalize_ratios(
        {"library": 0.05, "browser": 0.70, "harmony": 0.05, "livekit": 0.20}
    )
    available = 1120.0
    before = solve_widths(
        ratios,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
    )
    # Large leftward drag: try to grow livekit by shrinking browser hard.
    after_ratios = apply_divider_drag(
        ratios,
        divider_after="browser",
        delta_px=-400.0,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
    )
    after = solve_widths(
        after_ratios,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
    )
    assert after.widths["livekit"] >= before.widths["livekit"] - 1e-6
    # No negative / NaN and width budget conserved.
    visible = visible_panel_ids(harmony_open=False, has_active_source=True)
    handle_budget = HANDLE_WIDTH_PX * max(0, len(visible) - 1)
    assert abs(sum(after.widths[p] for p in visible) + handle_budget - available) < 1e-6
    assert all(math.isfinite(w) and w > 0 for w in after.widths.values())


def test_thousand_drag_steps_accumulate_no_relevant_ratio_drift():
    ratios = dict(CANONICAL_DEFAULT_RATIOS)
    available = 1600.0
    current = dict(ratios)
    for step in range(1000):
        delta = 3.0 if step % 2 == 0 else -3.0
        current = apply_divider_drag(
            current,
            divider_after="browser",
            delta_px=delta,
            available_width=available,
            harmony_open=True,
            has_active_source=True,
        )
    # Pairwise undo should land near start; residual drift must stay tiny.
    assert all(math.isfinite(v) and v > 0 for v in current.values())
    assert abs(sum(current.values()) - 1.0) < 1e-9
    for panel_id, start in ratios.items():
        assert abs(current[panel_id] - start) < 1e-6


def test_window_resize_preserves_ratios():
    ratios = dict(CANONICAL_DEFAULT_RATIOS)
    a = solve_widths(
        ratios, available_width=1600.0, harmony_open=False, has_active_source=True
    )
    b = solve_widths(
        ratios, available_width=1280.0, harmony_open=False, has_active_source=True
    )
    assert a.ratios == b.ratios == normalize_ratios(ratios)
    assert a.widths["browser"] > b.widths["browser"]


def test_three_to_four_panel_toggle_and_harmony_roundtrip_without_drift():
    ratios = dict(CANONICAL_DEFAULT_RATIOS)
    closed = set_harmony_open(ratios, False)
    opened = set_harmony_open(closed, True)
    closed_again = set_harmony_open(opened, False)
    opened_again = set_harmony_open(closed_again, True)
    for panel_id in PANEL_IDS:
        assert abs(opened[panel_id] - opened_again[panel_id]) < 1e-12
        assert abs(closed[panel_id] - closed_again[panel_id]) < 1e-12
    # Stored harmony ratio remains present while closed (not zeroed).
    assert closed["harmony"] > 0
    three = solve_widths(
        closed, available_width=1600.0, harmony_open=False, has_active_source=True
    )
    four = solve_widths(
        opened, available_width=1600.0, harmony_open=True, has_active_source=True
    )
    assert "harmony" not in three.widths
    assert "harmony" in four.widths
    assert four.widths["harmony"] > 0


def test_responsive_fallback_when_hard_minima_do_not_fit():
    ratios = dict(CANONICAL_DEFAULT_RATIOS)
    # 3-panel mins 230+480+220=930 + 2*6 handles = 942; force below that.
    available = 800.0
    solution = solve_widths(
        ratios,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
    )
    assert solution.fallback == "proportional_min_overflow"
    visible = visible_panel_ids(harmony_open=False, has_active_source=True)
    handle_budget = HANDLE_WIDTH_PX * max(0, len(visible) - 1)
    assert abs(sum(solution.widths[p] for p in visible) + handle_budget - available) < 1e-6


def test_layout_preferences_persist_and_restore_ratios_only(tmp_path: Path):
    ratios = normalize_ratios(
        {"library": 0.22, "browser": 0.48, "harmony": 0.16, "livekit": 0.14}
    )
    path = layout_preferences_path(state_dir=tmp_path)
    save_layout_preferences(ratios, state_dir=tmp_path)
    assert path.is_file()
    loaded = load_layout_preferences(state_dir=tmp_path)
    assert loaded.persistable is True
    assert loaded.ratios == ratios
    assert loaded.schema_version == LAYOUT_PREFERENCES_SCHEMA_VERSION


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version": 1, "panel_ratios": {"library": 0.2, "browser": "nan", "harmony": 0.2, "livekit": 0.2}}',
        '{"schema_version": 1, "panel_ratios": {"library": 0.2, "browser": 0.3, "harmony": 0.2, "livekit": 0.2, "dock": 0.1}}',
        '{"schema_version": 99, "panel_ratios": {"library": 0.25, "browser": 0.25, "harmony": 0.25, "livekit": 0.25}}',
        "not-json",
    ],
)
def test_corrupt_layout_preferences_fail_closed(tmp_path: Path, payload: str):
    path = layout_preferences_path(state_dir=tmp_path)
    path.write_text(payload, encoding="utf-8")
    loaded = load_layout_preferences(state_dir=tmp_path)
    assert loaded.persistable is False
    assert loaded.ratios == dict(CANONICAL_DEFAULT_RATIOS)


def test_inf_ratio_in_on_disk_blob_fail_closed(tmp_path: Path):
    path = layout_preferences_path(state_dir=tmp_path)
    # JSON cannot encode Inf; emulate a hand-edited corrupt numeric blob via Python.
    import json

    path.write_text(
        json.dumps(
            {
                "schema_version": LAYOUT_PREFERENCES_SCHEMA_VERSION,
                "panel_ratios": {
                    "library": 0.2,
                    "browser": 1e308 * 1e308,  # overflows to Inf when written via allow_nan
                    "harmony": 0.2,
                    "livekit": 0.2,
                },
            },
            allow_nan=True,
        ),
        encoding="utf-8",
    )
    loaded = load_layout_preferences(state_dir=tmp_path)
    assert loaded.persistable is False
    assert loaded.ratios == dict(CANONICAL_DEFAULT_RATIOS)
