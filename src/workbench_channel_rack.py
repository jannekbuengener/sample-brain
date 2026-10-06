"""Screen-2 Channel Rack controller — Python musical SoT + QML command surface.

Owns one :class:`ChannelRackState` per Workbench session, projects it for QML,
and routes Play/Stop through ``play_channel_rack_once`` / ``PatternPassPlayer``.
Screen-2 Play loops by orchestrating successive finite one-pass players until
Stop (#810). Does not own Live Kit, TempoMap, or the native audio engine; those
stay on the shared session transport. QML never holds pattern or loop shadow
truth.

User-channel classification is derived, session-bound, and never persisted
(``docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md``). The controller resolves it
only at the frozen boundaries B1-B4, keeps one path-keyed binding, freezes
path + class per Rack Play (``PLAYBACK_CLASSIFICATION_FREEZE``), and defers
durable user-channel mutations until after Stop (``PLAYBACK_MUTATION_APPLY_
POLICY``). It performs no library I/O itself.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .channel_rack import (
    ChannelRackPlayHandle,
    ChannelRackState,
    add_user_channel,
    assign_user_channel_sample,
    build_channel_rack_state,
    classification_kind,
    is_explicit_loop,
    is_point_trigger_safe,
    play_channel_rack_once,
    point_trigger_eligible_channel_ids,
    reconcile_live_kit_sample_assignments,
    sample_class_for_channel,
    toggle_step,
    warm_channel_rack_pcm,
)
from .gesture_rack_integration import GestureRackIntegrationPlan
from .loop_rack_playback import (
    LoopCycleSpec,
    NaturalCycleLoopPlayer,
    build_loop_cycle_specs,
)
from .pattern_core import Channel, Pattern, Trigger, allocate_user_channel_id
from .sequencer_pcm import SequencerPcmProvider
from .session_grid import TempoMap
from .workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState
from .workbench_user_sample_metadata import (
    EMPTY_USER_SAMPLE_METADATA_BINDING,
    UserSampleMetadata,
    UserSampleMetadataBinding,
)

DEFAULT_LOOKAHEAD_FRAMES = 4800
USER_GROUP_NAME = "User"
SCREEN1 = "screen1"
SCREEN2 = "screen2"

# Single Workspace bottom Rack geometry baselines (#908).
BOTTOM_RACK_HEIGHT_RATIO = 0.24
BOTTOM_RACK_EMPTY_STRIP_PX = 32
ROW_KIND_STEP = "step"
ROW_KIND_LOOP_IDENTITY = "loop_identity"


class GestureRackApplyPostMutationError(RuntimeError):
    """A failure raised *after* ``apply_gesture_integration_plan`` mutated state.

    The Rack state is assigned before the musical-state observer runs, so any
    exception escaping the observer — including one that happens to be a
    :class:`StaleGestureRackIntegrationPlanError` from a nested apply — arrives
    too late to be a zero-mutation rejection. This wrapper preserves that
    provenance so callers cannot mistake it for a pre-mutation rejection.

    The original exception is available via ``__cause__``.
    """


class StaleGestureRackIntegrationPlanError(ValueError):
    """Pre-mutation rejection of a stale ``GestureRackIntegrationPlan`` (#921).

    Raised by :meth:`ChannelRackController.apply_gesture_integration_plan`
    **only** when the live controller state no longer matches the plan's
    ``expected_base_state``. That check runs before ``stop()``, before the
    state assignment, and before the musical-state observer, so catching this
    type is always safe and never implies the Rack was already mutated.

    Callers must not infer this from a message match. Exceptions raised *after*
    the state assignment — notably from the observer callback — are wrapped in
    :class:`GestureRackApplyPostMutationError`, so they can never surface as
    this type even if the observer raised one itself.

    Subclasses :class:`ValueError` for backward compatibility with existing
    ``pytest.raises(ValueError)`` call sites.
    """


def _row_kind_for_channel(
    channel: Channel,
    live_kit: LiveKitState,
    *,
    user_metadata: Mapping[str, Any] | None,
) -> str:
    """Classify one channel for bottom Rack projection (#908/#920/#952).

    Point-trigger-safe (one_shot/oneshot) → step grid. Loop-class or
    missing/ambiguous sample_class → identity only (no step grid). User rows
    read the same resolved binding through :func:`sample_class_for_channel` as
    every other consumer, so no second normalization or class set exists here.
    """

    resolved = sample_class_for_channel(channel, live_kit, user_metadata=user_metadata)
    if is_point_trigger_safe(resolved):
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
    *,
    user_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Single Workspace bottom Rack projection (#908).

    Occupied Live Kit / user channels only. Empty groups omitted. Point-trigger-
    safe one-shot rows expose the step grid; loop-class / ambiguous rows expose
    identity without a misleading DEFAULT_ON step grid (#920 deferred).

    ``user_metadata`` is the resolved path-keyed binding (#952). User rows are
    classified through the same ``sample_class_for_channel`` consumption point
    as playback, so projection can no longer hardcode a user-row class. The
    ``None`` default reproduces the pre-#952 fail-closed user rows.
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
            row_kind = _row_kind_for_channel(channel, live_kit, user_metadata=None)
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
        # Binding decides the row kind; no evidence fails closed to identity only.
        row_kind = _row_kind_for_channel(
            channel, live_kit, user_metadata=user_metadata
        )
        step_enabled = row_kind == ROW_KIND_STEP
        user_rows.append(
            {
                "channel_id": channel.channel_id,
                "display_name": channel.channel_id.replace("ch_user_", "User "),
                "sample_path": channel.sample_path or "",
                "sample_label": _sample_label(channel.sample_path),
                "live_kit_group": None,
                "live_kit_slot": None,
                "is_user_channel": True,
                "steps": steps_by_channel[channel.channel_id] if step_enabled else [],
                "row_kind": row_kind,
                "step_grid_enabled": step_enabled,
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
    *,
    user_metadata: Mapping[str, Any] | None = None,
) -> ChannelRackState:
    """Refresh Live Kit seed paths and heal DEFAULT_ON for late assignments.

    Delegates to :func:`reconcile_live_kit_sample_assignments` so empty→assigned
    seeds DEFAULT_ON, replacements preserve user triggers, and clears strip
    orphan/trigger state fail-closed (#806). With an injected binding the same
    reconcile also strips stale user-channel triggers for resolved explicit loops
    (#952). Never resolves anything.
    """

    return reconcile_live_kit_sample_assignments(
        state, live_kit, user_metadata=user_metadata
    )


def _sample_bearing(sample_path: str | None) -> bool:
    """True when the channel holds a non-empty durable sample path."""
    return sample_path is not None and sample_path != ""


def _is_user_channel(channel: Channel) -> bool:
    """True for user-added channels (no Live Kit provenance)."""
    return channel.live_kit_group is None and channel.live_kit_slot is None


def _distinct_user_paths(state: ChannelRackState) -> tuple[str, ...]:
    """Ordered distinct non-empty user-channel sample paths."""
    return tuple(
        dict.fromkeys(
            channel.sample_path
            for channel in state.channels
            if _is_user_channel(channel) and _sample_bearing(channel.sample_path)
        )
    )


def _clear_channel_sample_path(
    state: ChannelRackState, channel_id: str
) -> ChannelRackState:
    """Clear one channel's ``sample_path``, keeping its triggers exactly.

    The counterpart to :func:`channel_rack.assign_user_channel_sample`: a clear
    drops the association without touching that channel's triggers, and leaves
    every unrelated channel, pattern, and step-grid value byte-identical.
    """
    channels = tuple(
        replace(channel, sample_path=None) if channel.channel_id == channel_id else channel
        for channel in state.channels
    )
    if channels == state.channels:
        return state
    return ChannelRackState(
        channels=channels,
        pattern=state.pattern,
        step_count=state.step_count,
    )


@dataclass(frozen=True)
class _PendingUserChannelMutation:
    """Declarative user-channel mutation deferred by ``PLAYBACK_MUTATION_APPLY_POLICY``.

    Only the *intent* is queued, never a state snapshot: Pattern and trigger
    state is deliberately not per-Play frozen (§6), so a mid-Play step toggle
    must survive the adoption. Replaying the intent against the live state at
    adoption time keeps that edit, keeps the ``DEFAULT_ON`` seeding rules owned
    by the core transitions, and still resolves nothing a second time.
    """

    added: tuple[tuple[str, str | None], ...] = ()
    paths: Mapping[str, str | None] = field(default_factory=dict)
    entries: Mapping[str, UserSampleMetadata] = field(default_factory=dict)
    replaced: frozenset[str] = frozenset()
    prune: bool = False

    def merged_with(self, other: "_PendingUserChannelMutation") -> "_PendingUserChannelMutation":
        """Fold a later queued mutation into this one, latest intent wins."""
        paths = dict(self.paths)
        paths.update(other.paths)
        entries = dict(self.entries)
        entries.update(other.entries)
        return _PendingUserChannelMutation(
            added=self.added + other.added,
            paths=paths,
            entries=entries,
            replaced=self.replaced | other.replaced,
            prune=self.prune or other.prune,
        )


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
        user_metadata_resolver: Any | None = None,
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
        self._natural_loop_player: NaturalCycleLoopPlayer | None = None
        self._frozen_loop_specs: tuple[LoopCycleSpec, ...] = ()
        self._frozen_sync_enabled: bool | None = None
        self._frozen_master_bpm: float | None = None
        self._on_claim_audio_focus = on_claim_audio_focus
        self._on_release_to_screen1 = on_release_to_screen1
        self._on_musical_state_changed = on_musical_state_changed
        # #952: injected resolver is the only classification I/O owner. With
        # ``None`` every user channel stays ambiguous and nothing resolves.
        self._user_metadata_resolver = user_metadata_resolver
        self._user_metadata: UserSampleMetadataBinding = EMPTY_USER_SAMPLE_METADATA_BINDING
        self._pending_user_mutation: _PendingUserChannelMutation | None = None
        self._playback_classification_snapshot: (
            Mapping[str, tuple[str, str | None, float | None]] | None
        ) = None
        self._frozen_user_metadata: UserSampleMetadataBinding | None = None

    # ------------------------------------------------------------------
    # #952 user-channel classification (derived, never persisted)
    # ------------------------------------------------------------------

    @property
    def user_metadata(self) -> UserSampleMetadataBinding:
        """Read-only derived binding keyed by exact durable sample path."""
        return self._user_metadata

    @property
    def playback_classification_snapshot(
        self,
    ) -> Mapping[str, tuple[str, str | None, float | None]] | None:
        """Per-Play frozen ``channel_id -> (path, class, source_bpm)``.

        ``None`` whenever no Rack Play is active. Pattern and trigger state is
        deliberately *not* frozen: only path and classification.
        """
        return self._playback_classification_snapshot

    @property
    def _classification_binding(self) -> UserSampleMetadataBinding:
        """Binding every classification consumer must read this Play.

        While a Rack Play is active this is the frozen per-Play binding, so no
        mid-Play mutation can retarget, mute, or re-classify a channel. Outside
        a Play it is the live derived binding.
        """
        if self._playing and self._frozen_user_metadata is not None:
            return self._frozen_user_metadata
        return self._user_metadata

    def _resolve_user_paths(
        self, paths: Mapping[str, Any] | tuple[str, ...] | list[str]
    ) -> UserSampleMetadataBinding:
        """One bounded resolve call for a batch of paths (B1/B3/B4).

        Returns an empty binding — never an exception — when no resolver is
        injected, the batch is empty, or the resolver fails: every one of those
        cases fails closed to ``ambiguous`` instead of breaking playback.
        """
        resolver = self._user_metadata_resolver
        if resolver is None:
            return EMPTY_USER_SAMPLE_METADATA_BINDING
        ordered = tuple(p for p in dict.fromkeys(paths) if p)
        if not ordered:
            return EMPTY_USER_SAMPLE_METADATA_BINDING
        try:
            binding = resolver.resolve(ordered)
        except Exception:
            return EMPTY_USER_SAMPLE_METADATA_BINDING
        if not isinstance(binding, Mapping):
            return EMPTY_USER_SAMPLE_METADATA_BINDING
        return binding if binding else UserSampleMetadataBinding()

    def _adopt_user_metadata(
        self,
        state: ChannelRackState,
        entries: Mapping[str, UserSampleMetadata],
    ) -> ChannelRackState:
        """Apply the binding trigger precedence to one already-built state.

        Frozen order (#952 §5): resolved explicit ``loop`` strips that channel's
        triggers; ``ambiguous`` and explicit one-shot preserve them verbatim and
        never re-seed. Nothing else in the pattern changes.
        """
        binding = (
            entries
            if isinstance(entries, UserSampleMetadataBinding)
            else UserSampleMetadataBinding(entries)
        )
        strip_ids = tuple(
            channel.channel_id
            for channel in state.channels
            if _is_user_channel(channel)
            and _sample_bearing(channel.sample_path)
            and is_explicit_loop(
                sample_class_for_channel(
                    channel, self._live_kit, user_metadata=binding
                )
            )
        )
        if not strip_ids:
            return state
        kept = tuple(
            trigger
            for trigger in state.pattern.triggers
            if trigger.channel_id not in strip_ids
        )
        if kept == state.pattern.triggers:
            return state
        return ChannelRackState(
            channels=state.channels,
            pattern=Pattern(
                pattern_id=state.pattern.pattern_id,
                length_quarter_notes=state.pattern.length_quarter_notes,
                triggers=kept,
            ),
            step_count=state.step_count,
        )

    def _commit_user_mutation(self, pending: _PendingUserChannelMutation) -> ChannelRackState:
        """Adopt one user-channel mutation now, or queue it for after Stop.

        Ordering is frozen as resolve → build target state (including the
        classification-implied reconcile) → adopt state → notify once
        (§5). While Rack Play is active (``PLAYBACK_MUTATION_APPLY_POLICY``)
        nothing durable changes and nothing is persisted; the intent is queued
        and adopted atomically by the next ``stop()`` or by the next explicit
        Rack Play before its anchor.

        Notification follows the durable state, not the derived binding (§7):
        evidence that changes only the classification - and therefore no
        trigger strip - is adopted silently, because the binding is never
        serialized and must not cause a musical-state autosave.
        """
        if self._playing:
            queued = (
                pending
                if self._pending_user_mutation is None
                else self._pending_user_mutation.merged_with(pending)
            )
            self._pending_user_mutation = queued
            return self._require_state()
        return self._adopt_user_mutation(pending, notify=True)

    def _adopt_user_mutation(
        self, pending: _PendingUserChannelMutation, *, notify: bool
    ) -> ChannelRackState:
        """Apply one pending intent against the *live* state and binding."""
        base_state = self._require_state()
        base_metadata = self._user_metadata

        # Replay the intent through the core transitions so DEFAULT_ON seeding,
        # Live Kit rejection, and trigger retention stay owned by one place.
        target = base_state
        for channel_id, path in pending.added:
            target = add_user_channel(
                target, sample_path=path, channel_id=channel_id
            )
        for channel_id, path in pending.paths.items():
            if path is None:
                target = _clear_channel_sample_path(target, channel_id)
            else:
                target = assign_user_channel_sample(target, channel_id, path)

        referenced = {
            channel.sample_path
            for channel in target.channels
            if _is_user_channel(channel) and _sample_bearing(channel.sample_path)
        }
        entries = dict(base_metadata)
        entries.update(pending.entries)
        if pending.prune:
            for key in tuple(entries):
                if key not in referenced:
                    entries.pop(key, None)
        for key in pending.replaced:
            if key not in referenced:
                entries.pop(key, None)
        binding = UserSampleMetadataBinding(entries)
        target = self._adopt_user_metadata(target, binding)

        self._state = target
        self._user_metadata = binding
        if notify and target is not base_state:
            self._notify_musical_state_changed()
        return target

    def _adopt_pending_user_mutation(self, *, notify: bool = True) -> bool:
        """Apply a queued mid-Play mutation as one coherent adoption."""
        pending = self._pending_user_mutation
        if pending is None:
            return False
        self._pending_user_mutation = None
        before = self._state
        self._adopt_user_mutation(pending, notify=notify)
        return self._state is not before

    def _discard_pending_user_mutation(self) -> None:
        """Drop a queued mutation without applying or persisting it."""
        self._pending_user_mutation = None

    def refresh_user_channel_metadata(self) -> UserSampleMetadataBinding:
        """B4: the explicit seam for library re-analysis / manual rescan.

        Resolves every distinct user-channel path in one read and rebuilds the
        binding from that evidence, then applies the frozen trigger precedence.
        Resolve-only changes never notify; a resolution that also implies a
        trigger strip fires the musical-state observer exactly once. Outside a
        Play this applies immediately; during a Play the whole rebuild is queued
        under ``PLAYBACK_MUTATION_APPLY_POLICY``.
        """
        state = self._require_state()
        paths = _distinct_user_paths(state)
        resolved = self._resolve_user_paths(paths)
        self._commit_user_mutation(
            _PendingUserChannelMutation(
                paths={},
                entries=resolved,
                replaced=frozenset(paths),
                prune=True,
            )
        )
        return self._user_metadata

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
        """Product projection for Single Workspace bottom Rack (#908).

        Reads the live derived binding: projection is display, not playback, so
        it is deliberately *not* the per-Play frozen snapshot (#952 §6).
        """
        if self._state is None:
            return _empty_bottom_projection()
        return project_bottom_rack_for_qml(
            self._state, self._live_kit, user_metadata=self._user_metadata
        )

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

        B1: resolves every distinct user-channel path of the restored state
        through one read-only library connection. Resolution happens here,
        before observers are wired, so resume writes nothing.

        Clears playback/loop runtime. Does not claim audio focus. Does not
        rebuild DEFAULT_ON. Does not fire musical-state autosave callbacks —
        callers must wire observers only after restore completes.
        """
        self._discard_pending_user_mutation()
        self.stop()
        self._state = state
        self._user_metadata = self._resolve_user_paths(_distinct_user_paths(state))
        self._clear_loop_session()
        self._active_screen = SCREEN1

    def reconcile_live_kit_state(self, *, notify: bool = True) -> bool:
        """Heal existing rack against current Live Kit without Screen-2 enter (#817).

        B5: never resolves. Reads the current binding only, so an explicit-loop
        user channel heals its stale triggers deterministically and exactly once.

        No-op when no rack state exists (does not materialize a rack). Does not
        claim audio focus or change playback/loop runtime. When ``notify`` is
        False, adopts reconciled state without firing the musical-state observer
        (session Live-Kit autosave owns a single coherent write).
        """
        if self._state is None:
            return False
        previous = self._state
        reconciled = _sync_live_kit_sample_paths(
            self._state, self._live_kit, user_metadata=self._classification_binding
        )
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
        """Append a user channel; a non-empty ``sample_path`` is a B2 boundary."""
        live = self._require_state()
        path = str(sample_path).strip() if sample_path is not None else None
        if not path:
            path = None

        # Allocate the opaque ID now so a Play can queue the intent, but keep the
        # channel itself inert until adoption: the core transition (and its
        # DEFAULT_ON seeding) runs in _adopt_user_mutation. IDs already claimed by
        # earlier queued additions count as taken, or two adds in one Play would
        # collide at adoption.
        pending = self._pending_user_mutation
        queued_ids = pending.added if pending is not None else ()
        reserved_ids = tuple(
            dict.fromkeys(
                [
                    *(channel.channel_id for channel in live.channels),
                    *(channel_id for channel_id, _ in queued_ids),
                ]
            )
        )
        added_channel_id = allocate_user_channel_id(reserved_ids)

        pending = _PendingUserChannelMutation(
            added=((added_channel_id, path),),
            entries=(
                self._resolved_entry_for(path) if path is not None else {}
            ),
            prune=True,
        )
        return self._commit_user_mutation(pending)

    def _resolved_entry_for(self, path: str) -> dict[str, UserSampleMetadata]:
        """B2 boundary: resolve one path exactly once, or no entry at all.

        Missing, stale, unreadable, or non-explicit evidence yields no entry, so
        the channel fails closed as ``ambiguous`` rather than guessing.
        """
        entry = self._resolve_user_paths((path,)).get(path)
        if entry is None:
            return {}
        return {path: entry}

    def _queued_view_path(self, channel: Channel) -> str | None:
        """The path a channel holds in the *queued* view, or the live one.

        A second mutation queued behind a pending replacement must treat the
        pending value as the previous path. Reading the live channel instead
        would leave the interim key in the binding forever.
        """
        pending = self._pending_user_mutation
        if pending is not None:
            return pending.paths.get(channel.channel_id, channel.sample_path)
        return channel.sample_path

    def assign_user_channel_sample(
        self, channel_id: str, sample_path: str
    ) -> ChannelRackState:
        """Assign a sample path to an existing user channel (#808).

        B2 boundary: resolves the new path, drops the previous key when no other
        channel still references it (reference-counted, because several channels
        may legally share one path), then applies the frozen trigger precedence.
        A same-path re-assign is a no-op that resolves nothing.
        """
        state = self._require_state()
        path = str(sample_path or "").strip()
        if not path:
            raise ValueError("sample_path must be a non-empty sample reference")
        channel = self._require_user_channel(channel_id)
        previous_path = self._queued_view_path(channel)
        if previous_path == path and self._pending_user_mutation is None:
            # Same-path re-assign: no resolve, no mutation, no observer call.
            return state

        # B2: resolve the new path exactly once, here, at the boundary.
        return self._commit_user_mutation(
            _PendingUserChannelMutation(
                paths={channel_id: path},
                entries=self._resolved_entry_for(path),
                replaced=frozenset(
                    {previous_path} if _sample_bearing(previous_path) else set()
                ),
            )
        )

    def clear_user_channel_sample(self, channel_id: str) -> ChannelRackState:
        """Clear a user channel's sample association (#952, named public seam).

        Frozen semantics:

        - unknown ``channel_id`` ⇒ ``ValueError``, no mutation, no resolution;
        - Live Kit seed channel ⇒ ``ValueError`` — clearing a seed channel stays
          a Live Kit operation;
        - already-empty user channel ⇒ no-op: no resolution, no observer call;
        - otherwise ``sample_path`` becomes ``None``, that channel's triggers and
          every unrelated channel/pattern invariant are preserved, the binding key
          is dropped only when no other channel still references it, and the
          musical-state observer fires exactly once.
        """
        state = self._require_state()
        channel = self._require_user_channel(channel_id)
        previous_path = self._queued_view_path(channel)
        if not _sample_bearing(previous_path):
            # Already empty in the queued view: no resolution, no mutation, no
            # observer call.
            return state
        return self._commit_user_mutation(
            _PendingUserChannelMutation(
                paths={channel_id: None},
                replaced=frozenset({str(previous_path)}),
            )
        )

    def _require_user_channel(self, channel_id: str) -> Channel:
        """Resolve a user channel or reject with the frozen ``ValueError``s."""
        state = self._require_state()
        for channel in state.channels:
            if channel.channel_id == channel_id:
                break
        else:
            raise ValueError(f"Unknown channel_id: {channel_id!r}")
        if not _is_user_channel(channel):
            raise ValueError(
                f"Not a user-added channel: {channel_id!r}; Live Kit channels are "
                "managed through the Live Kit, not the Rack"
            )
        return channel

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
        stale_reason: str | None = None
        if current != plan.expected_base_state:
            stale_reason = "controller state does not match expected_base_state"
        elif self._pending_user_mutation is not None:
            # A queued user-channel mutation would be adopted mid-apply, so the
            # plan no longer describes the state it would land on. Fail closed
            # as a stale plan instead of silently reverting the queued change.
            stale_reason = (
                "a user-channel mutation is queued from the active Rack Play and "
                "will be adopted on the next Stop or Rack Play; apply the plan "
                "again afterwards"
            )
        if stale_reason is not None:
            # One raise site only: the #928 guard requires a single owner for the
            # typed stale error, so every staleness cause is decided above.
            raise StaleGestureRackIntegrationPlanError(
                f"stale GestureRackIntegrationPlan: {stale_reason}"
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

        # B3 (#952): resolve only the gesture-introduced or gesture-changed
        # paths. Preserved base-channel bindings carry over untouched, so a
        # gesture apply never turns into an implicit metadata refresh.
        base_metadata = self._classification_binding
        delta = tuple(
            path
            for path in dict.fromkeys(
                channel.sample_path
                for channel in plan.target_channels
                if _is_user_channel(channel) and _sample_bearing(channel.sample_path)
            )
            if path not in base_metadata
        )
        entries = dict(base_metadata)
        for path, entry in self._resolve_user_paths(delta).items():
            entries[path] = entry
        target_metadata = UserSampleMetadataBinding(entries)
        target = self._adopt_user_metadata(target, target_metadata)

        # STOP → ATOMIC REPLACE → OBSERVER ONCE
        self.stop()
        self._state = target
        self._user_metadata = target_metadata
        try:
            self._notify_musical_state_changed()
        except Exception as exc:
            # State is already replaced here, so this can never be a
            # zero-mutation rejection. Preserve that provenance so a nested
            # StaleGestureRackIntegrationPlanError from the observer cannot be
            # mistaken for the pre-mutation validation branch above.
            raise GestureRackApplyPostMutationError(
                "gesture Rack apply observer failed after state replacement: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        return self._state

    def _clear_loop_session(self) -> None:
        self._loop_active = False
        self._loop_pass_index = 0
        self._loop_anchor_quarter = Fraction(0, 1)
        self._loop_anchor_engine_frame = 0
        self._natural_loop_player = None
        self._frozen_loop_specs = ()
        self._frozen_sync_enabled = None
        self._frozen_master_bpm = None

    def _clear_playback_classification(self) -> None:
        """End the ``PLAYBACK_CLASSIFICATION_FREEZE`` lifetime of one Play.

        Separate from ``_clear_loop_session`` on purpose: the freeze lifetime is
        anchored to the Play, not to audibility. A Play that fail-closes its
        honesty check still anchored a classification snapshot, so only an
        explicit ``stop()`` (or a restore that stops) ends it.
        """
        self._frozen_user_metadata = None
        self._playback_classification_snapshot = None

    def _freeze_playback_classification(self) -> None:
        """Snapshot path + class + source_bpm per channel at the Play anchor.

        ``PLAYBACK_CLASSIFICATION_FREEZE = SNAPSHOT_AT_PLAY_ANCHOR`` (#952 §6).
        Path and classification are frozen together: freezing the binding alone
        would let a later pass replan against a path the snapshot no longer
        holds, which fails silent. Only channels that can become audible are
        frozen — everything else is excluded and therefore not audible at all.
        """
        state = self._require_state()
        metadata = self._user_metadata
        snapshot: dict[str, tuple[str, str | None, float | None]] = {}
        frozen_entries: dict[str, UserSampleMetadata] = {}
        for channel in state.channels:
            path = channel.sample_path
            if not _sample_bearing(path):
                continue
            resolved = sample_class_for_channel(
                channel, self._live_kit, user_metadata=metadata
            )
            kind = classification_kind(resolved)
            if kind == "ambiguous":
                continue
            entry = metadata.get(path)
            source_bpm = getattr(entry, "source_bpm", None)
            snapshot[channel.channel_id] = (str(path), resolved, source_bpm)
            if _is_user_channel(channel):
                # Only user-channel evidence may enter the frozen *user*
                # binding. A Live Kit channel sharing this path resolved through
                # the Live Kit, and writing its class here would let the
                # ambiguous user channel inherit it on the next pass.
                frozen_entries[str(path)] = UserSampleMetadata(
                    sample_class=resolved, source_bpm=source_bpm
                )
        self._playback_classification_snapshot = MappingProxyType(snapshot)
        self._frozen_user_metadata = UserSampleMetadataBinding(frozen_entries)

    def _read_sync_enabled(self) -> bool:
        getter = getattr(self._transport, "is_sync_enabled", None)
        if callable(getter):
            return bool(getter())
        return bool(getattr(self._transport, "sync_enabled", False))

    def _read_master_bpm(self) -> float:
        getter = getattr(self._transport, "get_current_tempo", None)
        if callable(getter):
            return float(getter())
        return float(getattr(self._transport, "bpm", 120.0) or 120.0)

    def _start_natural_loop_player(self, *, engine: _SequencerEngineAdapter) -> None:
        """Freeze Play-time loop specs and start NATURAL_CYCLE_REPEAT scheduler."""
        sync_enabled = self._read_sync_enabled()
        master_bpm = self._read_master_bpm()
        self._frozen_sync_enabled = sync_enabled
        self._frozen_master_bpm = master_bpm
        warm_channel_rack_pcm(self._state, self._pcm_provider)
        specs = build_loop_cycle_specs(
            state=self._state,
            live_kit=self._live_kit,
            pcm_for_path=self._pcm_provider.pcm_for_path,
            play_anchor_engine_frame=self._loop_anchor_engine_frame,
            sync_enabled=sync_enabled,
            master_bpm=master_bpm,
            user_metadata=self._classification_binding,
        )
        self._frozen_loop_specs = specs
        if not specs:
            self._natural_loop_player = None
            return
        player = NaturalCycleLoopPlayer(
            specs,
            pcm_for_path=self._pcm_provider.pcm_for_path,
            lookahead_frames=self._lookahead_frames,
        )
        player.tick(
            engine_frame=self._loop_anchor_engine_frame,
            engine=engine,
            allocate_voice_id=self._allocate_voice_id,
        )
        self._natural_loop_player = player

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
            live_kit=self._live_kit,
            user_metadata=self._classification_binding,
        )

    def _has_active_natural_loops(self) -> bool:
        return self._natural_loop_player is not None and bool(self._frozen_loop_specs)

    def _adopt_pass_handle(self, handle: ChannelRackPlayHandle, *, pass_index: int) -> bool:
        """Install handle when playable; return False when empty-pass honesty fails closed."""
        empty_pass = handle.player.done and int(handle.scheduled_count) == 0
        if empty_pass:
            self._play_handle = None
            if self._has_active_natural_loops():
                # Loop-only playback has no finite point-trigger pass to own.
                # Keep the frozen natural-cycle session active without giving
                # tick_playback() a completed handle to repeatedly replace.
                self._loop_pass_index = pass_index
                self._playing = True
                return True
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

        # PLAYBACK_CLASSIFICATION_FREEZE: freeze path + class at this anchor so
        # every later pass of this Play reads one stable classification.
        self._freeze_playback_classification()

        # Freeze loop specs for this Play (DEFER_UNTIL_NEXT_RACK_PLAY).
        self._start_natural_loop_player(engine=engine)

        handle = self._start_pattern_pass(pass_index=0, engine=engine)
        # Honesty: do not advertise playing when the first tick already finished
        # with nothing scheduled (missing PCM / empty pass soft-skip) and no loops.
        if not self._adopt_pass_handle(handle, pass_index=0):
            return handle
        return handle

    def tick_playback(self) -> Mapping[str, Any] | None:
        """Advance the current pass; start the next finite pass when looping."""
        if not self._playing:
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

        if self._natural_loop_player is not None:
            self._natural_loop_player.tick(
                engine_frame=engine_frame,
                engine=engine,
                allocate_voice_id=self._allocate_voice_id,
            )

        if self._play_handle is None:
            return {
                "scheduled_count": 0,
                "pending_count": 0,
                "live_voice_count": 0,
                "playing": self._playing,
            }

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
                    # Empty / unplayable follow-up pass: fail closed, no busy loop
                    # unless natural-cycle loops are still owning playback.
                    if self._has_active_natural_loops():
                        self._play_handle = None
                        self._loop_pass_index = next_index
                        self._playing = True
                        return {
                            "scheduled_count": 0,
                            "pending_count": 0,
                            "live_voice_count": 0,
                            "playing": True,
                        }
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
            if self._has_active_natural_loops():
                self._play_handle = None
                return {
                    "scheduled_count": tick.scheduled_count,
                    "pending_count": 0,
                    "live_voice_count": tick.live_voice_count,
                    "playing": True,
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
        loop_player = self._natural_loop_player
        self._play_handle = None
        self._playing = False
        self._clear_loop_session()
        raw_engine = None
        if hasattr(self._transport, "get_native_engine"):
            raw_engine = self._transport.get_native_engine()
        if raw_engine is not None:
            adapter = _SequencerEngineAdapter(raw_engine)
            if loop_player is not None:
                loop_player.stop(adapter)
            if handle is not None:
                handle.player.stop(adapter)
        # PLAYBACK_MUTATION_APPLY_POLICY: a mutation queued during this Play
        # lands now as one coherent adoption with exactly one observer call.
        self._adopt_pending_user_mutation()
        # An explicit stop is the only thing that ends the freeze lifetime.
        self._clear_playback_classification()

__all__ = [
    "BOTTOM_RACK_EMPTY_STRIP_PX",
    "BOTTOM_RACK_HEIGHT_RATIO",
    "ChannelRackController",
    "DEFAULT_LOOKAHEAD_FRAMES",
    "GestureRackApplyPostMutationError",
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
