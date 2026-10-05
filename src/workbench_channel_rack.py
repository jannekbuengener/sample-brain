"""Screen-2 Channel Rack controller — Python musical SoT + QML command surface.

Owns one :class:`ChannelRackState` per Workbench session, projects it for QML,
and routes Play/Stop through ``play_channel_rack_once`` / ``PatternPassPlayer``.
Screen-2 Play loops by orchestrating successive finite one-pass players until
Stop (#810). Does not own Live Kit, TempoMap, or the native audio engine; those
stay on the shared session transport. QML never holds pattern or loop shadow
truth.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Mapping

from .channel_rack import (
    ChannelRackPlayHandle,
    ChannelRackState,
    add_user_channel,
    assign_user_channel_sample,
    build_channel_rack_state,
    play_channel_rack_once,
    reconcile_live_kit_sample_assignments,
    toggle_step,
    warm_channel_rack_pcm,
)
from .gesture_rack_integration import GestureRackIntegrationPlan
from .pattern_core import Trigger
from .sequencer_pcm import SequencerPcmProvider
from .session_grid import TempoMap
from .workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState

DEFAULT_LOOKAHEAD_FRAMES = 4800
USER_GROUP_NAME = "User"
SCREEN1 = "screen1"
SCREEN2 = "screen2"

# Single Workspace bottom Rack geometry baselines (#908).
BOTTOM_RACK_HEIGHT_RATIO = 0.24
BOTTOM_RACK_EMPTY_STRIP_PX = 32
ROW_KIND_STEP = "step"
ROW_KIND_LOOP_IDENTITY = "loop_identity"
_POINT_TRIGGER_SAFE_CLASSES = frozenset({"one_shot", "oneshot"})
_LOOP_CLASSES = frozenset({"loop"})


class StaleGestureRackIntegrationPlanError(ValueError):
    """Pre-mutation rejection of a stale ``GestureRackIntegrationPlan`` (#921).

    Raised by :meth:`ChannelRackController.apply_gesture_integration_plan`
    **only** when the live controller state no longer matches the plan's
    ``expected_base_state``. That check runs before ``stop()``, before the
    state assignment, and before the musical-state observer, so catching this
    type is always safe and never implies the Rack was already mutated.

    Callers must not infer this from a message match. Exceptions raised *after*
    the state assignment — notably from the observer callback — are ordinary
    exceptions and may surface the same words; treating those as stale would
    report a mutation that already happened as a zero-mutation rejection.

    Subclasses :class:`ValueError` for backward compatibility with existing
    ``pytest.raises(ValueError)`` call sites.
    """


def _normalize_sample_class(value: object | None) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _row_kind_for_assignment(assignment: Any) -> str:
    """Classify occupied Live Kit assignment for bottom Rack projection (#908/#920).

    Point-trigger-safe (one_shot/oneshot) → step grid.
    Loop-class or missing/ambiguous sample_class → identity only (no step grid).
    """
    sample_class = _normalize_sample_class(
        getattr(assignment, "sample_class", None) if assignment is not None else None
    )
    if sample_class in _POINT_TRIGGER_SAFE_CLASSES:
        return ROW_KIND_STEP
    return ROW_KIND_LOOP_IDENTITY


def pattern_pass_start_frames(
    tempo_map: TempoMap,
    *,
    anchor_quarter: Fraction,
    anchor_engine_frame: int,
    pass_index: int,
    length_quarter_notes: Fraction,
) -> tuple[Fraction, int]:
    """Map loop pass index → (musical start quarter, engine-frame anchor).

    Musical authority is ``TempoMap`` quarter-note positions. Engine anchors are
    derived as a session-frame delta from the play-time anchor — never by adding
    a constant pattern frame duration (tempo changes between passes must apply).
    """
    if pass_index < 0:
        raise ValueError("pass_index must be >= 0")
    start_quarter = anchor_quarter + (pass_index * length_quarter_notes)
    start_session = tempo_map.quarter_note_to_frame(start_quarter)
    anchor_session = tempo_map.quarter_note_to_frame(anchor_quarter)
    start_engine = int(anchor_engine_frame) + (start_session - anchor_session)
    return start_quarter, start_engine


def _read_transport_session_frame(transport: Any) -> int:
    getter = getattr(transport, "get_session_frame", None)
    if callable(getter):
        return int(getter() or 0)
    return int(getattr(transport, "session_frame", 0) or 0)


def _read_transport_engine_frame(transport: Any) -> int:
    getter = getattr(transport, "get_engine_frame", None)
    if callable(getter):
        return int(getter() or 0)
    return int(getattr(transport, "engine_frame", 0) or 0)


class _SequencerEngineAdapter:
    """Adapt NativeAudioEngine (``snapshot``) to PatternPassPlayer (``get_snapshot``)."""

    __slots__ = ("_engine",)

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    def create_voice(self, config: Any) -> int:
        return self._engine.create_voice(config)

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None:
        self._engine.schedule_voice_start(voice_id, engine_frame)

    def stop_voice(self, voice_id: int) -> None:
        self._engine.stop_voice(voice_id)

    def remove_voice(self, voice_id: int) -> None:
        self._engine.remove_voice(voice_id)

    def get_snapshot(self) -> Any:
        getter = getattr(self._engine, "get_snapshot", None)
        if callable(getter):
            return getter()
        return self._engine.snapshot()


def _sample_label(sample_path: str | None) -> str:
    if sample_path is None or sample_path == "":
        return ""
    return Path(sample_path).name


def _step_active(state: ChannelRackState, channel_id: str, step_index: int) -> bool:
    position = Fraction(step_index, 4)
    return Trigger(channel_id=channel_id, position=position) in state.pattern.triggers


def project_channel_rack_for_qml(state: ChannelRackState) -> dict[str, Any]:
    """Pure projection of rack state for the legacy Screen-2 QML surface."""

    steps_by_channel: dict[str, list[bool]] = {
        channel.channel_id: [
            _step_active(state, channel.channel_id, index)
            for index in range(state.step_count)
        ]
        for channel in state.channels
    }

    groups: list[dict[str, Any]] = []
    for group_name, slots in LIVE_KIT_SLOT_MAPPING:
        rows: list[dict[str, Any]] = []
        for channel in state.channels:
            if channel.live_kit_group != group_name:
                continue
            rows.append(
                {
                    "channel_id": channel.channel_id,
                    "display_name": channel.live_kit_slot or channel.channel_id,
                    "sample_path": channel.sample_path or "",
                    "sample_label": _sample_label(channel.sample_path),
                    "live_kit_group": channel.live_kit_group,
                    "live_kit_slot": channel.live_kit_slot,
                    "is_user_channel": False,
                    "steps": steps_by_channel[channel.channel_id],
                    "row_kind": ROW_KIND_STEP,
                    "step_grid_enabled": True,
                }
            )
        groups.append({"name": group_name, "rows": rows})

    user_rows = [
        {
            "channel_id": channel.channel_id,
            "display_name": channel.channel_id.replace("ch_user_", "User "),
            "sample_path": channel.sample_path or "",
            "sample_label": _sample_label(channel.sample_path),
            "live_kit_group": None,
            "live_kit_slot": None,
            "is_user_channel": True,
            "steps": steps_by_channel[channel.channel_id],
            "row_kind": ROW_KIND_STEP,
            "step_grid_enabled": True,
        }
        for channel in state.channels
        if channel.live_kit_group is None and channel.live_kit_slot is None
    ]
    if user_rows:
        groups.append({"name": USER_GROUP_NAME, "rows": user_rows})

    markers = []
    for index in range(state.step_count):
        markers.append(
            {
                "index": index,
                "beat_boundary": index % 4 == 0,
                "bar_boundary": index % 16 == 0,
            }
        )

    return {
        "pattern_id": state.pattern.pattern_id,
        "step_count": state.step_count,
        "groups": groups,
        "step_markers": markers,
        "product_surface": "legacy_screen2",
        "bottom_rack_materialized": True,
        "bottom_rack_height_ratio": BOTTOM_RACK_HEIGHT_RATIO,
        "bottom_rack_height_px": 0,
    }


def project_bottom_rack_for_qml(
    state: ChannelRackState,
    live_kit: LiveKitState,
) -> dict[str, Any]:
    """Single Workspace bottom Rack projection (#908).

    Occupied Live Kit / user channels only. Empty groups omitted. Point-trigger-
    safe one-shot rows expose the step grid; loop-class / ambiguous rows expose
    identity without a misleading DEFAULT_ON step grid (#920 deferred).
    """

    steps_by_channel: dict[str, list[bool]] = {
        channel.channel_id: [
            _step_active(state, channel.channel_id, index)
            for index in range(state.step_count)
        ]
        for channel in state.channels
    }

    groups: list[dict[str, Any]] = []
    for group_name, _slots in LIVE_KIT_SLOT_MAPPING:
        rows: list[dict[str, Any]] = []
        for channel in state.channels:
            if channel.live_kit_group != group_name:
                continue
            if not channel.sample_path:
                continue
            assignment = None
            if channel.live_kit_slot:
                assignment = live_kit.assignment_for(group_name, channel.live_kit_slot)
            row_kind = _row_kind_for_assignment(assignment)
            step_enabled = row_kind == ROW_KIND_STEP
            rows.append(
                {
                    "channel_id": channel.channel_id,
                    "display_name": channel.live_kit_slot or channel.channel_id,
                    "sample_path": channel.sample_path or "",
                    "sample_label": _sample_label(channel.sample_path),
                    "live_kit_group": channel.live_kit_group,
                    "live_kit_slot": channel.live_kit_slot,
                    "is_user_channel": False,
                    "steps": steps_by_channel[channel.channel_id] if step_enabled else [],
                    "row_kind": row_kind,
                    "step_grid_enabled": step_enabled,
                }
            )
        if rows:
            groups.append({"name": group_name, "rows": rows})

    user_rows: list[dict[str, Any]] = []
    for channel in state.channels:
        if channel.live_kit_group is not None or channel.live_kit_slot is not None:
            continue
        if not channel.sample_path:
            continue
        # User channels without Live Kit sample_class fail closed (identity only)
        # unless callers later attach classification through a dedicated seam.
        user_rows.append(
            {
                "channel_id": channel.channel_id,
                "display_name": channel.channel_id.replace("ch_user_", "User "),
                "sample_path": channel.sample_path or "",
                "sample_label": _sample_label(channel.sample_path),
                "live_kit_group": None,
                "live_kit_slot": None,
                "is_user_channel": True,
                "steps": [],
                "row_kind": ROW_KIND_LOOP_IDENTITY,
                "step_grid_enabled": False,
            }
        )
    if user_rows:
        groups.append({"name": USER_GROUP_NAME, "rows": user_rows})

    materialized = any(group["rows"] for group in groups)
    markers = []
    if materialized:
        for index in range(state.step_count):
            markers.append(
                {
                    "index": index,
                    "beat_boundary": index % 4 == 0,
                    "bar_boundary": index % 16 == 0,
                }
            )

    return {
        "pattern_id": state.pattern.pattern_id,
        "step_count": state.step_count,
        "groups": groups,
        "step_markers": markers,
        "product_surface": "bottom_rack",
        "bottom_rack_materialized": materialized,
        "bottom_rack_height_ratio": BOTTOM_RACK_HEIGHT_RATIO if materialized else 0.0,
        "bottom_rack_height_px": 0 if materialized else BOTTOM_RACK_EMPTY_STRIP_PX,
    }


def _empty_bottom_projection() -> dict[str, Any]:
    return {
        "pattern_id": "",
        "step_count": 16,
        "groups": [],
        "step_markers": [],
        "product_surface": "bottom_rack",
        "bottom_rack_materialized": False,
        "bottom_rack_height_ratio": 0.0,
        "bottom_rack_height_px": BOTTOM_RACK_EMPTY_STRIP_PX,
    }


def _sync_live_kit_sample_paths(
    state: ChannelRackState,
    live_kit: LiveKitState,
) -> ChannelRackState:
    """Refresh Live Kit seed paths and heal DEFAULT_ON for late assignments.

    Delegates to :func:`reconcile_live_kit_sample_assignments` so empty→assigned
    seeds DEFAULT_ON, replacements preserve user triggers, and clears strip
    orphan/trigger state fail-closed (#806).
    """

    return reconcile_live_kit_sample_assignments(state, live_kit)


class ChannelRackController:
    """Session-owned Screen-2 rack: project + commands + looping one-pass player.

    Each Play starts a finite ``PatternPassPlayer``. When that pass completes,
    the controller plans the next finite pass from the live ``ChannelRackState``
    at the next musical pattern boundary until Stop / leave Screen 2.
    """

    def __init__(
        self,
        *,
        live_kit: LiveKitState,
        transport: Any,
        pcm_provider: SequencerPcmProvider | None = None,
        lookahead_frames: int = DEFAULT_LOOKAHEAD_FRAMES,
        allocate_voice_id: Callable[[], int] | None = None,
        on_claim_audio_focus: Callable[[], None] | None = None,
        on_release_to_screen1: Callable[[], None] | None = None,
        on_musical_state_changed: Callable[[], None] | None = None,
    ) -> None:
        self._live_kit = live_kit
        self._transport = transport
        sample_rate = int(getattr(transport, "sample_rate", 0) or 0)
        if sample_rate <= 0:
            sample_rate = int(transport.tempo_map.sample_rate)
        self._pcm_provider = pcm_provider or SequencerPcmProvider(sample_rate=sample_rate)
        self._lookahead_frames = int(lookahead_frames)
        self._allocate_voice_id = allocate_voice_id or self._next_voice_id
        self._voice_seq = 10_000
        self._state: ChannelRackState | None = None
        self._active_screen = SCREEN1
        self._play_handle: ChannelRackPlayHandle | None = None
        self._playing = False
        self._loop_active = False
        self._loop_pass_index = 0
        self._loop_anchor_quarter = Fraction(0, 1)
        self._loop_anchor_engine_frame = 0
        self._on_claim_audio_focus = on_claim_audio_focus
        self._on_release_to_screen1 = on_release_to_screen1
        self._on_musical_state_changed = on_musical_state_changed

    def set_audio_focus_hooks(
        self,
        *,
        on_claim_focus: Callable[[], None] | None = None,
        on_release_to_screen1: Callable[[], None] | None = None,
    ) -> None:
        """Bind session-owned cross-screen audio focus callbacks (#807)."""
        self._on_claim_audio_focus = on_claim_focus
        self._on_release_to_screen1 = on_release_to_screen1

    def set_on_musical_state_changed(
        self, callback: Callable[[], None] | None
    ) -> None:
        """Bind or clear post-mutation observer for session persistence (#809)."""
        self._on_musical_state_changed = callback

    def _notify_musical_state_changed(self) -> None:
        if self._on_musical_state_changed is not None:
            self._on_musical_state_changed()

    def _claim_audio_focus(self) -> None:
        if self._on_claim_audio_focus is not None:
            self._on_claim_audio_focus()

    @property
    def live_kit(self) -> LiveKitState:
        return self._live_kit

    @property
    def transport(self) -> Any:
        return self._transport

    @property
    def pcm_provider(self) -> SequencerPcmProvider:
        return self._pcm_provider

    @property
    def state(self) -> ChannelRackState | None:
        return self._state

    @property
    def active_screen(self) -> str:
        return self._active_screen

    @property
    def is_playing(self) -> bool:
        return self._playing

    def _next_voice_id(self) -> int:
        self._voice_seq += 1
        return self._voice_seq

    def projection(self) -> dict[str, Any]:
        """Product projection for Single Workspace bottom Rack (#908)."""
        if self._state is None:
            return _empty_bottom_projection()
        return project_bottom_rack_for_qml(self._state, self._live_kit)

    def legacy_screen2_projection(self) -> dict[str, Any]:
        """Historical full seed-row projection (compatibility / protected tests)."""
        if self._state is None:
            return {
                "pattern_id": "",
                "step_count": 16,
                "groups": [],
                "step_markers": [],
                "product_surface": "legacy_screen2",
                "bottom_rack_materialized": False,
                "bottom_rack_height_ratio": 0.0,
                "bottom_rack_height_px": BOTTOM_RACK_EMPTY_STRIP_PX,
            }
        return project_channel_rack_for_qml(self._state)

    def restore_state(self, state: ChannelRackState) -> None:
        """Adopt a validated musical snapshot before first Screen-2 enter (#809).

        Clears playback/loop runtime. Does not claim audio focus. Does not
        rebuild DEFAULT_ON. Does not fire musical-state autosave callbacks —
        callers must wire observers only after restore completes.
        """
        self.stop()
        self._state = state
        self._clear_loop_session()
        self._active_screen = SCREEN1

    def reconcile_live_kit_state(self, *, notify: bool = True) -> bool:
        """Heal existing rack against current Live Kit without Screen-2 enter (#817).

        No-op when no rack state exists (does not materialize a rack). Does not
        claim audio focus or change playback/loop runtime. When ``notify`` is
        False, adopts reconciled state without firing the musical-state observer
        (session Live-Kit autosave owns a single coherent write).
        """
        if self._state is None:
            return False
        previous = self._state
        reconciled = _sync_live_kit_sample_paths(self._state, self._live_kit)
        if reconciled is previous:
            return False
        self._state = reconciled
        if notify:
            self._notify_musical_state_changed()
        return True

    def ensure_state(self, *, notify: bool = True) -> ChannelRackState:
        """Materialize/reconcile Rack from Live Kit without screen or focus (#916).

        Builds Rack state when absent; reconciles Live Kit sample paths when
        already materialized. When ``notify`` is False, skips the musical-state
        observer so Live Kit mutation can own one coherent autosave (#908).
        Does not claim audio focus, mutate ``active_screen``, or start/stop
        playback.
        """
        if self._state is None:
            self._state = build_channel_rack_state(self._live_kit)
            if notify:
                self._notify_musical_state_changed()
        else:
            self.reconcile_live_kit_state(notify=notify)
        return self._state

    def enter_screen2(self) -> ChannelRackState:
        """Legacy Screen-2 enter: claim focus, ensure state, set screen (#916)."""
        self._claim_audio_focus()
        state = self.ensure_state()
        self._active_screen = SCREEN2
        return state

    def leave_screen2(self) -> None:
        self.stop()
        self._active_screen = SCREEN1
        if self._on_release_to_screen1 is not None:
            self._on_release_to_screen1()

    def _require_state(self) -> ChannelRackState:
        if self._state is None:
            raise RuntimeError(
                "Channel Rack is not active; call ensure_state() first"
            )
        return self._state

    def toggle_step(self, channel_id: str, step_index: int) -> ChannelRackState:
        self._require_state()
        self._state = toggle_step(self._state, channel_id, step_index)
        self._notify_musical_state_changed()
        return self._state

    def add_user_channel(self, sample_path: str | None = None) -> ChannelRackState:
        self._require_state()
        self._state = add_user_channel(self._state, sample_path=sample_path)
        self._notify_musical_state_changed()
        return self._state

    def assign_user_channel_sample(
        self, channel_id: str, sample_path: str
    ) -> ChannelRackState:
        """Assign a sample path to an existing user channel (#808)."""
        self._require_state()
        self._state = assign_user_channel_sample(
            self._state, channel_id, sample_path
        )
        self._notify_musical_state_changed()
        return self._state

    def apply_gesture_integration_plan(
        self,
        plan: GestureRackIntegrationPlan,
        *,
        feature_enabled: bool,
    ) -> ChannelRackState:
        """Apply a ready gesture Rack integration plan atomically (#921).

        Fail-closed order (zero side effects until all gates pass):

        VALIDATE → CONSTRUCT TARGET → STOP → ATOMIC REPLACE → OBSERVER ONCE

        ``feature_enabled`` is injected by the caller from
        ``WorkbenchFeatureSettings.gesture_rack_apply_enabled``. This method
        never reads settings files.
        """
        # VALIDATE — before stop / mutation / notify
        if feature_enabled is not True:
            raise ValueError(
                "gesture Rack apply is disabled "
                "(feature_enabled must be True)"
            )
        if not isinstance(plan, GestureRackIntegrationPlan):
            raise TypeError(
                "plan must be a GestureRackIntegrationPlan "
                f"(got {type(plan).__name__})"
            )
        if plan.ready_for_apply is not True:
            raise ValueError(
                "plan is not ready_for_apply; refuse gesture Rack apply"
            )
        current = self._require_state()
        if current != plan.expected_base_state:
            raise StaleGestureRackIntegrationPlanError(
                "stale GestureRackIntegrationPlan: "
                "controller state does not match expected_base_state"
            )
        grid_span = Fraction(plan.target_step_count, 4)
        pattern_length = plan.target_pattern.length_quarter_notes
        if pattern_length < grid_span:
            raise ValueError(
                "target Pattern length "
                f"{pattern_length} is shorter than preserved step-grid span "
                f"{grid_span} (step_count={plan.target_step_count})"
            )

        # CONSTRUCT TARGET — still before stop / mutation / notify
        target = ChannelRackState(
            channels=plan.target_channels,
            pattern=plan.target_pattern,
            step_count=plan.target_step_count,
        )

        # STOP → ATOMIC REPLACE → OBSERVER ONCE
        self.stop()
        self._state = target
        self._notify_musical_state_changed()
        return self._state

    def _clear_loop_session(self) -> None:
        self._loop_active = False
        self._loop_pass_index = 0
        self._loop_anchor_quarter = Fraction(0, 1)
        self._loop_anchor_engine_frame = 0

    def _resolve_engine_adapter(self) -> _SequencerEngineAdapter:
        if hasattr(self._transport, "ensure_engine_running"):
            self._transport.ensure_engine_running()
        raw_engine = None
        if hasattr(self._transport, "get_native_engine"):
            raw_engine = self._transport.get_native_engine()
        if raw_engine is None:
            raise RuntimeError("Native audio engine is required for Channel Rack playback")
        return _SequencerEngineAdapter(raw_engine)

    def _start_pattern_pass(
        self,
        *,
        pass_index: int,
        engine: _SequencerEngineAdapter,
    ) -> ChannelRackPlayHandle:
        self._require_state()
        start_quarter, start_engine = pattern_pass_start_frames(
            self._transport.tempo_map,
            anchor_quarter=self._loop_anchor_quarter,
            anchor_engine_frame=self._loop_anchor_engine_frame,
            pass_index=pass_index,
            length_quarter_notes=self._state.pattern.length_quarter_notes,
        )
        warm_channel_rack_pcm(self._state, self._pcm_provider)
        return play_channel_rack_once(
            self._state,
            tempo_map=self._transport.tempo_map,
            pattern_start_quarter=start_quarter,
            pattern_start_engine_frame=start_engine,
            engine=engine,
            lookahead_frames=self._lookahead_frames,
            pcm_provider=self._pcm_provider,
            allocate_voice_id=self._allocate_voice_id,
        )

    def _adopt_pass_handle(self, handle: ChannelRackPlayHandle, *, pass_index: int) -> bool:
        """Install handle when playable; return False when empty-pass honesty fails closed."""
        if handle.player.done and int(handle.scheduled_count) == 0:
            self._play_handle = None
            self._playing = False
            self._clear_loop_session()
            return False
        self._play_handle = handle
        self._loop_pass_index = pass_index
        self._playing = True
        return True

    def play(self) -> ChannelRackPlayHandle | None:
        self._require_state()
        self._claim_audio_focus()
        self.stop()

        try:
            engine = self._resolve_engine_adapter()
        except RuntimeError:
            self._clear_loop_session()
            raise

        starter = None
        if callable(getattr(self._transport, "play", None)):
            # Production WorkbenchTransportAdapter / SessionTransport clock.
            starter = self._transport.play
        elif callable(getattr(self._transport, "start", None)):
            # Test doubles / compatibility alias.
            starter = self._transport.start
        if starter is not None:
            try:
                starter()
            except Exception as exc:
                # Fail closed: never advertise playing without a live transport clock.
                self._playing = False
                self._play_handle = None
                self._clear_loop_session()
                raise RuntimeError(
                    f"Channel Rack transport failed to start: {exc}"
                ) from exc

        # Play anchor: musical quarter from live session position + current engine
        # clock. Do not assume session quarter 0 after seek / prior transport use.
        session_frame = _read_transport_session_frame(self._transport)
        engine_frame = _read_transport_engine_frame(self._transport)
        self._loop_anchor_quarter = self._transport.tempo_map.frame_to_quarter_note(
            session_frame
        )
        self._loop_anchor_engine_frame = engine_frame
        self._loop_pass_index = 0
        self._loop_active = True

        handle = self._start_pattern_pass(pass_index=0, engine=engine)
        # Honesty: do not advertise playing when the first tick already finished
        # with nothing scheduled (missing PCM / empty pass soft-skip).
        if not self._adopt_pass_handle(handle, pass_index=0):
            return handle
        return handle

    def tick_playback(self) -> Mapping[str, Any] | None:
        """Advance the current pass; start the next finite pass when looping."""
        if not self._playing or self._play_handle is None:
            return None
        raw_engine = self._transport.get_native_engine()
        if raw_engine is None:
            self.stop()
            return None
        engine = _SequencerEngineAdapter(raw_engine)
        engine_frame = _read_transport_engine_frame(self._transport)
        # Prefer live native snapshot when available so scheduling tracks audio clock.
        try:
            if hasattr(self._transport, "poll"):
                self._transport.poll()
                engine_frame = _read_transport_engine_frame(self._transport)
        except Exception:
            pass
        tick = self._play_handle.player.tick(
            engine_frame=engine_frame,
            engine=engine,
            pcm_for_path=self._pcm_provider,
            allocate_voice_id=self._allocate_voice_id,
        )
        if self._play_handle.player.done:
            if self._loop_active and self._state is not None:
                next_index = self._loop_pass_index + 1
                next_handle = self._start_pattern_pass(
                    pass_index=next_index,
                    engine=engine,
                )
                # play_channel_rack_once already performed the initial tick.
                if not self._adopt_pass_handle(next_handle, pass_index=next_index):
                    # Empty / unplayable follow-up pass: fail closed, no busy loop.
                    return {
                        "scheduled_count": 0,
                        "pending_count": 0,
                        "live_voice_count": 0,
                        "playing": False,
                    }
                return {
                    "scheduled_count": int(next_handle.scheduled_count),
                    "pending_count": int(next_handle.player.pending_count),
                    "live_voice_count": int(next_handle.player.live_voice_count),
                    "playing": self._playing,
                }
            self._playing = False
            self._play_handle = None
            self._loop_active = False
        return {
            "scheduled_count": tick.scheduled_count,
            "pending_count": tick.pending_count,
            "live_voice_count": tick.live_voice_count,
            "playing": self._playing,
        }

    def stop(self) -> None:
        handle = self._play_handle
        self._play_handle = None
        self._playing = False
        self._clear_loop_session()
        if handle is None:
            return
        raw_engine = None
        if hasattr(self._transport, "get_native_engine"):
            raw_engine = self._transport.get_native_engine()
        if raw_engine is not None:
            handle.player.stop(_SequencerEngineAdapter(raw_engine))


__all__ = [
    "BOTTOM_RACK_EMPTY_STRIP_PX",
    "BOTTOM_RACK_HEIGHT_RATIO",
    "ChannelRackController",
    "DEFAULT_LOOKAHEAD_FRAMES",
    "ROW_KIND_LOOP_IDENTITY",
    "ROW_KIND_STEP",
    "SCREEN1",
    "SCREEN2",
    "StaleGestureRackIntegrationPlanError",
    "USER_GROUP_NAME",
    "pattern_pass_start_frames",
    "project_bottom_rack_for_qml",
    "project_channel_rack_for_qml",
]
