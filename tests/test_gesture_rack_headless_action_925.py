"""Frozen acceptance for R&D Slice 10 — headless gesture Rack action (#680 / #925).

Docs authority: docs/GESTURE_RACK_HEADLESS_ACTION_RND_SLICE10.md

Intentionally RED until src/gesture_rack_headless_action.py exists.
Synthetic tmp_path WAV + SQLite only — no private catalogs, paths, or audio.
Do not weaken / xfail / skip to fit a missing or incorrect Action.

Stage-1 onset is stubbed via monkeypatch of ``analyze_gesture_audio`` so this
suite freezes the Action orchestration contract independently of local onset
DSP drift; domain A still asserts the Action consumes ``audio_path``.
"""

from __future__ import annotations

import ast
import copy
import importlib
import inspect
import sqlite3
from fractions import Fraction
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
import soundfile as sf

from src.channel_rack import ChannelRackState
from src.gesture_analysis import FEATURE_DIM, GestureAnalysis, GestureEvent
from src.pattern_core import Channel, Pattern, Trigger
from src.session_grid import SessionTransport
from src.workbench_channel_rack import ChannelRackController
from src.workbench_live_kit import LiveKitState

# Import under test — RED until IMPLEMENTATION adds the module.
from src.gesture_rack_headless_action import (
    GestureRackHeadlessActionResult,
    prepare_and_apply_gesture_rack,
)

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "gesture_rack_headless_action.py"
)

_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "annotations",
        "__future__",
        "dataclasses",
        "fractions",
        "typing",
        "collections",
        "collections.abc",
        "pathlib",
        "gesture_analysis",
        "src.gesture_analysis",
        "gesture_library_ranking",
        "src.gesture_library_ranking",
        "gesture_catalog_adapter",
        "src.gesture_catalog_adapter",
        "gesture_timing_projection",
        "src.gesture_timing_projection",
        "gesture_pattern_binding",
        "src.gesture_pattern_binding",
        "gesture_pattern_core_composition",
        "src.gesture_pattern_core_composition",
        "gesture_rack_integration",
        "src.gesture_rack_integration",
        "workbench_channel_rack",
        "src.workbench_channel_rack",
        "channel_rack",
        "src.channel_rack",
        "pattern_core",
        "src.pattern_core",
    }
)

_BANNED_IMPORT_ROOTS = frozenset(
    {
        "workbench_session_store",
        "src.workbench_session_store",
        "workbench_feature_settings",
        "src.workbench_feature_settings",
        "workbench_qml",
        "src.workbench_qml",
        "workbench_session",
        "src.workbench_session",
        "sqlalchemy",
        "db",
        "src.db",
        "torch",
    }
)

_BANNED_NAME_CALLS = frozenset(
    {
        "ensure_state",
        "restore_state",
        "add_user_channel",
        "assign_user_channel_sample",
        "load_workbench_feature_settings",
        "save_workbench_feature_settings",
        "save_workbench_session_snapshot",
        "snapshot_from_musical_state",
    }
)

SR = 44100
MFCC_DIM = 13


# ---------------------------------------------------------------------------
# Synthetic audio / catalog / analysis helpers
# ---------------------------------------------------------------------------


def _write_placeholder_wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    y = np.zeros(int(SR * 0.25), dtype=np.float32)
    sf.write(path, y, SR, subtype="PCM_16")
    return path


def _feat(rms: float = 0.25, centroid: float = 1200.0, *, mfcc0: float = 1.0) -> tuple[float, ...]:
    mfcc = (mfcc0,) + tuple(float(i) for i in range(1, MFCC_DIM))
    vec = (rms, centroid) + mfcc
    assert len(vec) == FEATURE_DIM
    return vec


def _ok_analysis(*, cluster_ids: tuple[int, ...] = (0,), onsets: tuple[float, ...] | None = None) -> GestureAnalysis:
    if onsets is None:
        onsets = tuple(0.2 + 0.4 * i for i in range(len(cluster_ids)))
    assert len(onsets) == len(cluster_ids)
    events = tuple(
        GestureEvent(onset, _feat(mfcc0=1.0 + 0.1 * cid), int(cid))
        for onset, cid in zip(onsets, cluster_ids, strict=True)
    )
    return GestureAnalysis(
        events=events,
        sample_rate=SR,
        duration_sec=max(onsets) + 0.5 if onsets else 1.0,
        feature_dim=FEATURE_DIM,
        status="ok",
    )


