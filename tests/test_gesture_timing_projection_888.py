"""Frozen acceptance for R&D Slice 4 — gesture timing projection (#680 / #888).

Docs authority: docs/GESTURE_TIMING_PROJECTION_RND_SLICE4.md

Intentionally RED until src/gesture_timing_projection.py exists.
Synthetic GestureAnalysis fixtures only — no audio assets.
"""

from __future__ import annotations

import ast
import copy
import importlib
import math
from fractions import Fraction
from pathlib import Path

import pytest

from src.gesture_analysis import FEATURE_DIM, GestureAnalysis, GestureEvent
from src.pattern_core import Channel, Pattern, Trigger
from src.session_grid import TempoMap

from src.gesture_timing_projection import (
    GestureTimingProjection,
    ProjectedGestureEvent,
    project_gesture_timing,
)

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "gesture_timing_projection.py"
)

_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "annotations",
        "dataclasses",
        "fractions",
        "math",
        "typing",
        "collections",
        "collections.abc",
        "gesture_analysis",
        "src.gesture_analysis",
    }
)

_BANNED_IMPORT_ROOTS = frozenset(
    {
        "pattern_core",
        "src.pattern_core",
        "channel_rack",
        "src.channel_rack",
        "session_grid",
        "src.session_grid",
        "gesture_library_ranking",
        "src.gesture_library_ranking",
        "gesture_catalog_adapter",
        "src.gesture_catalog_adapter",
        "analyze",
        "src.analyze",
        "config",
        "src.config",
        "config_loader",
        "src.config_loader",
        "workbench_controller",
        "src.workbench_controller",
        "librosa",
        "numpy",
        "torch",
        "sklearn",
        "sqlite3",
        "sqlalchemy",
    }
)


def _feat(*vals: float) -> tuple[float, ...]:
    base = list(vals) + [0.0] * FEATURE_DIM
    return tuple(float(x) for x in base[:FEATURE_DIM])


def _event(
    onset: float,
    cluster_id: int = 0,
    *,
    feature: tuple[float, ...] | None = None,
) -> GestureEvent:
    return GestureEvent(
        onset_time_sec=float(onset),
        feature_vector=feature if feature is not None else _feat(0.2, 1000.0),
        cluster_id=int(cluster_id),
    )


def _analysis(
    events: tuple[GestureEvent, ...] | list[GestureEvent] = (),
    *,
    duration_sec: float = 2.0,
    sample_rate: int = 44100,
    status: str = "ok",
) -> GestureAnalysis:
    ev = tuple(events)
    return GestureAnalysis(
        events=ev,
        sample_rate=sample_rate,
        duration_sec=float(duration_sec),
        feature_dim=FEATURE_DIM,
        status=status if ev or status != "ok" else "empty",
    )


def _ok_analysis(
    onsets: list[float],
    *,
    cluster_ids: list[int] | None = None,
    duration_sec: float | None = None,
) -> GestureAnalysis:
    ids = cluster_ids if cluster_ids is not None else [0] * len(onsets)
    assert len(ids) == len(onsets)
    events = tuple(_event(t, cid) for t, cid in zip(onsets, ids, strict=True))
    dur = duration_sec if duration_sec is not None else max(onsets + [1.0]) + 0.5
    return _analysis(events, duration_sec=dur, status="ok")


