"""Python-owned #1084 Arrangement truth; no UI, clock, store or Pattern copy.

Inert foundation for #1087. Product activation remains the future consumer's
``arrangement_mode_enabled`` gate. Disclosure has no domain command here.
Unknown membership is derived from stable channel IDs, never sample metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from types import MappingProxyType

from .arrangement_32_field_time import (
    ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES,
    CYCLE_LENGTH_QUARTER_NOTES,
    plan_arrangement_block,
    require_32_field_channel_rack_state,
)
from .channel_rack import ChannelRackState
from .sequencer_playback import ScheduledTrigger
from .session_grid import TempoMap

PRESENTATION_GROUPS = MappingProxyType(
    {
        "pg_baseline": ("ch_kick", "ch_bass"),
        "pg_drums": (
            "ch_main_drum",
            "ch_closed_hat",
            "ch_open_hat",
            "ch_percussion",
            "ch_additional",
        ),
        "pg_melodic_atmos_fx": ("ch_lead", "ch_pad", "ch_atmos", "ch_fx"),
        "pg_vocals": (),
    }
)
_MEMBERSHIP = {c: g for g, channels in PRESENTATION_GROUPS.items() for c in channels}
_KEYS = frozenset(
    {
        "schema_version",
        "pattern_id",
        "disabled_blocks",
        "disabled_group_blocks",
        "disabled_track_blocks",
        "end_marker_qn",
    }
)


class ArrangementError(ValueError):
    """Controlled rejection without musical mutation."""


def _block(index: object) -> int:
    if type(index) is not int or index < 0:
        raise ArrangementError("invalid_block_index")
    return index


def _group(identity: object) -> str:
    if not isinstance(identity, str) or identity not in PRESENTATION_GROUPS:
        raise ArrangementError("unknown_group_id")
    return identity


def _marker(value: object) -> Fraction | None:
    if value is None:
        return None
    if type(value) not in (int, Fraction) or value <= 0:
        raise ArrangementError("invalid_end_marker")
    return Fraction(value)


def _snapped_marker(value: object) -> Fraction | None:
    if value is None:
        return None
    marker = _marker(value)
    if marker % 4:
        raise ArrangementError("invalid_end_marker")
    return marker


def _toggle(values: frozenset, key: object, enabled: bool) -> frozenset:
    if type(enabled) is not bool:
        raise ArrangementError("enabled_must_be_bool")
    return values - {key} if enabled else values | {key}


@dataclass(frozen=True)
class ArrangementState:
    """Sparse immutable intent. Tempo eligibility never rewrites this state."""

    pattern_id: str
    disabled_blocks: frozenset[int] = frozenset()
    disabled_group_blocks: frozenset[tuple[str, int]] = frozenset()
    disabled_track_blocks: frozenset[tuple[str, int]] = frozenset()
    end_marker_qn: Fraction | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.pattern_id, str) or not self.pattern_id:
            raise ArrangementError("invalid_pattern_id")
        for values in (
            self.disabled_blocks,
            self.disabled_group_blocks,
            self.disabled_track_blocks,
        ):
            if type(values) is not frozenset:
                raise ArrangementError("corrupt_mask_payload")
        for index in self.disabled_blocks:
            _block(index)
        for values, is_group in (
            (self.disabled_group_blocks, True),
            (self.disabled_track_blocks, False),
        ):
            for pair in values:
                if type(pair) is not tuple or len(pair) != 2:
                    raise ArrangementError("corrupt_mask_payload")
                identity, index = pair
                if not isinstance(identity, str) or not identity:
                    raise ArrangementError("invalid_mask_identity")
                if is_group:
                    _group(identity)
                _block(index)
        object.__setattr__(self, "end_marker_qn", _marker(self.end_marker_qn))

    @classmethod
    def for_rack(cls, rack: ChannelRackState) -> ArrangementState:
        require_32_field_channel_rack_state(rack)
        state = cls(rack.pattern.pattern_id)
        state.validate(rack)
        return state

    def validate(self, rack: ChannelRackState) -> None:
        try:
            require_32_field_channel_rack_state(rack)
        except (TypeError, ValueError) as exc:
            raise ArrangementError("invalid_pattern_state") from exc
        if rack.pattern.pattern_id != self.pattern_id:
            raise ArrangementError("unknown_pattern_id")
        ids = {c.channel_id for c in rack.channels}
        if len(ids) != len(rack.channels):
            raise ArrangementError("duplicate_channel_id")
        if any(t.channel_id not in ids for t in rack.pattern.triggers):
            raise ArrangementError("unknown_trigger_channel_id")
        if any(c not in ids for c, _ in self.disabled_track_blocks):
            raise ArrangementError("unknown_channel_id")

    def membership(self, channel_id: str, rack: ChannelRackState) -> str:
        self.validate(rack)
        if not isinstance(channel_id, str) or channel_id not in {
            c.channel_id for c in rack.channels
        }:
            raise ArrangementError("unknown_channel_id")
        return _MEMBERSHIP.get(channel_id, "unmapped")

    def groups(self, rack: ChannelRackState) -> dict[str, tuple[str, ...]]:
        self.validate(rack)
        ids = {c.channel_id for c in rack.channels}
        return {
            g: tuple(c for c in channels if c in ids)
            for g, channels in PRESENTATION_GROUPS.items()
        }

    def membership_status(self, rack: ChannelRackState) -> str:
        self.validate(rack)
        populated = {c.channel_id for c in rack.channels if c.sample_path}
        populated.update(t.channel_id for t in rack.pattern.triggers)
        return "migration_required" if populated - _MEMBERSHIP.keys() else "resolved"

    def block_status(self, index: int, tempo_map: TempoMap) -> str:
        start = _block(index) * ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES
        # Compare in TempoMap's musical coordinates to avoid admitting/rejecting
        # a sub-frame boundary due to frame rounding. No second tempo formula.
        horizon = tempo_map.frame_to_quarter_note(600 * tempo_map.sample_rate)
        return "eligible" if start < horizon else "out_of_current_horizon"

    def _require_horizon(self, index: int, tempo_map: TempoMap) -> None:
        if self.block_status(index, tempo_map) != "eligible":
            raise ArrangementError("out_of_current_horizon")

    def set_block(
        self, index: int, enabled: bool, tempo_map: TempoMap
    ) -> ArrangementState:
        self._require_horizon(index, tempo_map)
        return replace(
            self, disabled_blocks=_toggle(self.disabled_blocks, index, enabled)
        )

    def set_group(
        self, group_id: str, index: int, enabled: bool, tempo_map: TempoMap
    ) -> ArrangementState:
        _group(group_id)
        self._require_horizon(index, tempo_map)
        return replace(
            self,
            disabled_group_blocks=_toggle(
                self.disabled_group_blocks, (group_id, index), enabled
            ),
        )

    def set_track(
        self,
        channel_id: str,
        index: int,
        enabled: bool,
        rack: ChannelRackState,
        tempo_map: TempoMap,
    ) -> ArrangementState:
        if self.membership(channel_id, rack) == "unmapped":
            raise ArrangementError("migration_required")
        self._require_horizon(index, tempo_map)
        return replace(
            self,
            disabled_track_blocks=_toggle(
                self.disabled_track_blocks, (channel_id, index), enabled
            ),
        )

    def set_end_marker(self, quarter_note: Fraction | None) -> ArrangementState:
        return replace(self, end_marker_qn=_snapped_marker(quarter_note))

    def effective(
        self, channel_id: str, index: int, rack: ChannelRackState, tempo_map: TempoMap
    ) -> bool | str:
        group = self.membership(channel_id, rack)
        self._require_horizon(index, tempo_map)
        if group == "unmapped":
            return "unresolved"
        return (
            index not in self.disabled_blocks
            and (group, index) not in self.disabled_group_blocks
            and (channel_id, index) not in self.disabled_track_blocks
        )

    def render_eligible(self, rack: ChannelRackState, tempo_map: TempoMap) -> bool:
        try:
            self.validate(rack)
            return (
                self.end_marker_qn is not None
                and self.end_marker_qn
                <= tempo_map.frame_to_quarter_note(600 * tempo_map.sample_rate)
                and self.membership_status(rack) == "resolved"
            )
        except (TypeError, ValueError, OverflowError):
            return False

    def plan_block(
        self,
        index: int,
        rack: ChannelRackState,
        tempo_map: TempoMap,
        *,
        block_start_engine_frame: int,
    ) -> tuple[ScheduledTrigger, ...]:
        """Pure event projection; caller owns PCM, engine lifecycle and I/O."""
        self.validate(rack)
        self._require_horizon(index, tempo_map)
        if self.membership_status(rack) != "resolved":
            raise ArrangementError("migration_required")
        if self.end_marker_qn is not None and not self.render_eligible(rack, tempo_map):
            raise ArrangementError("end_marker_out_of_range")
        start = index * ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES
        cycles = plan_arrangement_block(
            pattern=rack.pattern,
            channels_by_id={c.channel_id: c for c in rack.channels},
            tempo_map=tempo_map,
            block_start_quarter=start,
            block_start_engine_frame=block_start_engine_frame,
        )
        planned = []
        for cycle_index, events in enumerate(cycles):
            for event in events:
                position = (
                    start + cycle_index * CYCLE_LENGTH_QUARTER_NOTES + event.position
                )
                if self.end_marker_qn is not None and position >= self.end_marker_qn:
                    continue
                if self.effective(event.channel_id, index, rack, tempo_map) is True:
                    planned.append(event)
        return tuple(sorted(planned, key=lambda e: (e.engine_frame, e.channel_id)))

    def to_payload(self) -> dict:
        return {
            "schema_version": 1,
            "pattern_id": self.pattern_id,
            "disabled_blocks": sorted(self.disabled_blocks),
            "disabled_group_blocks": [
                {"group_id": g, "block_index": i}
                for g, i in sorted(self.disabled_group_blocks)
            ],
            "disabled_track_blocks": [
                {"channel_id": c, "block_index": i}
                for c, i in sorted(self.disabled_track_blocks)
            ],
            "end_marker_qn": None
            if self.end_marker_qn is None
            else str(self.end_marker_qn),
        }

    @classmethod
    def from_payload(cls, payload: object, rack: ChannelRackState) -> ArrangementState:
        if not isinstance(payload, dict) or set(payload) != _KEYS:
            raise ArrangementError("corrupt_arrangement_payload")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            raise ArrangementError("unsupported_arrangement_schema")

        def masks(key: str, identity_key: str | None = None) -> frozenset:
            raw = payload[key]
            if type(raw) is not list:
                raise ArrangementError("corrupt_mask_payload")
            values = []
            for entry in raw:
                if identity_key is None:
                    values.append(_block(entry))
                else:
                    if not isinstance(entry, dict) or set(entry) != {
                        identity_key,
                        "block_index",
                    }:
                        raise ArrangementError("corrupt_mask_payload")
                    identity = entry[identity_key]
                    if not isinstance(identity, str) or not identity:
                        raise ArrangementError("invalid_mask_identity")
                    values.append((identity, _block(entry["block_index"])))
            if len(set(values)) != len(values):
                raise ArrangementError("duplicate_mask_entry")
            return frozenset(values)

        marker = payload["end_marker_qn"]
        if marker is not None:
            if type(marker) is not str:
                raise ArrangementError("invalid_end_marker")
            try:
                marker = _snapped_marker(Fraction(marker))
            except (ValueError, ZeroDivisionError) as exc:
                raise ArrangementError("invalid_end_marker") from exc
        state = cls(
            payload["pattern_id"],
            masks("disabled_blocks"),
            masks("disabled_group_blocks", "group_id"),
            masks("disabled_track_blocks", "channel_id"),
            marker,
        )
        state.validate(rack)
        return state
