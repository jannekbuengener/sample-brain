"""TEST_GATE / TEST_FREEZE — Session ownership (Live Kit + QML → native audition).

Canonical docs:
- docs/PRODUCT_WORKFLOW_CANON.md
- docs/SESSION_OWNERSHIP_CONTRACT.md

Authority for this file: TEST_GATE + TEST_FREEZE only.
Implementation is NOT authorized. Do not weaken, skip, or xfail these tests
to fit current code.

Expected public seam (name fixed here for the freeze; implement later):
``compose_workbench_session`` exposed from ``src.workbench_session`` (preferred)
or re-exported from ``src.workbench_qml``.

Frozen node ids (TEST_FREEZE):
- tests/test_workbench_session_ownership.py::test_compose_workbench_session_api_is_importable
- tests/test_workbench_session_ownership.py::test_session_owns_exactly_one_live_kit_state_instance
- tests/test_workbench_session_ownership.py::test_qml_live_kit_intents_mutate_the_shared_session_kit
- tests/test_workbench_session_ownership.py::test_tk_workbench_and_qml_share_the_same_live_kit_state
- tests/test_workbench_session_ownership.py::test_session_audition_owner_is_transport_aware_preview
- tests/test_workbench_session_ownership.py::test_qml_live_kit_audition_routes_through_session_transport_aware_preview
- tests/test_workbench_session_ownership.py::test_session_audition_stays_monophonic_no_parallel_playback_owner
- tests/test_workbench_session_ownership.py::test_production_qml_screen1_entry_uses_composed_session_ownership
- tests/test_workbench_session_ownership.py::test_ownership_slice_does_not_introduce_screen2_or_pattern_types
- tests/test_workbench_session_ownership.py::test_screen1_assign_replace_semantics_remain_single_slot_overwrite
"""

from __future__ import annotations

import importlib
import inspect
from types import SimpleNamespace

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LiveKitState
from src.workbench_transport_ui import TransportAwarePreview


def _row(name: str = "ownership_kick.wav") -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"synthetic/{name}",
        path=f"synthetic/{name}",
        bpm=132.0,
        key="Am",
        key_conf=0.91,
        loudness=-13.5,
        brightness=3200.0,
        sample_class="one_shot",
        pred_type="Kick",
        status="ok",
        details={"duration_sec": "0.25", "source": "synthetic"},
    )


def _resolve_compose():
    """Locate the session ownership compose seam required by the contract."""

    errors: list[str] = []
    for module_name in ("src.workbench_session", "src.workbench_qml"):
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            errors.append(f"{module_name}: {exc}")
            continue
        compose = getattr(module, "compose_workbench_session", None)
        if callable(compose):
            return compose
        errors.append(f"{module_name}: missing compose_workbench_session")
    pytest.fail(
        "SESSION_OWNERSHIP_CONTRACT requires compose_workbench_session; "
        + "; ".join(errors)
    )


def _compose_session(**kwargs):
    return _resolve_compose()(**kwargs)


def test_compose_workbench_session_api_is_importable():
    compose = _resolve_compose()
    assert callable(compose)


def test_session_owns_exactly_one_live_kit_state_instance():
    session = _compose_session()
    live_kit = session.live_kit
    assert isinstance(live_kit, LiveKitState)
    assert session.live_kit is live_kit
    # Presenter / adapter projections must alias the same object, not a copy.
    presenter_state = getattr(session, "live_kit_presenter", None)
    if presenter_state is not None:
        assert presenter_state.state is live_kit
    qml_adapter = getattr(session, "qml_interaction_adapter", None)
    if qml_adapter is not None and getattr(qml_adapter, "_live_kit", None) is not None:
        assert qml_adapter._live_kit.state is live_kit


def test_qml_live_kit_intents_mutate_the_shared_session_kit():
    session = _compose_session()
    adapter = session.qml_interaction_adapter
    assert adapter is not None, "session must expose qml_interaction_adapter"
    row = _row("shared_assign.wav")

    # Drive the same intent path Screen-1 QML uses (pending → assign).
    adapter._pending_live_kit_row = row
    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
    assert session.live_kit.assignment_for("Drums", "Main Drum") is row
    assert adapter._live_kit.state is session.live_kit


def test_tk_workbench_and_qml_share_the_same_live_kit_state():
    session = _compose_session(include_tk_workbench=True)
    tk_app = session.tk_workbench
    assert tk_app is not None, "include_tk_workbench=True must attach a Tk WorkbenchApp"
    assert tk_app._live_kit_state is session.live_kit

    row = _row("tk_qml_shared.wav")
    session.live_kit.assign("Kick + Bass", "Kick", row)
    assert tk_app._live_kit_state.assignment_for("Kick + Bass", "Kick") is row

    adapter = session.qml_interaction_adapter
    adapter._pending_live_kit_row = _row("from_qml.wav")
    assert adapter.assign_live_kit_slot("Kick + Bass", "Bass") is True
    assert (
        tk_app._live_kit_state.assignment_for("Kick + Bass", "Bass")
        is session.live_kit.assignment_for("Kick + Bass", "Bass")
    )