def _imported_module_names(mod) -> set[str]:
    path = Path(mod.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
                names.add(node.module)
    return names


def _source_text() -> str:
    return _MODULE_PATH.read_text(encoding="utf-8")


def _expected_quarter(seconds: float | str, bpm: float | int | str | Fraction) -> Fraction:
    sec_f = Fraction(str(seconds)) if not isinstance(seconds, str) else Fraction(seconds)
    if isinstance(bpm, Fraction):
        bpm_f = bpm
    elif isinstance(bpm, bool):
        raise AssertionError("bool must not reach expected helper")
    elif isinstance(bpm, int):
        bpm_f = Fraction(bpm, 1)
    elif isinstance(bpm, float):
        bpm_f = Fraction(str(bpm))
    else:
        bpm_f = Fraction(bpm)
    return sec_f * bpm_f / Fraction(60, 1)


# ---------------------------------------------------------------------------
# Golden / exact conversion cases
# ---------------------------------------------------------------------------


def test_01_zero_seconds_at_120_is_zero_quarters() -> None:
    """1. 0.0 sec @ 120 → Fraction(0, 1)."""
    result = project_gesture_timing(_ok_analysis([0.0]), 120)
    assert result.events[0].quarter_position == Fraction(0, 1)
    assert type(result.events[0].quarter_position) is Fraction


def test_02_half_second_at_120_is_one_quarter() -> None:
    """2. 0.5 sec @ 120 → Fraction(1, 1)."""
    result = project_gesture_timing(_ok_analysis([0.5]), 120)
    assert result.events[0].quarter_position == Fraction(1, 1)


def test_03_one_second_at_120_is_two_quarters() -> None:
    """3. 1.0 sec @ 120 → Fraction(2, 1)."""
    result = project_gesture_timing(_ok_analysis([1.0]), 120)
    assert result.events[0].quarter_position == Fraction(2, 1)


def test_04_quarter_second_at_120_is_half_quarter() -> None:
    """4. 0.25 sec @ 120 → Fraction(1, 2)."""
    result = project_gesture_timing(_ok_analysis([0.25]), 120)
    assert result.events[0].quarter_position == Fraction(1, 2)


def test_05_non_integer_bpm_127_5_is_exact() -> None:
    """5. 127.5 BPM deterministic exact case."""
    result = project_gesture_timing(_ok_analysis([1.0]), 127.5)
    assert result.events[0].quarter_position == Fraction(17, 8)
    assert result.reference_bpm == Fraction("127.5")


def test_06_fraction_bpm_input_accepted() -> None:
    """6. Fraction BPM input if public API allows it."""
    bpm = Fraction(240, 2)  # 120
    result = project_gesture_timing(_ok_analysis([0.5]), bpm)
    assert result.events[0].quarter_position == Fraction(1, 1)
    assert result.reference_bpm == Fraction(120, 1) or result.reference_bpm == bpm


def test_07_string_bpm_input_accepted() -> None:
    """7. string BPM input if public API allows it."""
    result = project_gesture_timing(_ok_analysis([0.5]), "120")
    assert result.events[0].quarter_position == Fraction(1, 1)
    assert result.reference_bpm == Fraction(120, 1)


# ---------------------------------------------------------------------------
# Origin / order / cluster identity
# ---------------------------------------------------------------------------


def test_08_leading_silence_preserved() -> None:
    """8. leading silence preserved."""
    result = project_gesture_timing(_ok_analysis([0.25, 0.75], duration_sec=2.0), 120)
    assert result.events[0].quarter_position == Fraction(1, 2)
    assert result.events[1].quarter_position == Fraction(3, 2)


def test_09_first_onset_not_normalized_to_zero() -> None:
    """9. first onset NOT normalized to zero."""
    result = project_gesture_timing(_ok_analysis([0.25, 0.75]), 120)
    assert result.events[0].quarter_position != Fraction(0, 1)
    assert result.events[0].source_onset_sec == 0.25
    assert result.events[0].quarter_position == Fraction(1, 2)


def test_10_multiple_events_preserve_order() -> None:
    """10. multiple events preserve order."""
    onsets = [0.1, 0.4, 0.9, 1.3]
    result = project_gesture_timing(_ok_analysis(onsets), 120)
    assert [e.source_onset_sec for e in result.events] == onsets
    assert [e.quarter_position for e in result.events] == [
        _expected_quarter(t, 120) for t in onsets
    ]


def test_11_same_cluster_id_events_stay_separate() -> None:
    """11. same cluster ID events stay separate."""
    analysis = _ok_analysis([0.0, 0.5, 1.0], cluster_ids=[0, 0, 0])
    result = project_gesture_timing(analysis, 120)
    assert len(result.events) == 3
    assert [e.cluster_id for e in result.events] == [0, 0, 0]
    assert [e.quarter_position for e in result.events] == [
        Fraction(0, 1),
        Fraction(1, 1),
        Fraction(2, 1),
    ]


def test_12_cluster_ids_unchanged() -> None:
    """12. cluster IDs unchanged."""
    analysis = _ok_analysis([0.2, 0.5, 0.9], cluster_ids=[2, 0, 2])
    result = project_gesture_timing(analysis, 100)
    assert [e.cluster_id for e in result.events] == [2, 0, 2]


# ---------------------------------------------------------------------------
# Duration evidence
# ---------------------------------------------------------------------------


def test_13_projected_duration_uses_same_conversion() -> None:
    """13. projected duration uses same conversion."""
    analysis = _ok_analysis([0.5], duration_sec=2.0)
    result = project_gesture_timing(analysis, 120)
    assert result.projected_duration_quarters == _expected_quarter(2.0, 120)
    assert result.projected_duration_quarters == Fraction(4, 1)


def test_14_projected_duration_separate_from_pattern_length() -> None:
    """14. projected duration is exposed separately from Pattern."""
    result = project_gesture_timing(_ok_analysis([0.5], duration_sec=1.5), 120)
    assert hasattr(result, "projected_duration_quarters")
    assert not hasattr(result, "length_quarter_notes")
    assert not isinstance(result, Pattern)
    # Evidence field exists; Pattern length authority is not claimed.
    assert result.projected_duration_quarters == Fraction(3, 1)


# ---------------------------------------------------------------------------
# Empty / fail-soft statuses
# ---------------------------------------------------------------------------


def test_15_empty_analysis_empty_events() -> None:
    """15. empty analysis → empty events."""
    analysis = _analysis((), duration_sec=1.0, status="empty")
    result = project_gesture_timing(analysis, 120)
    assert result.events == ()
    assert isinstance(result, GestureTimingProjection)
    assert result.projected_duration_quarters == Fraction(2, 1)


@pytest.mark.parametrize("status", ["too_short", "unreadable"])
def test_16_too_short_or_unreadable_empty_events(status: str) -> None:
    """16. too_short/unreadable empty analysis → empty events."""
    duration = 0.0 if status == "unreadable" else 0.02
    analysis = _analysis((), duration_sec=duration, status=status)
    result = project_gesture_timing(analysis, 120)
    assert result.events == ()
    assert result.projected_duration_quarters == _expected_quarter(duration, 120)


# ---------------------------------------------------------------------------
# Fail-closed BPM
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bpm", [0, 0.0, "0", Fraction(0, 1)])
def test_17_bpm_zero_fail_closed(bpm) -> None:
    """17. BPM zero → fail closed."""
    with pytest.raises((ValueError, TypeError)):
        project_gesture_timing(_ok_analysis([0.5]), bpm)


@pytest.mark.parametrize("bpm", [-1, -120.0, "-3", Fraction(-5, 1)])
def test_18_bpm_negative_fail_closed(bpm) -> None:
    """18. BPM negative → fail closed."""
    with pytest.raises((ValueError, TypeError)):
        project_gesture_timing(_ok_analysis([0.5]), bpm)


def test_19_bpm_nan_fail_closed() -> None:
    """19. BPM NaN → fail closed (isfinite before Fraction(str))."""
    with pytest.raises((ValueError, TypeError)):
        project_gesture_timing(_ok_analysis([0.5]), float("nan"))


@pytest.mark.parametrize("bpm", [float("inf"), float("-inf")])
def test_20_bpm_inf_fail_closed(bpm: float) -> None:
    """20. BPM Inf → fail closed (isfinite before Fraction(str))."""
    with pytest.raises((ValueError, TypeError)):
        project_gesture_timing(_ok_analysis([0.5]), bpm)


def test_20b_bpm_bool_rejected_before_int() -> None:
    """bool is an int subtype — must be rejected before int coercion."""
    with pytest.raises(TypeError):
        project_gesture_timing(_ok_analysis([0.5]), True)
    with pytest.raises(TypeError):
        project_gesture_timing(_ok_analysis([0.5]), False)


# ---------------------------------------------------------------------------
# Fail-closed onset / duration / sample_rate
# ---------------------------------------------------------------------------


def test_21_negative_onset_fail_closed() -> None:
    """21. negative onset → fail closed."""
    analysis = _analysis((_event(-0.1),), duration_sec=1.0, status="ok")
    with pytest.raises(ValueError):
        project_gesture_timing(analysis, 120)


@pytest.mark.parametrize("onset", [float("nan"), float("inf"), float("-inf")])
def test_22_onset_nan_inf_fail_closed(onset: float) -> None:
    """22. onset NaN/Inf → fail closed."""
    analysis = _analysis((_event(0.0),), duration_sec=1.0, status="ok")
    # Bypass GestureEvent helper float() path with object.__setattr__ if frozen.
    bad = GestureEvent(
        onset_time_sec=0.0,
        feature_vector=_feat(0.1, 100.0),
        cluster_id=0,
    )
    object.__setattr__(bad, "onset_time_sec", onset)
    analysis = _analysis((bad,), duration_sec=1.0, status="ok")
    with pytest.raises(ValueError):
        project_gesture_timing(analysis, 120)


def test_23_onset_greater_than_duration_fail_closed() -> None:
    """23. onset > duration → fail closed."""
    analysis = _analysis((_event(1.5),), duration_sec=1.0, status="ok")
    with pytest.raises(ValueError):
        project_gesture_timing(analysis, 120)


@pytest.mark.parametrize("duration", [-1.0, float("nan"), float("inf"), float("-inf")])
def test_24_malformed_duration_fail_closed(duration: float) -> None:
    """24. malformed duration → fail closed."""
    analysis = GestureAnalysis(
        events=(_event(0.0),),
        sample_rate=44100,
        duration_sec=0.0,
        feature_dim=FEATURE_DIM,
        status="ok",
    )
    object.__setattr__(analysis, "duration_sec", duration)
    with pytest.raises(ValueError):
        project_gesture_timing(analysis, 120)


@pytest.mark.parametrize("sample_rate", [0, -44100, True, 44100.0, "44100"])
def test_25_invalid_sample_rate_fail_closed(sample_rate) -> None:
    """25. invalid sample_rate → fail closed (structural invariant)."""
    analysis = GestureAnalysis(
        events=(_event(0.0),),
        sample_rate=44100,
        duration_sec=1.0,
        feature_dim=FEATURE_DIM,
        status="ok",
    )
    object.__setattr__(analysis, "sample_rate", sample_rate)
    with pytest.raises((ValueError, TypeError)):
        project_gesture_timing(analysis, 120)


def test_25b_non_monotonic_event_order_fail_closed() -> None:
    """Event order must be strictly increasing — no silent reorder."""
    analysis = _analysis(
        (_event(0.5), _event(0.2)),
        duration_sec=1.0,
        status="ok",
    )
    with pytest.raises(ValueError):
        project_gesture_timing(analysis, 120)


# ---------------------------------------------------------------------------
# Determinism / immutability
# ---------------------------------------------------------------------------


def test_26_identical_input_twice_identical_fractions() -> None:
    """26. identical input twice → exact identical Fraction outputs."""
    analysis = _ok_analysis([0.25, 0.5, 1.0], duration_sec=2.0)
    a = project_gesture_timing(analysis, 127.5)
    b = project_gesture_timing(analysis, 127.5)
    assert a == b
    assert [e.quarter_position for e in a.events] == [
        e.quarter_position for e in b.events
    ]
    assert a.projected_duration_quarters == b.projected_duration_quarters
    assert a.reference_bpm == b.reference_bpm


def test_27_input_gesture_analysis_unchanged() -> None:
    """27. input GestureAnalysis unchanged."""
    analysis = _ok_analysis([0.25, 0.75], cluster_ids=[1, 2], duration_sec=2.0)
    before = copy.deepcopy(analysis)
    project_gesture_timing(analysis, 120)
    assert analysis == before
    assert analysis.events[0].onset_time_sec == 0.25
    assert analysis.events[0].cluster_id == 1


# ---------------------------------------------------------------------------
# Scope / import / mutation guards
# ---------------------------------------------------------------------------


def test_28_no_pattern_instance() -> None:
    """28. no Pattern instance."""
    result = project_gesture_timing(_ok_analysis([0.5]), 120)
    assert not isinstance(result, Pattern)
    assert all(not isinstance(e, Pattern) for e in result.events)


def test_29_no_trigger_instance() -> None:
    """29. no Trigger instance."""
    result = project_gesture_timing(_ok_analysis([0.5]), 120)
    assert not isinstance(result, Trigger)
    assert all(not isinstance(e, Trigger) for e in result.events)


def test_30_no_channel_instance() -> None:
    """30. no Channel instance."""
    result = project_gesture_timing(_ok_analysis([0.5]), 120)
    assert not isinstance(result, Channel)
    assert all(not isinstance(e, Channel) for e in result.events)


def test_31_no_quantization_helper() -> None:
    """31. no quantization helper."""
    src = _source_text().lower()
    for token in (
        "quantize",
        "quantise",
        "snap_to",
        "grid_snap",
        "swing",
        "groove",
        "nearest_16",
        "nearest_beat",
    ):
        assert token not in src
    result = project_gesture_timing(_ok_analysis([0.3]), 120)
    # Unquantized: 0.3s @ 120 = 0.6 quarters = 3/5 exactly via Fraction(str).
    assert result.events[0].quarter_position == Fraction("0.3") * Fraction(120) / 60


def test_32_no_bpm_analyzer_import() -> None:
    """32. no BPM analyzer/import."""
    mod = importlib.import_module("src.gesture_timing_projection")
    imported = _imported_module_names(mod)
    assert imported <= _ALLOWED_IMPORT_ROOTS | {"__future__"}
    for banned in ("analyze", "librosa", "beat_track", "tempo"):
        assert banned not in imported
    src = _source_text().lower()
    for token in ("beat_track", "tempo_estimate", "estimate_tempo", "onset_detect"):
        assert token not in src


def test_33_no_global_or_session_bpm_lookup() -> None:
    """33. no global/session BPM lookup."""
    mod = importlib.import_module("src.gesture_timing_projection")
    imported = _imported_module_names(mod)
    for banned in _BANNED_IMPORT_ROOTS:
        assert banned not in imported
    src = _source_text()
    for token in (
        "SessionTransport",
        "workbench_controller",
        "get_profile",
        "load_profile",
        "ANALYZE_BPM",
        "config_loader",
    ):
        assert token not in src


def test_34_no_catalog_or_ranking_mutation() -> None:
    """34. no catalog/ranking mutation."""
    mod = importlib.import_module("src.gesture_timing_projection")
    imported = _imported_module_names(mod)
    for banned in (
        "gesture_library_ranking",
        "gesture_catalog_adapter",
        "sqlite3",
        "sqlalchemy",
    ):
        assert banned not in imported
    src = _source_text()
    for token in (
        "rank_gesture",
        "LibraryCandidate",
        "load_gesture_library",
        "init_db",
        "INSERT",
        "UPDATE",
    ):
        assert token not in src


def test_35_projected_quarters_compatible_with_trigger_position() -> None:
    """35. TEST-ONLY: projected quarters pass Trigger(position=...) without projector creating Trigger."""
    result = project_gesture_timing(_ok_analysis([0.0, 0.25, 0.5]), 120)
    for event in result.events:
        trigger = Trigger(channel_id="ch_kick", position=event.quarter_position)
        assert trigger.position == event.quarter_position
        assert type(trigger.position) is Fraction
    # Projector result itself must not be / contain Trigger.
    assert not isinstance(result, Trigger)
    assert all(not isinstance(e, Trigger) for e in result.events)
    assert all(isinstance(e, ProjectedGestureEvent) for e in result.events)


def test_36_tempomap_constant_bpm_semantic_consistency() -> None:
    """36. TempoMap semantic consistency for constant reference BPM."""
    sr = 48_000
    bpm = 120
    onsets = [0.0, 0.5, 1.0]
    result = project_gesture_timing(
        _ok_analysis(onsets, duration_sec=2.0),
        bpm,
    )
    tempo_map = TempoMap(sample_rate=sr, bpm=bpm)
    for event, t in zip(result.events, onsets, strict=True):
        frame = int(round(t * sr))
        assert event.quarter_position == tempo_map.frame_to_quarter_note(frame)
        assert event.quarter_position == _expected_quarter(t, bpm)

    # 127.5 BPM parity with closed form / TempoMap
    result_b = project_gesture_timing(_ok_analysis([1.0], duration_sec=2.0), 127.5)
    tempo_b = TempoMap(sample_rate=sr, bpm=127.5)
    assert result_b.events[0].quarter_position == tempo_b.frame_to_quarter_note(sr)
    assert result_b.events[0].quarter_position == Fraction(17, 8)


def test_result_preserves_source_onset_evidence() -> None:
    """Output preserves source timing evidence alongside quarters."""
    result = project_gesture_timing(_ok_analysis([0.25]), 120)
    assert result.events[0].source_onset_sec == 0.25
    assert result.reference_bpm == Fraction(120, 1)


def test_module_has_no_pattern_trigger_channel_construction() -> None:
    """AST: projector module must not construct Pattern/Trigger/Channel."""
    tree = ast.parse(_source_text())
    banned_calls = {"Pattern", "Trigger", "Channel"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            assert name not in banned_calls
