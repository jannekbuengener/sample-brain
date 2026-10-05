"""Minimal Channel Rack core — Live Kit channels, step grid, one pattern pass.

Projects canonical Live Kit slots into Pattern Core channels, seeds DEFAULT_ON
triggers for sample-bearing channels, toggles 16th-note steps immutably,
appends user-added channels without Live Kit provenance, and schedules one
pattern pass through sequencer_playback. Musical truth stays Python-owned;
this module adds no visual surfaces.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Literal

from .pattern_core import (
    CHANNEL_ID_BY_LIVE_KIT_SLOT,
    Channel,
    Pattern,
    Trigger,
    allocate_user_channel_id,
    require_triggers_reference_known_channels,
)
from .sequencer_pcm import SequencerPcmProvider, canonicalize_pcm_path
from .sequencer_playback import (
    PatternPassPlayer,
    plan_pattern_once,
)
from .session_grid import TempoMap
from .workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState

DEFAULT_PATTERN_ID = "screen2-main"
DEFAULT_STEP_COUNT = 16
DEFAULT_PATTERN_LENGTH = Fraction(4, 1)

ClassificationKind = Literal["oneshot", "loop", "ambiguous"]
_POINT_TRIGGER_SAFE_CLASSES = frozenset({"one_shot", "oneshot"})
_LOOP_CLASSES = frozenset({"loop"})


def normalize_sample_class(value: object | None) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def classification_kind(sample_class: object | None) -> ClassificationKind:
    normalized = normalize_sample_class(sample_class)
    if normalized in _POINT_TRIGGER_SAFE_CLASSES:
        return "oneshot"
    if normalized in _LOOP_CLASSES:
        return "loop"
    return "ambiguous"


def is_point_trigger_safe(sample_class: object | None) -> bool:
    return classification_kind(sample_class) == "oneshot"


def is_explicit_loop(sample_class: object | None) -> bool:
    return classification_kind(sample_class) == "loop"


def sample_class_for_channel(
    channel: Channel, live_kit: LiveKitState
) -> str | None:
    """Live Kit assignment class for seed channels; None for unclassified user channels."""
    if channel.live_kit_group is None or channel.live_kit_slot is None:
        return None
    assignment = live_kit.assignment_for(channel.live_kit_group, channel.live_kit_slot)
    if assignment is None:
        return None
    return getattr(assignment, "sample_class", None)


def point_trigger_eligible_channel_ids(
    state: ChannelRackState, live_kit: LiveKitState
) -> frozenset[str]:
    """Only explicit oneshot channels."""
    return frozenset(
        channel.channel_id
        for channel in state.channels
        if is_point_trigger_safe(sample_class_for_channel(channel, live_kit))
    )


def filter_pattern_for_point_trigger_playback(
    state: ChannelRackState, live_kit: LiveKitState
) -> Pattern:
    """Pure filter: drop triggers for non-oneshot channels; do not mutate state."""
    eligible = point_trigger_eligible_channel_ids(state, live_kit)
    return Pattern(
        pattern_id=state.pattern.pattern_id,
        length_quarter_notes=state.pattern.length_quarter_notes,
        triggers=tuple(
            trigger
            for trigger in state.pattern.triggers
            if trigger.channel_id in eligible
        ),
    )


@dataclass(frozen=True)
class ChannelRackPlayHandle:
    """Result of starting one rack pattern pass via ``PatternPassPlayer``."""

    player: PatternPassPlayer
    planned_count: int
    scheduled_voice_ids: tuple[int, ...]
    scheduled_count: int
    skipped_missing_source_count: int
    skipped_voice_limit_count: int
    skipped_engine_error_count: int


def _sample_bearing(sample_path: str | None) -> bool:
    """True when the channel has a non-empty sample path (playable source)."""
    return sample_path is not None and sample_path != ""


def _full_step_triggers(channel_id: str, step_count: int) -> tuple[Trigger, ...]:
    """DEFAULT_ON seed: every v1 step active at Fraction(step_index, 4)."""
    return tuple(
        Trigger(channel_id=channel_id, position=Fraction(i, 4))
        for i in range(step_count)
    )


@dataclass(frozen=True)
class ChannelRackState:
    """Immutable rack snapshot: channels, active pattern, and step grid size."""

    channels: tuple[Channel, ...]
    pattern: Pattern
    step_count: int

    def __post_init__(self) -> None:
        channel_ids = [channel.channel_id for channel in self.channels]
        if len(channel_ids) != len(set(channel_ids)):
            raise ValueError("channels must have unique channel_id values")
        require_triggers_reference_known_channels(
            self.pattern.triggers,
            known_channel_ids=channel_ids,
        )


def build_channel_rack_state(live_kit: LiveKitState) -> ChannelRackState:
    """Project Live Kit assignments into a 16-step rack with DEFAULT_ON seeds.

    Explicit one-shot sample-bearing channels start with every step active.
    Explicit loop / ambiguous / empty channels remain triggerless (no phantom
    DEFAULT_ON for non-point-trigger-safe material).
    """

    channels: list[Channel] = []
    for group, slots in LIVE_KIT_SLOT_MAPPING:
        for slot in slots:
            assignment = live_kit.assignment_for(group, slot)
            sample_path = str(assignment.path) if assignment is not None else None
            channels.append(
                Channel(
                    channel_id=CHANNEL_ID_BY_LIVE_KIT_SLOT[(group, slot)],
                    live_kit_group=group,
                    live_kit_slot=slot,
                    sample_path=sample_path,
                )
            )

    triggers: list[Trigger] = []
    for channel in channels:
        if not _sample_bearing(channel.sample_path):
            continue
        if not is_point_trigger_safe(sample_class_for_channel(channel, live_kit)):
            continue
        triggers.extend(_full_step_triggers(channel.channel_id, DEFAULT_STEP_COUNT))

    return ChannelRackState(
        channels=tuple(channels),
        pattern=Pattern(
            pattern_id=DEFAULT_PATTERN_ID,
            length_quarter_notes=DEFAULT_PATTERN_LENGTH,
            triggers=tuple(triggers),
        ),
        step_count=DEFAULT_STEP_COUNT,
    )


def reconcile_live_kit_sample_assignments(
    state: ChannelRackState,
    live_kit: LiveKitState,
) -> ChannelRackState:
    """Sync Live Kit seed paths and heal DEFAULT_ON without global pattern reset.

    Per Live Kit seed channel (#806 / #926):

    - empty → newly assigned oneshot: seed canonical DEFAULT_ON for that channel
    - empty → newly assigned loop/ambiguous: set path, do not seed DEFAULT_ON
    - assigned → replaced (still sample-bearing): preserve existing triggers
    - assigned → cleared / empty: strip that channel's triggers (fail-closed)
    - sample-bearing with a manually edited pattern (including all-off): keep it
    - orphan triggers on an empty seed channel: strip them
    - when classification is securely loop: strip that channel's triggers
    - ambiguous with persisted triggers: keep them (playback filter excludes)
    - user-added channels: untouched

    Does not rebuild the full rack; only paths and per-channel trigger sets change.
    """

    updated_channels: list[Channel] = []
    # Per seed channel_id: "seed" | "strip" | "keep"
    seed_heal: dict[str, str] = {}
    path_changed = False

    for channel in state.channels:
        if channel.live_kit_group is None or channel.live_kit_slot is None:
            updated_channels.append(channel)
            continue

        assignment = live_kit.assignment_for(
            channel.live_kit_group,
            channel.live_kit_slot,
        )
        new_path = str(assignment.path) if assignment is not None else None
        old_bearing = _sample_bearing(channel.sample_path)
        new_bearing = _sample_bearing(new_path)
        sample_class = (
            getattr(assignment, "sample_class", None) if assignment is not None else None
        )

        if new_path != channel.sample_path:
            path_changed = True
            updated_channels.append(
                Channel(
                    channel_id=channel.channel_id,
                    live_kit_group=channel.live_kit_group,
                    live_kit_slot=channel.live_kit_slot,
                    sample_path=new_path,
                )
            )
        else:
            updated_channels.append(channel)

        if not new_bearing:
            seed_heal[channel.channel_id] = "strip"
        elif not old_bearing:
            # New assignment: DEFAULT_ON only for explicit oneshot.
            seed_heal[channel.channel_id] = (
                "seed" if is_point_trigger_safe(sample_class) else "keep"
            )
        elif is_explicit_loop(sample_class):
            # Secure loop classification reconciles stale point triggers away.
            seed_heal[channel.channel_id] = "strip"
        else:
            seed_heal[channel.channel_id] = "keep"

    strip_or_seed_ids = {
        channel_id
        for channel_id, action in seed_heal.items()
        if action in {"strip", "seed"}
    }

    if not path_changed:
        needs_trigger_work = False
        for channel_id, action in seed_heal.items():
            if action == "keep":
                continue
            channel_triggers = [
                t for t in state.pattern.triggers if t.channel_id == channel_id
            ]
            if action == "strip" and channel_triggers:
                needs_trigger_work = True
                break
            if action == "seed":
                needs_trigger_work = True
                break
        if not needs_trigger_work:
            return state

    new_triggers: list[Trigger] = [
        trigger
        for trigger in state.pattern.triggers
        if trigger.channel_id not in strip_or_seed_ids
    ]
    for channel_id, action in seed_heal.items():
        if action == "seed":
            new_triggers.extend(_full_step_triggers(channel_id, state.step_count))

    new_pattern = Pattern(
        pattern_id=state.pattern.pattern_id,
        length_quarter_notes=state.pattern.length_quarter_notes,
        triggers=tuple(new_triggers),
    )
    if (
        tuple(updated_channels) == state.channels
        and new_pattern.triggers == state.pattern.triggers
    ):
        return state

    return ChannelRackState(
        channels=tuple(updated_channels),
        pattern=new_pattern,
        step_count=state.step_count,
    )


def add_user_channel(
    state: ChannelRackState,
    *,
    sample_path: str | None = None,
    channel_id: str | None = None,
) -> ChannelRackState:
    """Append a user-added rack channel without Live Kit provenance.

    Sample-bearing user channels seed DEFAULT_ON (all steps active). Empty
    user channels append without adding triggers.
    """

    existing_ids = [channel.channel_id for channel in state.channels]
    new_id = (
        channel_id
        if channel_id is not None
        else allocate_user_channel_id(existing_ids)
    )
    if new_id in existing_ids:
        raise ValueError(f"Duplicate channel_id: {new_id!r}")

    new_channel = Channel(
        channel_id=new_id,
        live_kit_group=None,
        live_kit_slot=None,
        sample_path=sample_path,
    )
    new_triggers = state.pattern.triggers
    if _sample_bearing(sample_path):
        new_triggers = state.pattern.triggers + _full_step_triggers(
            new_id, state.step_count
        )
    return ChannelRackState(
        channels=state.channels + (new_channel,),
        pattern=Pattern(
            pattern_id=state.pattern.pattern_id,
            length_quarter_notes=state.pattern.length_quarter_notes,
            triggers=new_triggers,
        ),
        step_count=state.step_count,
    )


def assign_user_channel_sample(
    state: ChannelRackState,
    channel_id: str,
    sample_path: str,
) -> ChannelRackState:
    """Assign a library sample path to an existing user-added channel (#808).

    Policy mirrors #806 DEFAULT_ON principles for a single user channel:

    - empty → newly assigned: set path and seed DEFAULT_ON for this channel only
    - assigned → replacement: replace path; keep that channel's triggers exactly
    - Live Kit seed channels: rejected (no taxonomy pollution)
    - empty / whitespace path: rejected
    - unknown ``channel_id``: rejected

    User channels keep ``live_kit_group`` / ``live_kit_slot`` as ``None``. Does
    not call :func:`reconcile_live_kit_sample_assignments`.
    """

    if sample_path is None or not str(sample_path).strip():
        raise ValueError("sample_path must be a non-empty sample reference")
    path = str(sample_path).strip()

    known = {channel.channel_id: channel for channel in state.channels}
    if channel_id not in known:
        raise ValueError(f"Unknown channel_id: {channel_id!r}")

    channel = known[channel_id]
    if channel.live_kit_group is not None or channel.live_kit_slot is not None:
        raise ValueError(
            f"Cannot assign sample to Live Kit channel: {channel_id!r}"
        )

    old_bearing = _sample_bearing(channel.sample_path)
    if channel.sample_path == path:
        return state

    updated_channels = tuple(
        Channel(
            channel_id=existing.channel_id,
            live_kit_group=existing.live_kit_group,
            live_kit_slot=existing.live_kit_slot,
            sample_path=path if existing.channel_id == channel_id else existing.sample_path,
        )
        if existing.channel_id == channel_id
        else existing
        for existing in state.channels
    )

    if not old_bearing:
        # empty → assigned: strip orphans for this id, then seed DEFAULT_ON
        other = tuple(
            trigger
            for trigger in state.pattern.triggers
            if trigger.channel_id != channel_id
        )
        new_triggers = other + _full_step_triggers(channel_id, state.step_count)
    else:
        # assigned → replacement: keep exact trigger pattern
        new_triggers = state.pattern.triggers

    return ChannelRackState(
        channels=updated_channels,
        pattern=Pattern(
            pattern_id=state.pattern.pattern_id,
            length_quarter_notes=state.pattern.length_quarter_notes,
            triggers=new_triggers,
        ),
        step_count=state.step_count,
    )


def toggle_step(
    state: ChannelRackState,
    channel_id: str,
    step_index: int,
) -> ChannelRackState:
    """Return a new state with the given step toggled on or off."""

    known_ids = {channel.channel_id for channel in state.channels}
    if channel_id not in known_ids:
        raise ValueError(f"Unknown channel_id: {channel_id!r}")

    if type(step_index) is not int:
        raise TypeError(
            f"step_index must be an exact int (got {type(step_index).__name__})"
        )
    if not (0 <= step_index < state.step_count):
        raise ValueError(
            f"step_index must be in 0..{state.step_count - 1}, got {step_index}"
        )

    position = Fraction(step_index, 4)
    existing = state.pattern.triggers
    match = Trigger(channel_id=channel_id, position=position)

    if match in existing:
        new_triggers = tuple(t for t in existing if t != match)
    else:
        new_triggers = existing + (match,)

    return ChannelRackState(
        channels=state.channels,
        pattern=Pattern(
            pattern_id=state.pattern.pattern_id,
            length_quarter_notes=state.pattern.length_quarter_notes,
            triggers=new_triggers,
        ),
        step_count=state.step_count,
    )


def play_channel_rack_once(
    state: ChannelRackState,
    *,
    tempo_map: TempoMap,
    pattern_start_quarter: Fraction,
    pattern_start_engine_frame: int,
    engine: Any,
    lookahead_frames: int,
    pcm_for_path: Callable[[str], Any] | None = None,
    pcm_provider: SequencerPcmProvider | None = None,
    allocate_voice_id: Callable[[], int],
    live_kit: LiveKitState | None = None,
) -> ChannelRackPlayHandle:
    """Plan and start one pattern pass via ``PatternPassPlayer``.

    Builds a stateful player for the full planned event list, runs an initial
    ``tick`` at ``pattern_start_engine_frame`` with the injected
    ``lookahead_frames``, and returns a handle so callers can continue ticking
    as the engine clock advances. The eager ``schedule_pattern_once`` helper is
    intentionally not used here.

    When ``live_kit`` is provided, only explicit oneshot triggers are planned
    (``filter_pattern_for_point_trigger_playback``). Loop/ambiguous triggers
    remain in Pattern state but do not reach ``PatternPassPlayer``.

    Resolution for PCM:

    1. Explicit ``pcm_for_path`` callable (tests / custom injectors).
    2. Else long-lived ``pcm_provider`` (preferred production path).

    At least one of ``pcm_for_path`` / ``pcm_provider`` is required. The provider
    is never created ephemerally here — keep it at rack/session lifetime and
    prefer ``warm_channel_rack_pcm`` before anchoring playback.
    """

    resolver = _resolve_pcm_injector(
        pcm_for_path=pcm_for_path,
        pcm_provider=pcm_provider,
        tempo_map=tempo_map,
    )

    channels_by_id: Mapping[str, Channel] = {
        channel.channel_id: channel for channel in state.channels
    }
    pattern = (
        filter_pattern_for_point_trigger_playback(state, live_kit)
        if live_kit is not None
        else state.pattern
    )
    planned = plan_pattern_once(
        pattern=pattern,
        channels_by_id=channels_by_id,
        tempo_map=tempo_map,
        pattern_start_quarter=pattern_start_quarter,
        pattern_start_engine_frame=pattern_start_engine_frame,
    )
    player = PatternPassPlayer(
        planned_triggers=planned,
        lookahead_frames=lookahead_frames,
    )
    tick = player.tick(
        engine_frame=pattern_start_engine_frame,
        engine=engine,
        pcm_for_path=resolver,
        allocate_voice_id=allocate_voice_id,
    )
    return ChannelRackPlayHandle(
        player=player,
        planned_count=player.planned_count,
        scheduled_voice_ids=tick.scheduled_voice_ids,
        scheduled_count=tick.scheduled_count,
        skipped_missing_source_count=tick.skipped_missing_source_count,
        skipped_voice_limit_count=tick.skipped_voice_limit_count,
        skipped_engine_error_count=tick.skipped_engine_error_count,
    )


def _resolve_pcm_injector(
    *,
    pcm_for_path: Callable[[str], Any] | None,
    pcm_provider: SequencerPcmProvider | None,
    tempo_map: TempoMap,
) -> Callable[[str], Any]:
    if pcm_for_path is not None:
        bound_provider = _sequencer_provider_from_callable(pcm_for_path)
        if bound_provider is not None:
            _require_matching_sample_rate(bound_provider, tempo_map)
        return pcm_for_path
    if pcm_provider is not None:
        _require_matching_sample_rate(pcm_provider, tempo_map)
        return pcm_provider
    raise ValueError(
        "play_channel_rack_once requires pcm_provider or pcm_for_path; "
        "pass a long-lived SequencerPcmProvider so PCM cache survives pattern passes"
    )


def _sequencer_provider_from_callable(
    pcm_for_path: Callable[[str], Any],
) -> SequencerPcmProvider | None:
    if isinstance(pcm_for_path, SequencerPcmProvider):
        return pcm_for_path
    owner = getattr(pcm_for_path, "__self__", None)
    if isinstance(owner, SequencerPcmProvider):
        return owner
    return None


def _require_matching_sample_rate(
    provider: SequencerPcmProvider,
    tempo_map: TempoMap,
) -> None:
    if int(provider.sample_rate) != int(tempo_map.sample_rate):
        raise ValueError(
            "pcm_provider.sample_rate must match tempo_map.sample_rate "
            f"(got provider={provider.sample_rate}, tempo_map={tempo_map.sample_rate})"
        )


def warm_channel_rack_pcm(
    state: ChannelRackState,
    provider: SequencerPcmProvider,
) -> tuple[str, ...]:
    """Decode/cache every assigned sample path before scheduling voices.

    Capacity is measured by provider cache identity (canonical key), not raw
    path spellings, so aliases of one file count once.

    Returns every raw alias that failed to load (fail-soft), including all
    spellings that share a failed identity. Raises ``ValueError`` when unique
    identities exceed ``provider.max_entries``.
    """

    aliases_by_identity: dict[str, list[str]] = {}
    order: list[str] = []
    for channel in state.channels:
        path = channel.sample_path
        if path is None or path == "" or path.isspace():
            continue
        try:
            identity = canonicalize_pcm_path(path)
        except (OSError, RuntimeError, ValueError):
            identity = path
        if identity not in aliases_by_identity:
            aliases_by_identity[identity] = []
            order.append(identity)
        aliases_by_identity[identity].append(path)

    if len(order) > provider.max_entries:
        raise ValueError(
            "warm_channel_rack_pcm requires provider.max_entries >= number of "
            "unique sample identities "
            f"(need {len(order)}, max_entries={provider.max_entries})"
        )

    failed: list[str] = []
    for identity in order:
        aliases = aliases_by_identity[identity]
        representative = aliases[0]
        if provider.pcm_for_path(representative) is None:
            failed.extend(aliases)
    return tuple(failed)


__all__ = [
    "ChannelRackPlayHandle",
    "ChannelRackState",
    "ClassificationKind",
    "add_user_channel",
    "assign_user_channel_sample",
    "build_channel_rack_state",
    "classification_kind",
    "filter_pattern_for_point_trigger_playback",
    "is_explicit_loop",
    "is_point_trigger_safe",
    "normalize_sample_class",
    "play_channel_rack_once",
    "point_trigger_eligible_channel_ids",
    "reconcile_live_kit_sample_assignments",
    "sample_class_for_channel",
    "toggle_step",
    "warm_channel_rack_pcm",
]