def test_session_audition_owner_is_transport_aware_preview():
    session = _compose_session()
    audition = session.audition
    assert isinstance(audition, TransportAwarePreview)
    assert not type(audition).__name__ == "WorkbenchPreviewPlayer"
    # Inner legacy player may exist as fallback wrappee; the session owner must
    # still be TransportAwarePreview.
    assert hasattr(audition, "play_row")
    assert hasattr(audition, "_active_voice_id")


def test_qml_live_kit_audition_routes_through_session_transport_aware_preview():
    session = _compose_session()
    adapter = session.qml_interaction_adapter
    audition = session.audition
    assert isinstance(audition, TransportAwarePreview)

    calls: list[object] = []
    original_play_row = audition.play_row

    def tracking_play_row(row, *, start_ms: int = 0):
        calls.append((row, start_ms))
        return SimpleNamespace(ok=True)

    audition.play_row = tracking_play_row  # type: ignore[method-assign]
    try:
        assigned = _row("audition_native.wav")
        session.live_kit.assign("Drums", "Closed Hat", assigned)
        adapter._sync_live_kit_projection()
        assert adapter.audition_live_kit_slot("Drums", "Closed Hat") is True
    finally:
        audition.play_row = original_play_row  # type: ignore[method-assign]

    assert calls == [(assigned, 0)]
    # Adapter must be wired to the session audition owner, not a parallel player.
    assert adapter._on_preview_requested is not None
    bound = adapter._on_preview_requested
    assert (
        getattr(bound, "__self__", None) is audition
        or bound is audition.play_row
        or getattr(getattr(bound, "__func__", None), "__name__", "") == "play_row"
    )


def test_session_audition_stays_monophonic_no_parallel_playback_owner():
    session = _compose_session()
    audition = session.audition
    assert isinstance(audition, TransportAwarePreview)

    # Ownership slice must not grow a second concurrent voice registry / pool.
    assert not hasattr(session, "pattern_voices")
    assert not hasattr(session, "polyphonic_preview")
    assert not hasattr(audition, "_active_voice_ids")
    assert hasattr(audition, "_active_voice_id")

    first = _row("mono_a.wav")
    second = _row("mono_b.wav")
    session.live_kit.assign("Drums", "Main Drum", first)
    session.live_kit.assign("Drums", "Open Hat", second)
    adapter = session.qml_interaction_adapter
    adapter._sync_live_kit_projection()

    play_calls: list[str] = []

    def tracking_play_row(row, *, start_ms: int = 0):
        play_calls.append(row.display_name)
        audition._active_voice_id = len(play_calls)
        return SimpleNamespace(ok=True)

    audition.play_row = tracking_play_row  # type: ignore[method-assign]
    assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True
    assert adapter.audition_live_kit_slot("Drums", "Open Hat") is True
    assert play_calls == ["mono_a.wav", "mono_b.wav"]
    # Still a single-slot owner field after A→B replacement, not a voice list.
    assert audition._active_voice_id == 2
    assert not isinstance(getattr(audition, "_active_voice_id"), (list, set, tuple))


def test_production_qml_screen1_entry_uses_composed_session_ownership():
    """Producer Screen-1 entry must not silently spawn a second kit + legacy player."""

    workbench_qml = importlib.import_module("src.workbench_qml")
    run_source = inspect.getsource(workbench_qml.run_qml_screen1)
    engine_source = inspect.getsource(workbench_qml._qml_engine)

    assert "compose_workbench_session" in run_source or "compose_workbench_session" in engine_source

    # Default adapter construction for the producer path must not leave the
    # Live Kit audition on a bare WorkbenchPreviewPlayer owner.
    # (Wrapping TAP around a legacy player is fine; constructing only the
    # legacy player as on_preview_requested is not.)
    default_branch_uses_legacy_only = (
        "WorkbenchPreviewPlayer()" in engine_source
        and "TransportAwarePreview" not in engine_source
        and "compose_workbench_session" not in engine_source
    )
    assert default_branch_uses_legacy_only is False


def test_ownership_slice_does_not_introduce_screen2_or_pattern_types():
    for module_name in ("src.workbench_session", "src.workbench_qml", "src.workbench"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for forbidden in (
            "ChannelRack",
            "Pattern",
            "PatternTrigger",
            "Screen2",
            "SequencerEngine",
        ):
            assert not hasattr(module, forbidden), f"{module_name}.{forbidden}"


def test_screen1_assign_replace_semantics_remain_single_slot_overwrite():
    """Ownership wiring must not redefine Live Kit assign/replace behavior."""

    session = _compose_session()
    adapter = session.qml_interaction_adapter
    first = _row("first_slot.wav")
    second = _row("replace_slot.wav")

    adapter._pending_live_kit_row = first
    assert adapter.assign_live_kit_slot("Drums", "Percussion") is True
    assert session.live_kit.assignment_for("Drums", "Percussion") is first

    adapter._pending_live_kit_row = second
    assert adapter.assign_live_kit_slot("Drums", "Percussion") is True
    assert session.live_kit.assignment_for("Drums", "Percussion") is second
    assert session.live_kit.assignment_for("Drums", "Main Drum") is None
