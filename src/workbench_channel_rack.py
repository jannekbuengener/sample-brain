"""Screen-2 Channel Rack controller — Python musical SoT + QML command surface.

Owns one :class:`ChannelRackState` per Workbench session, projects it for QML,
and routes Play/Stop through ``play_channel_rack_once`` / ``PatternPassPlayer``.
Does not own Live Kit, TempoMap, or the native audio engine; those stay on the
shared session transport. QML never holds pattern shadow truth.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Mapping

from .channel_rack import (
    ChannelRackPlayHandle,
    ChannelRackState,
    add_user_channel,
    build_channel_rack_state,
    play_channel_rack_once,
    reconcile_live_kit_sample_assignments,
    toggle_step,
    warm_channel_rack_pcm,
)
from .pattern_core import Trigger
from .sequencer_pcm import SequencerPcmProvider
from .workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState

DEFAULT_LOOKAHEAD_FRAMES = 4800
USER_GROUP_NAME = "User"
SCREEN1 = "screen1"
SCREEN2 = "screen2"


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
    """Pure projection of rack state for the Screen-2 QML surface."""

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
    """Session-owned Screen-2 rack: project + commands + one pattern-pass player."""

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
        self._on_claim_audio_focus = on_claim_audio_focus
        self._on_release_to_screen1 = on_release_to_screen1

    def set_audio_focus_hooks(
        self,
        *,
        on_claim_focus: Callable[[], None] | None = None,
        on_release_to_screen1: Callable[[], None] | None = None,
    ) -> None:
        """Bind session-owned cross-screen audio focus callbacks (#807)."""
        self._on_claim_audio_focus = on_claim_focus
        self._on_release_to_screen1 = on_release_to_screen1

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
        if self._state is None:
            return {
                "pattern_id": "",
                "step_count": 16,
                "groups": [],
                "step_markers": [],
            }
        return project_channel_rack_for_qml(self._state)

    def enter_screen2(self) -> ChannelRackState:
        self._claim_audio_focus()
        if self._state is None:
            self._state = build_channel_rack_state(self._live_kit)
        else:
            self._state = _sync_live_kit_sample_paths(self._state, self._live_kit)
        self._active_screen = SCREEN2
        return self._state

    def leave_screen2(self) -> None:
        self.stop()
        self._active_screen = SCREEN1
        if self._on_release_to_screen1 is not None:
            self._on_release_to_screen1()

    def toggle_step(self, channel_id: str, step_index: int) -> ChannelRackState:
        if self._state is None:
            raise RuntimeError("Channel Rack is not active; call enter_screen2() first")
        self._state = toggle_step(self._state, channel_id, step_index)
        return self._state

    def add_user_channel(self, sample_path: str | None = None) -> ChannelRackState:
        if self._state is None:
            raise RuntimeError("Channel Rack is not active; call enter_screen2() first")
        self._state = add_user_channel(self._state, sample_path=sample_path)
        return self._state

    def play(self) -> ChannelRackPlayHandle | None:
        if self._state is None:
            raise RuntimeError("Channel Rack is not active; call enter_screen2() first")
        self._claim_audio_focus()
        self.stop()

        engine = None
        if hasattr(self._transport, "ensure_engine_running"):
            self._transport.ensure_engine_running()
        if hasattr(self._transport, "get_native_engine"):
            engine = self._transport.get_native_engine()
        if engine is None:
            raise RuntimeError("Native audio engine is required for Channel Rack playback")
        engine = _SequencerEngineAdapter(engine)

        if hasattr(self._transport, "start"):
            try:
                self._transport.start()
            except Exception as exc:
                # Fail closed: never advertise playing without a live transport clock.
                self._playing = False
                self._play_handle = None
                raise RuntimeError(
                    f"Channel Rack transport failed to start: {exc}"
                ) from exc

        warm_channel_rack_pcm(self._state, self._pcm_provider)
        start_frame = int(getattr(self._transport, "engine_frame", 0) or 0)
        handle = play_channel_rack_once(
            self._state,
            tempo_map=self._transport.tempo_map,
            pattern_start_quarter=Fraction(0, 1),
            pattern_start_engine_frame=start_frame,
            engine=engine,
            lookahead_frames=self._lookahead_frames,
            pcm_provider=self._pcm_provider,
            allocate_voice_id=self._allocate_voice_id,
        )
        # Honesty: do not advertise playing when the first tick already finished
        # with nothing scheduled (missing PCM / empty pass soft-skip).
        if handle.player.done and int(handle.scheduled_count) == 0:
            self._play_handle = None
            self._playing = False
            return handle
        self._play_handle = handle
        self._playing = True
        return handle

    def tick_playback(self) -> Mapping[str, Any] | None:
        """Advance one PatternPassPlayer tick; used by the QML timer bridge."""
        if not self._playing or self._play_handle is None:
            return None
        raw_engine = self._transport.get_native_engine()
        if raw_engine is None:
            self.stop()
            return None
        engine = _SequencerEngineAdapter(raw_engine)
        engine_frame = int(getattr(self._transport, "engine_frame", 0) or 0)
        # Prefer live native snapshot when available so scheduling tracks audio clock.
        try:
            if hasattr(self._transport, "poll"):
                self._transport.poll()
                engine_frame = int(getattr(self._transport, "engine_frame", engine_frame))
        except Exception:
            pass
        tick = self._play_handle.player.tick(
            engine_frame=engine_frame,
            engine=engine,
            pcm_for_path=self._pcm_provider,
            allocate_voice_id=self._allocate_voice_id,
        )
        if self._play_handle.player.done:
            self._playing = False
            self._play_handle = None
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
        if handle is None:
            return
        raw_engine = None
        if hasattr(self._transport, "get_native_engine"):
            raw_engine = self._transport.get_native_engine()
        if raw_engine is not None:
            handle.player.stop(_SequencerEngineAdapter(raw_engine))


__all__ = [
    "ChannelRackController",
    "DEFAULT_LOOKAHEAD_FRAMES",
    "SCREEN1",
    "SCREEN2",
    "USER_GROUP_NAME",
    "project_channel_rack_for_qml",
]
