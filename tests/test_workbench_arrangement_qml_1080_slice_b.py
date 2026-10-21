"""#1080 Slice B TEST_FREEZE — interactive canonical 32-field sequencer.

Canonical authority:
- docs/ARRANGEMENT_32_FIELD_TIME_CONTRACT.md (#1083/#1086)
- docs/SESSION_OWNERSHIP_CONTRACT.md (#678/#809)
- docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md (#952)
- docs/design/1079-arrangement-visual-gate/DESIGN_CONTRACT.md (Direction B)
- src/arrangement_32_field_time.py (#1086 sole field/quarter-note authority)
- src/workbench_session.py (#1078 projection-mode owner)
- src/workbench_channel_rack.py (ChannelRackController, single rack truth)

Slice B scope (frozen): the Slice A read-only Arrangement sequencer becomes
productively interactive through the *canonical* #1086 field semantics:

1. channel-aware 32-field projection (renderer-facing channel rows);
2. exact #1086 field mutation — field 0 → qn 0, field 1 → qn 1, field 31 →
   qn 31, never the legacy ``step_index / 4`` 16th-note semantics;
3. one Step click → exactly one Python-owned Pattern mutation on the ONE
   Pattern truth via ``ChannelRackController.toggle_arrangement_field``;
4. immediate canonical reprojection from Python truth (no QML local truth);
5. persistence/re-entry correctness through the existing musical-state
   autosave owner (no second save seam);
6. the Direction-B sequencer geometry (32 fields, 8×4 grouping, precise
   rectangular hit targets) is preserved.

Explicitly out of scope for Slice B: 16-bar block mutation, group/track
masks, expand/collapse, zoom/pan, virtualization, end marker, render
eligibility UI, Arrangement DnD, Live, Mixer/Piano Roll/Automation.

Frozen gates (do not weaken during implementation):
1. field 0 mutation ⇒ Trigger qn == 0;
2. field 1 mutation ⇒ Trigger qn == 1, explicitly NOT Fraction(1, 4);
3. field 31 mutation ⇒ Trigger qn == 31;
4. exactly one click ⇒ exactly one controller mutation ⇒ exactly one
   musical-state notification;
5. toggle twice ⇒ Trigger removed ⇒ same Pattern identity / pattern_id;
6. invalid field -1 ⇒ no mutation (fail closed);
7. invalid field 32 ⇒ no mutation (fail closed);
8. unknown channel ⇒ no mutation (fail closed);
9. legacy / non-32-field rack ⇒ fail closed, no silent migration;
10. one-shot row ⇒ 32 editable fields;
11. loop row ⇒ no editable step matrix ⇒ QML intent mutates nothing;
12. ambiguous row ⇒ no editable step matrix ⇒ QML intent mutates nothing;
13. first active field ⇒ Slice A upper stage becomes active;
14. last active field removed ⇒ upper stage becomes quiet again;
15. successful mutation persists through the EXISTING active-track autosave
    owner — no second store/save seam;
16. return to Edit + re-entry keeps the mutation, the same active_track_id
    and the same Pattern owner;
17. pure projection refresh ⇒ no musical mutation, no serialization;
18. Arrangement Step click ⇒ no browser audition / pointer fall-through;
19. legacy ``ChannelRackController.toggle_step`` behavior stays unchanged
    (the protected 16th-note seam);
20. pending/deferred legacy user-channel mutation state ⇒ controlled
    fail-closed for the new field mutation — never ``step_index / 4`` for
    an Arrangement field.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

import pytest

from src import track_package as tp
from src import workbench_session as ws
from src.workbench_session_store import snapshot_from_track_package_musical
from src.arrangement_32_field_time import (
    TOTAL_FIELDS,
    add_user_channel_32_field,
    build_32_field_channel_rack_state,
    build_32_field_pattern,
)
from src.channel_rack import ChannelRackState, build_channel_rack_state
from src.native_audio import (
    SB_MAX_VOICES,
    SB_VOICE_IDLE,
    SB_VOICE_PLAYING,
    SB_VOICE_SCHEDULED,
    VoiceConfig,
)
from src.pattern_core import CHANNEL_ID_BY_LIVE_KIT_SLOT, Channel, Trigger
from src.sequencer_pcm import SequencerPcmProvider
from src.session_grid import SessionTransport
from src.workbench_channel_rack import ChannelRackController
from src.workbench_controller import WorkbenchRow
from src.workbench_feature_settings import (
    WorkbenchFeatureSettings,
    save_workbench_feature_settings,
)
from src.workbench_live_kit import LiveKitState
from src.workbench_qml import QML_SOURCE
from src.workbench_session_store import active_track_pointer_path
from tests.audio_fixtures import write_sine_wav

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

KICK_ID = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Kick + Bass", "Kick")]
PAD_ID = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Melodic", "Pad")]

SAMPLE_RATE = 48_000
BPM = 120.0
PCM_FRAMES = 8


# --- production-surface accessors (repo pattern) --------------------------------


def _projection_module_or_fail():
    try:
        return importlib.import_module("src.workbench_arrangement_qml")
    except ModuleNotFoundError as exc:
        if exc.name is not None and exc.name.endswith("workbench_arrangement_qml"):
            pytest.fail(
                "MISSING_PRODUCTION_SURFACE: src.workbench_arrangement_qml "
                "(#1080 Slice B channel-aware Arrangement projection seam)"
            )
        raise


def _controller_module_or_fail():
    try:
        return importlib.import_module("src.workbench_channel_rack")
    except ModuleNotFoundError as exc:
        if exc.name is not None and exc.name.endswith("workbench_channel_rack"):
            pytest.fail(
                "MISSING_PRODUCTION_SURFACE: src.workbench_channel_rack"
            )
        raise


def _require(module, name: str):
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"MISSING_PRODUCTION_SURFACE: {module.__name__}.{name}")
    return value


def _project(session):
    return _projection_module_or_fail().project_arrangement_for_qml(session)


def _request_toggle(session, channel_id, field_index):
    module = _projection_module_or_fail()
    seam = _require(module, "request_arrangement_field_toggle")
    return seam(session, channel_id, field_index)


def _toggle_arrangement_field(controller, channel_id, field_index):
    command = _require(_controller_module_or_fail(), "ChannelRackController")
    method = getattr(command, "toggle_arrangement_field", None)
    if method is None:
        pytest.fail(
            "MISSING_PRODUCTION_SURFACE: "
            "ChannelRackController.toggle_arrangement_field"
        )
    return method(controller, channel_id, field_index)


# --- session fixtures ------------------------------------------------------------


@pytest.fixture
def draft(tmp_path):
    session = ws.compose_workbench_session(state_dir=tmp_path / "state")
    source = tmp_path / "kick.wav"
    write_sine_wav(source, duration_sec=0.05, frequency_hz=60)
    session.live_kit.assign("Kick + Bass", "Kick", _oneshot_row(source))
    session.channel_rack.restore_state(
        build_32_field_channel_rack_state(session.live_kit)
    )
    yield session, tmp_path / "track", source
    session.transport.close()


def _oneshot_row(path: Path) -> WorkbenchRow:
    return _class_row(path, sample_class="oneshot")


def _loop_row(path: Path) -> WorkbenchRow:
    return _class_row(path, sample_class="loop")


def _class_row(path: Path, *, sample_class: str) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=path.name,
        relative_path=path.name,
        path=str(path),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=sample_class,
        pred_type=None,
        status="ok",
        details={},
    )


def _enable(session):
    settings = replace(WorkbenchFeatureSettings(), arrangement_mode_enabled=True)
    assert save_workbench_feature_settings(settings, state_dir=session._state_dir)


def _enter(s, root):
    _enable(s)
    result = s.enter_arrangement_from_edit(package_root=root)
    assert result.ok, result.message


def _flat_fields(projection):
    return [field for bar in projection.bars for field in bar.fields]


def _channel_row(projection, channel_id):
    rows = getattr(projection, "channel_rows", ())
    for row in rows:
        if row.channel_id == channel_id:
            return row
    return None


def _triggers_for(state, channel_id):
    return tuple(t for t in state.pattern.triggers if t.channel_id == channel_id)


# --- controller doubles (repo pattern: 952 runtime suite) -----------------------


@dataclass
class _Snapshot:
    total_voice_count: int
    active_voice_count: int
    voice_ids: tuple[int, ...]
    voice_states: tuple[int, ...]


class _FakeEngine:
    """Minimal native engine double: scheduling bookkeeping only."""

    VOICE_DURATION_FRAMES = SAMPLE_RATE

    def __init__(self) -> None:
        self.create_calls: list[VoiceConfig] = []
        self.schedule_calls: list[tuple[int, int]] = []
        self.stop_voice_calls: list[int] = []
        self.remove_voice_calls: list[int] = []
        self._voices: dict[int, int] = {}
        self._next_id = 1
        self.engine_frame = 0

    def create_voice(self, config: VoiceConfig) -> int:
        self.create_calls.append(config)
        voice_id = self._next_id
        self._next_id += 1
        self._voices[voice_id] = SB_VOICE_IDLE
        return voice_id

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None:
        self.schedule_calls.append((int(voice_id), int(engine_frame)))
        if voice_id in self._voices:
            self._voices[voice_id] = SB_VOICE_SCHEDULED

    def stop_voice(self, voice_id: int) -> None:
        self.stop_voice_calls.append(int(voice_id))
        if voice_id in self._voices:
            self._voices[voice_id] = SB_VOICE_IDLE

    def remove_voice(self, voice_id: int) -> None:
        self.remove_voice_calls.append(int(voice_id))
        self._voices.pop(int(voice_id), None)

    def advance_to(self, engine_frame: int) -> None:
        frame = int(engine_frame)
        self.engine_frame = frame
        starts = dict(self.schedule_calls)
        for voice_id, state in list(self._voices.items()):
            if state == SB_VOICE_SCHEDULED:
                self._voices[voice_id] = SB_VOICE_PLAYING
            elif state == SB_VOICE_PLAYING:
                start = starts.get(voice_id)
                if start is not None and frame >= start + self.VOICE_DURATION_FRAMES:
                    self._voices[voice_id] = SB_VOICE_IDLE

    def get_snapshot(self) -> _Snapshot:
        ids = tuple(sorted(self._voices))
        states = [self._voices[vid] for vid in ids]
        pad = SB_MAX_VOICES - len(ids)
        if pad > 0:
            states.extend([SB_VOICE_IDLE] * pad)
        return _Snapshot(
            total_voice_count=len(self._voices),
            active_voice_count=sum(1 for s in states if s == SB_VOICE_PLAYING),
            voice_ids=ids,
            voice_states=tuple(states),
        )

    def snapshot(self) -> _Snapshot:
        return self.get_snapshot()


class _EngineTransport:
    """Transport facade for the rack controller (engine + session clock)."""

    def __init__(
        self,
        engine: _FakeEngine,
        *,
        bpm: float = BPM,
        sync_enabled: bool = False,
    ) -> None:
        self._engine = engine
        self._core = SessionTransport(sample_rate=SAMPLE_RATE, bpm=bpm)
        self._sync_enabled = bool(sync_enabled)

    @property
    def tempo_map(self):
        return self._core.tempo_map

    @property
    def sample_rate(self) -> int:
        return self._core.sample_rate

    @property
    def session_frame(self) -> int:
        return self._core.session_frame

    @property
    def engine_frame(self) -> int:
        return self._core.engine_frame

    def play(self) -> None:
        self._core.play()

    def stop(self) -> None:
        self._core.stop()

    def poll(self) -> None:
        return None

    def get_native_engine(self) -> _FakeEngine:
        return self._engine

    def is_native_available(self) -> bool:
        return True

    def is_sync_enabled(self) -> bool:
        return self._sync_enabled

    def get_current_tempo(self) -> float:
        segment = self._core.tempo_map._segment_for_frame(self._core.session_frame)
        return float(segment.bpm)

    def set_tempo(self, bpm: float) -> int:
        return self._core.set_tempo(bpm)

    def set_sync_enabled(self, enabled: bool) -> None:
        self._sync_enabled = bool(enabled)


def _pcm_provider() -> SequencerPcmProvider:
    def decode_fn(path, *, sample_rate, start_ms=0):
        del path, start_ms
        import numpy as np

        return np.linspace(-0.2, 0.2, PCM_FRAMES, dtype=np.float32), 1

    return SequencerPcmProvider(sample_rate=SAMPLE_RATE, decode_fn=decode_fn)


def _kit_with_kick() -> LiveKitState:
    kit = LiveKitState()
    kit.assign("Kick + Bass", "Kick", _oneshot_row(Path("kick.wav")))
    return kit


def _rack_controller(
    *,
    live_kit: LiveKitState | None = None,
    state: ChannelRackState | None = None,
    observer: list | None = None,
):
    engine = _FakeEngine()
    transport = _EngineTransport(engine)
    notifications: list = observer if observer is not None else []
    controller = ChannelRackController(
        live_kit=live_kit if live_kit is not None else LiveKitState(),
        transport=transport,
        pcm_provider=_pcm_provider(),
        lookahead_frames=4800,
        on_musical_state_changed=lambda: notifications.append(len(notifications)),
    )
    if state is None and live_kit is not None:
        state = build_32_field_channel_rack_state(live_kit)
    if state is not None:
        controller.restore_state(state)
    return controller


# --- gates 1-3: exact #1086 field → quarter-note semantics ------------------------


def test_gate_1_field_0_mutation_lands_on_quarter_note_zero():
    controller = _rack_controller(live_kit=_kit_with_kick())
    before = controller.state
    _toggle_arrangement_field(controller, KICK_ID, 0)
    triggers = controller.state.pattern.triggers
    assert Trigger(channel_id=KICK_ID, position=Fraction(0, 1)) in triggers
    assert controller.state is not before
    assert controller.state.step_count == TOTAL_FIELDS


def test_gate_2_field_1_mutation_is_qn_1_not_legacy_quarter():
    controller = _rack_controller(live_kit=_kit_with_kick())
    _toggle_arrangement_field(controller, KICK_ID, 1)
    triggers = controller.state.pattern.triggers
    assert Trigger(channel_id=KICK_ID, position=Fraction(1, 1)) in triggers
    # Explicitly NOT the legacy 16th-note semantics.
    assert Trigger(channel_id=KICK_ID, position=Fraction(1, 4)) not in triggers
    assert all(t.position != Fraction(1, 4) for t in triggers)


def test_gate_3_field_31_mutation_lands_on_quarter_note_31():
    controller = _rack_controller(live_kit=_kit_with_kick())
    _toggle_arrangement_field(controller, KICK_ID, 31)
    triggers = controller.state.pattern.triggers
    assert Trigger(channel_id=KICK_ID, position=Fraction(31, 1)) in triggers
    assert len(triggers) == 1


# --- gate 4: exactly one mutation, exactly one notification ----------------------


def test_gate_4_one_click_is_exactly_one_mutation_and_one_notification():
    observer: list[int] = []
    controller = _rack_controller(live_kit=_kit_with_kick(), observer=observer)
    before = controller.state
    _toggle_arrangement_field(controller, KICK_ID, 7)
    assert len(observer) == 1
    new_triggers = tuple(
        t for t in controller.state.pattern.triggers if t not in before.pattern.triggers
    )
    assert new_triggers == (Trigger(channel_id=KICK_ID, position=Fraction(7, 1)),)
    assert len(controller.state.pattern.triggers) == 1


# --- gate 5: toggle twice restores the pattern identity --------------------------


def test_gate_5_toggle_twice_removes_trigger_keeps_pattern_identity():
    controller = _rack_controller(live_kit=_kit_with_kick())
    _toggle_arrangement_field(controller, KICK_ID, 2)
    _toggle_arrangement_field(controller, KICK_ID, 9)
    pattern_with_two = controller.state.pattern
    _toggle_arrangement_field(controller, KICK_ID, 9)
    triggers = controller.state.pattern.triggers
    assert Trigger(channel_id=KICK_ID, position=Fraction(9, 1)) not in triggers
    assert triggers == (Trigger(channel_id=KICK_ID, position=Fraction(2, 1)),)
    assert controller.state.pattern.pattern_id == pattern_with_two.pattern_id
    # Removing the last field returns the exact empty one-cycle truth.
    _toggle_arrangement_field(controller, KICK_ID, 2)
    assert controller.state.pattern.triggers == ()
    assert controller.state.pattern.pattern_id == pattern_with_two.pattern_id


# --- gates 6-8: fail-closed inputs -------------------------------------------------


@pytest.mark.parametrize("field_index", [-1, 32])
def test_gates_6_7_invalid_field_indices_fail_closed_without_mutation(field_index):
    controller = _rack_controller(live_kit=_kit_with_kick())
    _toggle_arrangement_field(controller, KICK_ID, 4)
    before = controller.state
    with pytest.raises(ValueError):
        _toggle_arrangement_field(controller, KICK_ID, field_index)
    assert controller.state is before
    assert controller.state.pattern.triggers == (
        Trigger(channel_id=KICK_ID, position=Fraction(4, 1)),
    )


def test_gate_8_unknown_channel_fails_closed_without_mutation():
    controller = _rack_controller(live_kit=_kit_with_kick())
    before = controller.state
    with pytest.raises(ValueError):
        _toggle_arrangement_field(controller, "ch_missing", 0)
    assert controller.state is before
    assert controller.state.pattern.triggers == ()


# --- gate 9: legacy rack fails closed, never silently migrated ---------------------


def test_gate_9_legacy_rack_fails_closed_without_silent_migration():
    kit = _kit_with_kick()
    controller = _rack_controller(live_kit=kit)
    controller.restore_state(build_channel_rack_state(kit))
    before = controller.state
    assert before.step_count == 16
    assert before.pattern.length_quarter_notes == Fraction(4, 1)
    with pytest.raises(ValueError):
        _toggle_arrangement_field(controller, KICK_ID, 0)
    assert controller.state is before
    assert controller.state.step_count == 16
    assert controller.state.pattern == before.pattern


# --- gate 10: one-shot row projects 32 editable fields ----------------------------


def test_gate_10_one_shot_row_projects_32_editable_fields(draft):
    s, _root, _source = draft
    projection = _project(s)
    row = _channel_row(projection, KICK_ID)
    assert row is not None
    assert row.step_grid_enabled is True
    assert row.row_kind == "step"
    assert len(row.fields) == 32
    assert [f.index for f in row.fields] == list(range(32))
    assert all(not f.active for f in row.fields)
    assert len(row.bars) == 8
    assert all(len(bar.fields) == 4 for bar in row.bars)
    # Editability reaches the last field through the intent seam too.
    result = _request_toggle(s, KICK_ID, 31)
    assert result.ok
    assert result.outcome == "mutated"
    assert Trigger(channel_id=KICK_ID, position=Fraction(31, 1)) in (
        s.channel_rack.state.pattern.triggers
    )


# --- gate 11: loop row has no editable matrix, QML intent mutates nothing ----------


def test_gate_11_loop_row_is_identity_only_and_intent_mutates_nothing(tmp_path):
    s = ws.compose_workbench_session(state_dir=tmp_path / "state")
    try:
        kick = tmp_path / "kick.wav"
        pad = tmp_path / "pad.wav"
        write_sine_wav(kick, duration_sec=0.05, frequency_hz=60)
        write_sine_wav(pad, duration_sec=0.2, frequency_hz=110)
        s.live_kit.assign("Kick + Bass", "Kick", _oneshot_row(kick))
        s.live_kit.assign("Melodic", "Pad", _loop_row(pad))
        s.channel_rack.restore_state(
            build_32_field_channel_rack_state(s.live_kit)
        )
        projection = _project(s)
        row = _channel_row(projection, PAD_ID)
        assert row is not None, "loop channels stay visible as identity rows"
        assert row.step_grid_enabled is False
        assert row.row_kind == "loop_identity"
        before = s.channel_rack.state
        for field_index in (0, 5, 31):
            result = _request_toggle(s, PAD_ID, field_index)
            assert not result.ok
            assert result.outcome == "row_not_editable"
        assert s.channel_rack.state is before
        assert _triggers_for(s.channel_rack.state, PAD_ID) == ()
    finally:
        s.transport.close()


# --- gate 12: ambiguous row has no editable matrix, QML intent mutates nothing ----


def test_gate_12_ambiguous_row_is_identity_only_and_intent_mutates_nothing(tmp_path):
    s = ws.compose_workbench_session(state_dir=tmp_path / "state")
    try:
        kick = tmp_path / "kick.wav"
        user = tmp_path / "user_ambiguous.wav"
        write_sine_wav(kick, duration_sec=0.05, frequency_hz=60)
        write_sine_wav(user, duration_sec=0.1, frequency_hz=220)
        s.live_kit.assign("Kick + Bass", "Kick", _oneshot_row(kick))
        rack = add_user_channel_32_field(
            build_32_field_channel_rack_state(s.live_kit),
            sample_path=str(user),
        )
        s.channel_rack.restore_state(rack)
        projection = _project(s)
        row = _channel_row(projection, "ch_user_1")
        assert row is not None, "ambiguous user channels stay visible as identity rows"
        assert row.step_grid_enabled is False
        assert row.row_kind == "loop_identity"
        before = s.channel_rack.state
        result = _request_toggle(s, "ch_user_1", 0)
        assert not result.ok
        assert result.outcome == "row_not_editable"
        assert s.channel_rack.state is before
        assert _triggers_for(s.channel_rack.state, "ch_user_1") == ()
    finally:
        s.transport.close()


# --- gates 13-14: upper stage quiet/active transitions ----------------------------


def test_gates_13_14_upper_stage_transitions_follow_the_canonical_fields(draft):
    s, root, _source = draft
    _enter(s, root)
    projection = _project(s)
    assert projection.any_active_step is False
    _toggle_arrangement_field(s.channel_rack, KICK_ID, 0)
    projection = _project(s)
    assert projection.any_active_step is True
    assert [f.index for f in _flat_fields(projection) if f.active] == [0]
    # Remove the last active field: the upper stage becomes quiet again.
    _toggle_arrangement_field(s.channel_rack, KICK_ID, 0)
    projection = _project(s)
    assert projection.any_active_step is False
    assert [f.index for f in _flat_fields(projection) if f.active] == []


# --- gate 15: persistence through the existing autosave owner ---------------------


def test_gate_15_mutation_persists_through_existing_active_track_owner(draft):
    s, root, _source = draft
    _enter(s, root)
    assert s.active_track_package_root is not None
    _toggle_arrangement_field(s.channel_rack, KICK_ID, 3)
    # The single existing musical-state autosave owner persisted the
    # mutation: no second save seam, package not left dirty.
    assert s.track_package_dirty is False
    opened = tp.open_track_package(root)
    assert opened.ok, opened.message
    snapshot = snapshot_from_track_package_musical(
        opened.manifest.musical, root
    )
    rack = snapshot.channel_rack
    assert rack.step_count == TOTAL_FIELDS
    assert Trigger(channel_id=KICK_ID, position=Fraction(3, 1)) in (
        rack.pattern.triggers
    )
    # One mutation ⇒ exactly one persisted trigger.
    assert len(rack.pattern.triggers) == 1
    assert rack.pattern == s.channel_rack.state.pattern


# --- gate 16: return to Edit + re-entry preserves mutation and owners -------------


def test_gate_16_return_and_re_entry_preserve_mutation_identity_and_owner(draft):
    s, root, _source = draft
    _enter(s, root)
    _toggle_arrangement_field(s.channel_rack, KICK_ID, 21)
    pattern_after_mutation = s.channel_rack.state.pattern
    track_id = s.active_track_id
    rack_owner = s.channel_rack

    s.return_to_edit()
    assert s.projection_mode == "EDIT"
    reentry = s.enter_arrangement_from_edit()
    assert reentry.ok, reentry.message
    assert s.projection_mode == "ARRANGEMENT"
    assert s.active_track_id == track_id
    assert s.channel_rack is rack_owner
    # Media rebase may rebuild the state object; the Pattern truth carries
    # over byte-identically (frozen #1078 contract: equality, not identity).
    assert s.channel_rack.state.pattern == pattern_after_mutation
    assert s.channel_rack.state.pattern.pattern_id == (
        pattern_after_mutation.pattern_id
    )
    assert Trigger(channel_id=KICK_ID, position=Fraction(21, 1)) in (
        s.channel_rack.state.pattern.triggers
    )
    projection = _project(s)
    assert [f.index for f in _flat_fields(projection) if f.active] == [21]
    row = _channel_row(projection, KICK_ID)
    assert [f.index for f in row.fields if f.active] == [21]


# --- gate 17: pure projection refresh mutates and serializes nothing --------------


def test_gate_17_pure_projection_refresh_neither_mutates_nor_serializes(draft):
    s, root, _source = draft
    _enter(s, root)
    manifest_path = root / tp.TRACK_PACKAGE_FILENAME
    pointer_path = active_track_pointer_path(state_dir=s._state_dir)
    manifest_before = manifest_path.read_bytes()
    pointer_before = pointer_path.read_bytes()
    state_before = s.channel_rack.state
    first = _project(s)
    second = _project(s)
    assert first == second
    assert s.channel_rack.state is state_before
    assert manifest_path.read_bytes() == manifest_before
    assert pointer_path.read_bytes() == pointer_before


# --- gate 19: legacy toggle_step stays the protected 16th-note seam ---------------


def test_gate_19_legacy_toggle_step_semantics_remain_unchanged():
    kit = _kit_with_kick()
    controller = _rack_controller(live_kit=kit)
    controller.restore_state(build_channel_rack_state(kit))
    seeded = _triggers_for(controller.state, KICK_ID)
    assert len(seeded) == 16
    assert Trigger(channel_id=KICK_ID, position=Fraction(5, 4)) in seeded
    controller.toggle_step(KICK_ID, 5)
    assert Trigger(channel_id=KICK_ID, position=Fraction(5, 4)) not in (
        _triggers_for(controller.state, KICK_ID)
    )
    controller.toggle_step(KICK_ID, 5)
    assert Trigger(channel_id=KICK_ID, position=Fraction(5, 4)) in (
        _triggers_for(controller.state, KICK_ID)
    )
    assert controller.state.step_count == 16


# --- gate 20: pending deferred mutation fails closed, never step_index / 4 --------


def test_gate_20_pending_deferred_mutation_fails_closed_never_step_over_4():
    controller = _rack_controller(live_kit=_kit_with_kick())
    _toggle_arrangement_field(controller, KICK_ID, 0)
    controller.play()
    assert controller.is_playing
    # Queue a deferred user-channel mutation (the historical stream).
    controller.add_user_channel()
    assert controller._pending_user_mutation is not None
    before = controller.state
    with pytest.raises(ValueError):
        _toggle_arrangement_field(controller, KICK_ID, 3)
    assert controller.state is before
    # No mutation, and never the legacy quarter-note misinterpretation.
    assert Trigger(channel_id=KICK_ID, position=Fraction(3, 1)) not in (
        controller.state.pattern.triggers
    )
    assert Trigger(channel_id=KICK_ID, position=Fraction(3, 4)) not in (
        controller.state.pattern.triggers
    )
    # After the deferred stream drains, the exact field semantics work again.
    controller.stop()
    _toggle_arrangement_field(controller, KICK_ID, 3)
    assert Trigger(channel_id=KICK_ID, position=Fraction(3, 1)) in (
        controller.state.pattern.triggers
    )


# --- QML string contracts (no Qt required) ----------------------------------------


def _arrangement_shell_region() -> str:
    """Gated Loader through the last stage chrome marker."""
    start = QML_SOURCE.index('objectName: "arrangementStageLoader"')
    anchor = QML_SOURCE.index('objectName: "arrangementTrackIdentity"', start)
    return QML_SOURCE[
        start : anchor + len('objectName: "arrangementTrackIdentity"')
    ]


def test_qml_channel_rows_are_python_owned_intent_only():
    region = _arrangement_shell_region()
    assert 'objectName: "arrangementChannelRow"' in region
    assert 'objectName: "arrangementChannelField"' in region
    assert "model: window.arrangement.channelRows" in region
    # One click sends ONLY channel identity + projected field index to the
    # Python interaction seam — no quarter-note math, no local truth flip.
    assert (
        "onClicked: window.arrangement.toggleArrangementField("
        "arrangementChannelRow.channelId, arrangementChannelField.fieldIndex)"
    ) in region
    assert "localActive" not in region
    assert "Fraction(" not in region
    assert "/ 4" not in region
    # C2b: "* 4" appears in height calculations (* 48), not legacy quarter-note mapping.
    # Check for legacy "* 4" as standalone operator, not part of "* 48".
    import re
    assert not re.search(r'\* 4(?!\d)', region)
    # No legacy rack seam, no audition, no persistence bypass in the stage.
    for forbidden in (
        "toggleStep",
        "previewRow",
        "stopPreview",
        "previewHarmonyRow",
        "sessionPersistence",
        "saveWorkspacePreset",
    ):
        assert forbidden not in region
    # The aggregate Slice A row keeps its read-only geometry.
    assert "model: window.arrangement.bars" in region
    assert 'objectName: "arrangementBar"' in region
    assert 'objectName: "arrangementField"' in region


def test_qml_editability_is_bound_to_python_authority_rows():
    region = _arrangement_shell_region()
    # Only rows the Python projection marked editable carry hit targets.
    assert "enabled: arrangementChannelRow.stepGridEnabled" in region
    # The stage input blocker stays: no pointer fall-through beneath the
    # stage, and it carries no command of its own.
    # Explicit Owner-approved freeze reconciliation for #1080 C2a/C2b:
    # pin all authorized handlers, preserving the field/input contract.
    # C2b adds: expand/collapse, track block handlers.
    assert region.count("onClicked: window.arrangement.toggleArrangementField(arrangementChannelRow.channelId, arrangementChannelField.fieldIndex)") == 1
    assert region.count("onClicked: window.arrangement.toggleArrangementGroupBlock(arrangementGroupRow.groupId, arrangementGroupBlock.blockIndex)") == 1
    # C2b authorized handlers
    assert region.count("onClicked: window.arrangement.toggleArrangementGroupExpanded(arrangementGroupRow.groupId)") == 1
    assert region.count("onClicked: window.arrangement.toggleArrangementTrackBlock(arrangementTrackRow.channelId, arrangementTrackBlock.blockIndex)") == 1
    import inspect
    from src.workbench_qml import _qml_arrangement_bridge

    assert "arrangement_seam.request_arrangement_group_toggle(" in inspect.getsource(
        _qml_arrangement_bridge
    )
    assert "MouseArea {" in region
    assert (
        "acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton"
        in region
    )


def test_projection_module_exports_slice_b_seam():
    module = _projection_module_or_fail()
    _require(module, "ArrangementQmlChannelRow")
    _require(module, "request_arrangement_field_toggle")
    _require(module, "ArrangementFieldToggleResult")
    controller_module = _controller_module_or_fail()
    _require(controller_module, "ChannelRackController")
    assert hasattr(controller_module.ChannelRackController, "toggle_arrangement_field")


def test_intent_seam_fail_closed_vocabulary(draft):
    s, _root, _source = draft
    # Unknown channel through the QML intent seam.
    result = _request_toggle(s, "ch_missing", 0)
    assert not result.ok
    assert result.outcome == "unknown_channel"
    # Invalid fields through the QML intent seam.
    for field_index in (-1, 32):
        result = _request_toggle(s, KICK_ID, field_index)
        assert not result.ok
        assert result.outcome == "invalid_field_index"
    assert s.channel_rack.state.pattern.triggers == ()
    # Legacy rack through the QML intent seam: fail closed, no migration.
    s.channel_rack.restore_state(build_channel_rack_state(s.live_kit))
    result = _request_toggle(s, KICK_ID, 0)
    assert not result.ok
    assert result.outcome == "legacy_rack_fail_closed"
    assert s.channel_rack.state.step_count == 16


# --- runtime gates (PySide6) ------------------------------------------------------


def _build_production_window():
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.set_library_revealed(True)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=True,
    )
    app, engine, window = _qml_engine(view_model)
    window.show()
    _settle_qml_frame(app)
    return app, engine, window, _settle_qml_frame


def _visual_items_named(root, name):
    """Collect items by objectName via the visual tree (repo pattern)."""
    found = []
    to_visit = [root]
    while to_visit:
        current = to_visit.pop()
        if current.objectName() == name:
            found.append(current)
        to_visit.extend(current.childItems())
    return found


def _click_item(window, item, settle, app) -> None:
    from PySide6.QtCore import QPointF

    center = item.mapToItem(
        window.contentItem(), QPointF(item.width() / 2, item.height() / 2)
    )
    _click_point(window, center, settle, app)


def _click_point(window, point, settle, app) -> None:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QMouseEvent

    for action in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        event = QMouseEvent(
            action,
            point,
            window.mapToGlobal(point.toPoint()),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        app.sendEvent(window, event)
        settle(app)


def _cells_by_field_index(stage, row_channel_id=None):
    """Map projected field index → cell item, optionally scoped to one row."""
    mapping: dict[int, object] = {}
    for cell in _visual_items_named(stage, "arrangementChannelField"):
        if row_channel_id is not None and _owning_row_id(cell) != row_channel_id:
            continue
        mapping[int(cell.property("fieldIndex"))] = cell
    return mapping


def _click_cell(window, stage, field_index, settle, app) -> None:
    """Click the *current* cell for one field index.

    Every successful mutation re-projects and rebuilds the row Repeater
    delegates, so the cell item must be re-resolved for each click — never
    cached across mutations.
    """
    cells = _cells_by_field_index(stage)
    assert field_index in cells, f"field {field_index} has no rendered cell"
    _click_item(window, cells[field_index], settle, app)


def _owning_row_id(item):
    """Channel id of the arrangementChannelRow owning a delegate item."""
    current = item
    while current is not None:
        if current.objectName() == "arrangementChannelRow":
            return str(current.property("channelId"))
        current = current.parentItem()
    return ""


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_gates_18_runtime_field_clicks_projection_persistence_and_no_fall_through(
    tmp_path, monkeypatch
):
    from PySide6.QtQuick import QQuickItem

    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    app, engine, window, settle = _build_production_window()
    session = engine._screen1_session
    try:
        bridge = engine.rootContext().contextProperty("arrangementModel")
        assert bridge is not None
        source = tmp_path / "kick.wav"
        write_sine_wav(source, duration_sec=0.05, frequency_hz=60)
        session.live_kit.assign("Kick + Bass", "Kick", _oneshot_row(source))
        session.channel_rack.restore_state(
            build_32_field_channel_rack_state(session.live_kit)
        )
        _enable(session)
        engine._screen1_interaction_adapter.load_feature_settings()
        bridge.refresh()
        assert session.enter_arrangement_from_edit(
            package_root=tmp_path / "track"
        ).ok
        bridge.refresh()

        stage = window.findChild(QQuickItem, "arrangementStage")
        assert stage is not None and stage.isVisible()
        rows = _visual_items_named(stage, "arrangementChannelRow")
        assert len(rows) == 1, "exactly the occupied channels project as rows"
        cells = _cells_by_field_index(stage)
        assert len(cells) == 32
        assert sorted(cells) == list(range(32))
        assert bridge.anyActiveStep is False
        assert not session.channel_rack.is_playing
        assert not session.transport.playing

        vm = engine._screen1_interaction_adapter.view_model
        selected_before = vm.selected_browser_index

        # Click field 0: exactly one Python-owned mutation, immediate
        # reprojection, upper stage active — and no browser audition behind
        # the Arrangement stage.
        _click_cell(window, stage, 0, settle, app)
        settle(app)
        assert bridge.lastFieldToggleOutcome == "mutated"
        assert bridge.anyActiveStep is True
        assert (
            Trigger(channel_id=KICK_ID, position=Fraction(0, 1))
            in session.channel_rack.state.pattern.triggers
        )
        assert len(session.channel_rack.state.pattern.triggers) == 1
        assert vm.selected_browser_index == selected_before
        assert engine._screen1_interaction_adapter.preview_active is False
        assert not session.channel_rack.is_playing
        assert not session.transport.playing

        # Click field 1 and field 31: canonical positions, not legacy steps.
        _click_cell(window, stage, 1, settle, app)
        settle(app)
        _click_cell(window, stage, 31, settle, app)
        settle(app)
        rack = session.channel_rack.state
        assert {
            t.position for t in rack.pattern.triggers if t.channel_id == KICK_ID
        } == {Fraction(0, 1), Fraction(1, 1), Fraction(31, 1)}

        # Remove the last active field (31): upper stage stays active while
        # fields remain, then all three removals make it quiet again.
        _click_cell(window, stage, 31, settle, app)
        settle(app)
        assert bridge.anyActiveStep is True
        _click_cell(window, stage, 1, settle, app)
        _click_cell(window, stage, 0, settle, app)
        settle(app)
        assert bridge.anyActiveStep is False
        assert session.channel_rack.state.pattern.triggers == ()
        assert vm.selected_browser_index == selected_before

        # Re-set field 12, return to Browser (Edit destination), re-enter via
        # the product route: state and owners survive the round trip.
        _click_cell(window, stage, 12, settle, app)
        settle(app)
        assert bridge.anyActiveStep is True
        track_id = session.active_track_id

        browser_nav = window.findChild(QQuickItem, "programNavEdit")
        assert browser_nav is not None
        _click_item(window, browser_nav, settle, app)
        settle(app)
        assert bridge.projectionMode == "EDIT"
        assert window.findChild(QQuickItem, "arrangementStage") is None

        nav = window.findChild(QQuickItem, "programNavArrangement")
        assert nav is not None and nav.property("enabled") is True
        _click_item(window, nav, settle, app)
        settle(app)
        assert bridge.projectionMode == "ARRANGEMENT"
        assert bridge.activeTrackId == track_id
        # The persisted field survived the return + re-entry round trip.
        assert (
            Trigger(channel_id=KICK_ID, position=Fraction(12, 1))
            in session.channel_rack.state.pattern.triggers
        )
        stage = window.findChild(QQuickItem, "arrangementStage")
        cells = _cells_by_field_index(stage)
        assert sorted(cells) == list(range(32))
        _click_cell(window, stage, 12, settle, app)
        settle(app)
        assert session.channel_rack.state.pattern.triggers == ()
        assert bridge.anyActiveStep is False

        # Play/Stop regression smoke: the field surface leaves rack
        # playback parked and the stop seam stays safe.
        assert not session.channel_rack.is_playing
        session.channel_rack.stop()
        assert not session.channel_rack.is_playing
    finally:
        window.close()
        app.processEvents()
        if session is not None:
            session.transport.close()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_non_editable_identity_rows_carry_no_hit_targets(tmp_path, monkeypatch):
    from PySide6.QtQuick import QQuickItem

    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    app, engine, window, settle = _build_production_window()
    session = engine._screen1_session
    try:
        bridge = engine.rootContext().contextProperty("arrangementModel")
        kick = tmp_path / "kick.wav"
        pad = tmp_path / "pad.wav"
        write_sine_wav(kick, duration_sec=0.05, frequency_hz=60)
        write_sine_wav(pad, duration_sec=0.2, frequency_hz=110)
        session.live_kit.assign("Kick + Bass", "Kick", _oneshot_row(kick))
        session.live_kit.assign("Melodic", "Pad", _loop_row(pad))
        session.channel_rack.restore_state(
            build_32_field_channel_rack_state(session.live_kit)
        )
        _enable(session)
        engine._screen1_interaction_adapter.load_feature_settings()
        bridge.refresh()
        assert session.enter_arrangement_from_edit(
            package_root=tmp_path / "track"
        ).ok
        bridge.refresh()
        stage = window.findChild(QQuickItem, "arrangementStage")
        rows = _visual_items_named(stage, "arrangementChannelRow")
        assert len(rows) == 2
        row_by_id = {str(row.property("channelId")): row for row in rows}
        assert row_by_id[KICK_ID].property("stepGridEnabled") is True
        assert row_by_id[PAD_ID].property("stepGridEnabled") is False
        pad_cells = _cells_by_field_index(stage, row_channel_id=PAD_ID)
        assert len(pad_cells) == 32
        # A disabled hit target never sends an intent at all: clicking a Pad
        # cell mutates nothing, sends nothing, and does not fall through
        # into the Edit workspace beneath the stage.
        vm = engine._screen1_interaction_adapter.view_model
        selected_before = vm.selected_browser_index
        state_before = session.channel_rack.state
        _click_item(window, pad_cells[0], settle, app)
        settle(app)
        assert bridge.lastFieldToggleOutcome == ""
        assert session.channel_rack.state is state_before
        assert vm.selected_browser_index == selected_before
        assert engine._screen1_interaction_adapter.preview_active is False
        assert bridge.anyActiveStep is False
    finally:
        window.close()
        app.processEvents()
        if session is not None:
            session.transport.close()