def _not_ok_analysis(status: str = "empty") -> GestureAnalysis:
    return GestureAnalysis(
        events=(),
        sample_rate=SR,
        duration_sec=0.01,
        feature_dim=FEATURE_DIM,
        status=status,
    )


def _mfcc_blob(values: list[float] | None = None) -> bytes:
    arr = np.asarray(
        values if values is not None else [float(i) for i in range(MFCC_DIM)],
        dtype=np.float32,
    )
    assert arr.shape == (MFCC_DIM,)
    return arr.tobytes()


def _init_catalog(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE samples (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            relpath TEXT,
            samplerate INTEGER,
            channels INTEGER,
            duration REAL,
            size_bytes INTEGER,
            hash TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE features (
            sample_id INTEGER PRIMARY KEY,
            bpm REAL,
            key TEXT,
            key_conf REAL,
            loudness REAL,
            brightness REAL,
            mfcc_mean BLOB,
            mfcc_std BLOB,
            chroma_mean BLOB,
            chroma_std BLOB,
            class TEXT,
            FOREIGN KEY(sample_id) REFERENCES samples(id)
        )
        """
    )
    conn.commit()
    return conn


def _insert_oneshot(
    conn: sqlite3.Connection,
    *,
    sample_id: int,
    path: str,
    loudness: float = -12.0,
    brightness: float = 1200.0,
    mfcc: list[float] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO samples(
            id, path, relpath, samplerate, channels, duration, size_bytes, hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (sample_id, path, Path(path).name, SR, 1, 0.2, 1000, f"hash-{sample_id}"),
    )
    conn.execute(
        """
        INSERT INTO features(
            sample_id, bpm, key, key_conf, loudness, brightness,
            mfcc_mean, mfcc_std, chroma_mean, chroma_std, class
        ) VALUES (?, NULL, NULL, NULL, ?, ?, ?, NULL, NULL, NULL, ?)
        """,
        (sample_id, loudness, brightness, _mfcc_blob(mfcc), "oneshot"),
    )
    conn.commit()


def _catalog_with_oneshots(tmp_path: Path) -> Path:
    path = tmp_path / "gesture_catalog.db"
    conn = _init_catalog(path)
    try:
        _insert_oneshot(
            conn,
            sample_id=101,
            path="synth/kick_a.wav",
            loudness=-10.0,
            brightness=1200.0,
            mfcc=[1.0] + [float(i) for i in range(1, MFCC_DIM)],
        )
        _insert_oneshot(
            conn,
            sample_id=202,
            path="synth/kick_b.wav",
            loudness=-14.0,
            brightness=1500.0,
            mfcc=[2.0] + [float(i) for i in range(1, MFCC_DIM)],
        )
        _insert_oneshot(
            conn,
            sample_id=303,
            path="synth/hat_a.wav",
            loudness=-18.0,
            brightness=4000.0,
            mfcc=[5.0] + [float(i) for i in range(1, MFCC_DIM)],
        )
    finally:
        conn.close()
    return path


# ---------------------------------------------------------------------------
# Rack / controller helpers
# ---------------------------------------------------------------------------


def _live_kit_channel(
    channel_id: str,
    group: str,
    slot: str,
    *,
    sample_path: str | None = "kit.wav",
) -> Channel:
    return Channel(
        channel_id=channel_id,
        live_kit_group=group,
        live_kit_slot=slot,
        sample_path=sample_path,
    )


def _user_channel(channel_id: str, *, sample_path: str = "user.wav") -> Channel:
    return Channel(
        channel_id=channel_id,
        live_kit_group=None,
        live_kit_slot=None,
        sample_path=sample_path,
    )


def _pattern(
    pattern_id: str,
    *,
    length: Fraction = Fraction(4, 1),
    triggers: tuple[Trigger, ...] = (),
) -> Pattern:
    return Pattern(
        pattern_id=pattern_id,
        length_quarter_notes=length,
        triggers=triggers,
    )


def _base_state(
    *,
    channels: tuple[Channel, ...] | None = None,
    pattern: Pattern | None = None,
    step_count: int = 16,
) -> ChannelRackState:
    if channels is None:
        channels = (
            _live_kit_channel("ch_kick", "Kick + Bass", "Kick"),
            _live_kit_channel("ch_bass", "Kick + Bass", "Bass", sample_path=None),
            _user_channel("ch_user_9", sample_path="existing.wav"),
        )
    if pattern is None:
        pattern = _pattern(
            "screen2-main",
            triggers=(
                Trigger(channel_id="ch_kick", position=Fraction(0, 4)),
                Trigger(channel_id="ch_kick", position=Fraction(4, 4)),
                Trigger(channel_id="ch_user_9", position=Fraction(2, 4)),
            ),
        )
    return ChannelRackState(
        channels=channels,
        pattern=pattern,
        step_count=step_count,
    )


def _controller(
    *,
    state: ChannelRackState | None = None,
    on_musical_state_changed=None,
) -> ChannelRackController:
    transport = SessionTransport(sample_rate=48_000, bpm=120.0)
    controller = ChannelRackController(
        live_kit=LiveKitState(),
        transport=transport,
        on_musical_state_changed=on_musical_state_changed,
    )
    if state is not None:
        controller.restore_state(state)
    return controller


def _patch_analysis(monkeypatch: pytest.MonkeyPatch, analysis: GestureAnalysis):
    """Stub Stage 1 wherever the Action may import it from."""
    stub = mock.Mock(return_value=analysis)
    monkeypatch.setattr("src.gesture_analysis.analyze_gesture_audio", stub)
    # Also patch the Action module attribute after import when present.
    try:
        import src.gesture_rack_headless_action as action_mod

        if hasattr(action_mod, "analyze_gesture_audio"):
            monkeypatch.setattr(action_mod, "analyze_gesture_audio", stub)
    except Exception:
        pass
    return stub


def _call_action(
    *,
    audio_path: Path | str,
    channel_rack: ChannelRackController,
    catalog_path: Path | str,
    selections: dict[int, str],
    feature_enabled: bool,
    reference_bpm: float | Fraction = 120.0,
    pattern_length_quarters: Fraction = Fraction(8, 1),
    pattern_id: str = "gesture-pat-slice10",
    allow_pattern_replacement: bool = True,
) -> GestureRackHeadlessActionResult:
    return prepare_and_apply_gesture_rack(
        audio_path,
        channel_rack,
        catalog_path=catalog_path,
        reference_bpm=reference_bpm,
        pattern_length_quarters=pattern_length_quarters,
        selections=selections,
        pattern_id=pattern_id,
        allow_pattern_replacement=allow_pattern_replacement,
        feature_enabled=feature_enabled,
    )


# ---------------------------------------------------------------------------
# K / module contract — import graph + signature
# ---------------------------------------------------------------------------


def test_k1_module_import_graph_allow_and_ban_lists() -> None:
    assert _MODULE_PATH.is_file(), "Action module must exist after implementation"
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            imported.add(node.module.split(".")[0])
            imported.add(node.module)
            if not node.module.startswith("src."):
                imported.add(f"src.{node.module}")

    banned_hit = sorted(imported & _BANNED_IMPORT_ROOTS)
    assert banned_hit == [], f"banned imports present: {banned_hit}"

    for name in sorted(imported):
        if name.startswith("."):
            continue
        root = name.split(".")[0]
        ok = (
            name in _ALLOWED_IMPORT_ROOTS
            or root in _ALLOWED_IMPORT_ROOTS
            or f"src.{root}" in _ALLOWED_IMPORT_ROOTS
        )
        assert ok, f"unexpected import {name!r}"


def test_k2_banned_name_calls_absent_in_action_module() -> None:
    assert _MODULE_PATH.is_file()
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    banned_hit = sorted(called & _BANNED_NAME_CALLS)
    assert banned_hit == [], f"banned calls present: {banned_hit}"


def test_k3_public_signature_kwonly_inputs() -> None:
    sig = inspect.signature(prepare_and_apply_gesture_rack)
    params = sig.parameters
    assert "audio_path" in params
    assert "channel_rack" in params
    for name in (
        "catalog_path",
        "reference_bpm",
        "pattern_length_quarters",
        "selections",
        "pattern_id",
        "allow_pattern_replacement",
        "feature_enabled",
    ):
        assert name in params
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY


# ---------------------------------------------------------------------------
# A. Audio path
# ---------------------------------------------------------------------------


def test_a1_happy_path_consumes_audio_path_and_applies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture_input.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    analysis = _ok_analysis(cluster_ids=(0, 0, 0), onsets=(0.2, 0.6, 1.0))
    analyze_stub = _patch_analysis(monkeypatch, analysis)

    observers: list[str] = []
    base = _base_state()
    controller = _controller(
        state=base,
        on_musical_state_changed=lambda: observers.append("obs"),
    )

    result = _call_action(
        audio_path=audio,
        channel_rack=controller,
        catalog_path=catalog,
        selections={0: "101"},
        feature_enabled=True,
    )

    assert isinstance(result, GestureRackHeadlessActionResult)
    assert result.status == "applied"
    assert result.unresolved_cluster_ids == ()
    assert result.applied_state is not None
    assert result.applied_state == controller.state
    assert result.applied_state != base
    assert result.analysis_status == "ok"
    assert result.binding_plan is not None
    assert result.rack_plan is not None
    assert result.rack_plan.ready_for_apply is True
    assert observers == ["obs"]
    analyze_stub.assert_called()
    called_path = Path(analyze_stub.call_args.args[0])
    assert called_path == audio or called_path.resolve() == audio.resolve()


def test_a2_analysis_not_ok_zero_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "too_short.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _not_ok_analysis("too_short"))

    observers: list[str] = []
    controller = _controller(
        state=_base_state(),
        on_musical_state_changed=lambda: observers.append("obs"),
    )
    before = copy.deepcopy(controller.state)

    result = _call_action(
        audio_path=audio,
        channel_rack=controller,
        catalog_path=catalog,
        selections={},
        feature_enabled=True,
    )

    assert result.status == "analysis_not_ok"
    assert result.applied_state is None
    assert controller.state == before
    assert observers == []
    assert result.analysis_status == "too_short"


# ---------------------------------------------------------------------------
# B. Catalog / ranking — no auto rank-1
# ---------------------------------------------------------------------------


def test_b1_missing_selection_does_not_auto_pick_rank1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0, 0)))

    observers: list[str] = []
    controller = _controller(
        state=_base_state(),
        on_musical_state_changed=lambda: observers.append("obs"),
    )
    before = copy.deepcopy(controller.state)

    result = _call_action(
        audio_path=audio,
        channel_rack=controller,
        catalog_path=catalog,
        selections={},
        feature_enabled=True,
    )

    assert result.status == "unresolved_selections"
    assert result.unresolved_cluster_ids == (0,)
    assert result.applied_state is None
    assert controller.state == before
    assert observers == []
    if result.binding_plan is not None:
        assert result.binding_plan.ready_for_pattern is False


def test_b2_partial_selection_leaves_unresolved_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "abab.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(
        monkeypatch,
        _ok_analysis(cluster_ids=(0, 1, 0, 1), onsets=(0.2, 0.55, 0.9, 1.25)),
    )

    observers: list[str] = []
    controller = _controller(
        state=_base_state(),
        on_musical_state_changed=lambda: observers.append("obs"),
    )
    before = copy.deepcopy(controller.state)

    result = _call_action(
        audio_path=audio,
        channel_rack=controller,
        catalog_path=catalog,
        selections={0: "101"},
        feature_enabled=True,
    )

    assert result.status == "unresolved_selections"
    assert result.unresolved_cluster_ids == (1,)
    assert result.applied_state is None
    assert controller.state == before
    assert observers == []


# ---------------------------------------------------------------------------
# C. Timing Fraction
# ---------------------------------------------------------------------------


def test_c1_binding_plan_uses_exact_fraction_positions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0, 0), onsets=(0.5, 1.0)))
    controller = _controller(state=_base_state())

    result = _call_action(
        audio_path=audio,
        channel_rack=controller,
        catalog_path=catalog,
        selections={0: "101"},
        feature_enabled=True,
        reference_bpm=Fraction(120, 1),
        pattern_length_quarters=Fraction(8, 1),
    )

    assert result.status == "applied"
    assert result.binding_plan is not None
    assert result.binding_plan.pattern_length_quarters == Fraction(8, 1)
    for event in result.binding_plan.event_bindings:
        assert isinstance(event.quarter_position, Fraction)
        assert event.quarter_position >= Fraction(0, 1)
        assert event.quarter_position < Fraction(8, 1)


# ---------------------------------------------------------------------------
# D / E. Selection + explicit pattern id/length
# ---------------------------------------------------------------------------


def test_d1_explicit_non_rank1_selection_is_honored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0, 0)))
    controller = _controller(state=_base_state())

    result = _call_action(
        audio_path=audio,
        channel_rack=controller,
        catalog_path=catalog,
        selections={0: "202"},
        feature_enabled=True,
    )

    assert result.status == "applied"
    assert result.binding_plan is not None
    assert result.binding_plan.channel_bindings
    for binding in result.binding_plan.channel_bindings:
        assert binding.sample_id == "202"
        assert binding.sample_path == "synth/kick_b.wav"


def test_e1_explicit_pattern_id_and_length_reach_applied_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))
    controller = _controller(state=_base_state())
    pattern_id = "explicit-gesture-pattern-10"
    length = Fraction(16, 1)

    result = _call_action(
        audio_path=audio,
        channel_rack=controller,
        catalog_path=catalog,
        selections={0: "101"},
        feature_enabled=True,
        pattern_id=pattern_id,
        pattern_length_quarters=length,
    )

    assert result.status == "applied"
    assert result.applied_state is not None
    assert result.applied_state.pattern.pattern_id == pattern_id
    assert result.applied_state.pattern.length_quarter_notes == length
    assert result.binding_plan is not None
    assert result.binding_plan.pattern_length_quarters == length


# ---------------------------------------------------------------------------
# F. Rack plan replacement / stale / readiness
# ---------------------------------------------------------------------------


def test_f1_replacement_disallowed_returns_not_ready_zero_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))
    observers: list[str] = []
    controller = _controller(
        state=_base_state(),
        on_musical_state_changed=lambda: observers.append("obs"),
    )
    before = copy.deepcopy(controller.state)

    result = _call_action(
        audio_path=audio,
        channel_rack=controller,
        catalog_path=catalog,
        selections={0: "101"},
        feature_enabled=True,
        allow_pattern_replacement=False,
    )

    assert result.status == "not_ready_for_apply"
    assert result.applied_state is None
    assert result.rack_plan is not None
    assert result.rack_plan.ready_for_apply is False
    assert controller.state == before
    assert observers == []


def test_f2_stale_base_state_zero_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))
    observers: list[str] = []
    base = _base_state()
    controller = _controller(
        state=base,
        on_musical_state_changed=lambda: observers.append("obs"),
    )

    real_apply = controller.apply_gesture_integration_plan

    def _mutate_then_apply(plan, *, feature_enabled: bool):
        mutated = ChannelRackState(
            channels=base.channels,
            pattern=_pattern(
                "mutated-elsewhere",
                length=base.pattern.length_quarter_notes,
            ),
            step_count=base.step_count,
        )
        controller.restore_state(mutated)
        return real_apply(plan, feature_enabled=feature_enabled)

    with mock.patch.object(
        controller,
        "apply_gesture_integration_plan",
        side_effect=_mutate_then_apply,
    ):
        result = _call_action(
            audio_path=audio,
            channel_rack=controller,
            catalog_path=catalog,
            selections={0: "101"},
            feature_enabled=True,
        )

    assert result.status == "stale_base_state"
    assert result.applied_state is None
    assert observers == []


# ---------------------------------------------------------------------------
# G. Feature gate
# ---------------------------------------------------------------------------


def test_g1_feature_disabled_zero_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))
    observers: list[str] = []
    controller = _controller(
        state=_base_state(),
        on_musical_state_changed=lambda: observers.append("obs"),
    )
    before = copy.deepcopy(controller.state)
    stop_spy = mock.Mock(wraps=controller.stop)

    with mock.patch.object(controller, "stop", stop_spy):
        result = _call_action(
            audio_path=audio,
            channel_rack=controller,
            catalog_path=catalog,
            selections={0: "101"},
            feature_enabled=False,
        )

    assert result.status == "feature_disabled"
    assert result.applied_state is None
    assert controller.state == before
    assert observers == []
    stop_spy.assert_not_called()


def test_g2_action_does_not_perform_settings_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))
    controller = _controller(state=_base_state())

    with mock.patch(
        "src.workbench_feature_settings.load_workbench_feature_settings",
        side_effect=AssertionError("Action must not load settings"),
    ), mock.patch(
        "src.workbench_feature_settings.save_workbench_feature_settings",
        side_effect=AssertionError("Action must not save settings"),
    ):
        result = _call_action(
            audio_path=audio,
            channel_rack=controller,
            catalog_path=catalog,
            selections={0: "101"},
            feature_enabled=True,
        )

    assert result.status == "applied"


# ---------------------------------------------------------------------------
# H. Apply observer / autosave once
# ---------------------------------------------------------------------------


def test_h1_observer_exactly_once_on_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))
    observers: list[str] = []
    controller = _controller(
        state=_base_state(),
        on_musical_state_changed=lambda: observers.append("obs"),
    )

    result = _call_action(
        audio_path=audio,
        channel_rack=controller,
        catalog_path=catalog,
        selections={0: "101"},
        feature_enabled=True,
    )

    assert result.status == "applied"
    assert observers == ["obs"]


def test_h2_action_does_not_call_session_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))
    controller = _controller(state=_base_state())

    with mock.patch(
        "src.workbench_session_store.save_workbench_session_snapshot",
        side_effect=AssertionError("Action must not write session store"),
    ):
        result = _call_action(
            audio_path=audio,
            channel_rack=controller,
            catalog_path=catalog,
            selections={0: "101"},
            feature_enabled=True,
        )

    assert result.status == "applied"


# ---------------------------------------------------------------------------
# I. Pre-apply failures — zero side effects / state-none
# ---------------------------------------------------------------------------


def test_i1_state_none_no_ensure_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))
    observers: list[str] = []
    controller = _controller(
        state=None,
        on_musical_state_changed=lambda: observers.append("obs"),
    )
    assert controller.state is None
    ensure_spy = mock.Mock(wraps=controller.ensure_state)

    with mock.patch.object(controller, "ensure_state", ensure_spy):
        result = _call_action(
            audio_path=audio,
            channel_rack=controller,
            catalog_path=catalog,
            selections={0: "101"},
            feature_enabled=True,
        )

    assert result.status == "state_none"
    assert result.applied_state is None
    assert controller.state is None
    assert observers == []
    ensure_spy.assert_not_called()


def test_i2_public_state_property_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))
    controller = _controller(state=_base_state())

    reads = {"state": 0}
    original = ChannelRackController.state

    def _counting_state(self):
        reads["state"] += 1
        return original.fget(self)

    with mock.patch.object(ChannelRackController, "state", property(_counting_state)):
        result = _call_action(
            audio_path=audio,
            channel_rack=controller,
            catalog_path=catalog,
            selections={0: "101"},
            feature_enabled=True,
        )

    assert result.status == "applied"
    assert reads["state"] >= 1


# ---------------------------------------------------------------------------
# J. Immutability / determinism of result shape
# ---------------------------------------------------------------------------


def test_j1_result_is_frozen_and_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0, 0), onsets=(0.25, 0.75)))

    c1 = _controller(state=_base_state())
    r1 = _call_action(
        audio_path=audio,
        channel_rack=c1,
        catalog_path=catalog,
        selections={0: "101"},
        feature_enabled=True,
    )
    c2 = _controller(state=_base_state())
    r2 = _call_action(
        audio_path=audio,
        channel_rack=c2,
        catalog_path=catalog,
        selections={0: "101"},
        feature_enabled=True,
    )

    assert r1.status == r2.status == "applied"
    assert r1.unresolved_cluster_ids == r2.unresolved_cluster_ids == ()
    assert r1.applied_state == r2.applied_state
    assert r1.analysis_status == r2.analysis_status == "ok"
    with pytest.raises(Exception):
        r1.status = "mutated"  # type: ignore[misc]


def test_j2_module_reimport_exposes_same_public_symbols() -> None:
    mod = importlib.import_module("src.gesture_rack_headless_action")
    assert hasattr(mod, "prepare_and_apply_gesture_rack")
    assert hasattr(mod, "GestureRackHeadlessActionResult")
    assert callable(mod.prepare_and_apply_gesture_rack)
