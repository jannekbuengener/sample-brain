"""Activity segmentation with idle / listening contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .correlate import CorrelatedAction
from .normalize import NormalizedEvent
from .rules import (
    ARRANGEMENT_LIKE_SURFACES,
    EDIT_LIKE_SURFACES,
    IDLE_QUIET_NS,
    SEGMENT_MERGE_GAP_NS,
)

# Align with recorder ActivityTracker.ACTIVE_EVENT_TYPES for idle quiet reset.
_FL_ACTIVITY_EVENT_TYPES = frozenset(
    {
        "FOCUS_SURFACE",
        "FOCUS_FORM",
        "HINT",
        "UNDO",
        "REFRESH",
        "DIRTY_MIXER",
        "DIRTY_CHANNEL",
        "FOCUS_PLUGIN",
    }
)


@dataclass
class ActivitySegment:
    segment_id: str
    session_id: str
    start_wall_ns: int
    end_wall_ns: int
    activity: str
    truth_level: str
    confidence: str
    surface: str | None = None
    action_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    props: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ns(self) -> int:
        return max(0, self.end_wall_ns - self.start_wall_ns)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration_ns"] = self.duration_ns
        return d


_INPUT_PREFIXES = ("click", "drag", "wheel", "key_command", "text_entry")


def _is_input_action(action_type: str) -> bool:
    return action_type.startswith(_INPUT_PREFIXES) or action_type in _INPUT_PREFIXES


def _activity_for_action(action: CorrelatedAction, *, playing: bool) -> str:
    """Map a correlated action to a V1 activity label.

    Interpreted activities (browse, audition, edit, arrangement) are always
    tagged with truth_level interpreted at segment emission — never claimed measured.
    """
    at = action.action_type
    surface = action.surface

    if at == "foreground_leave":
        return "background"
    if at.startswith("transport_play") or (at == "transport_play"):
        return "transport_listening"
    if at == "transport_stop":
        return "navigation"

    if at == "surface_focus":
        # Align focus labels with interaction activities so adjacent
        # focus+input merge into one segment (supports backtrack/path mining).
        if surface == "Playlist":
            return "arrangement"
        if surface == "PianoRoll":
            return "piano_roll_edit"
        if surface == "ChannelRack":
            return "channel_rack"
        if surface == "Plugin":
            return "plugin_interaction"
        if surface == "Mixer":
            return "mixer"
        if surface is None:
            return "unknown"
        return "navigation"

    if at == "plugin_focus":
        return "plugin_interaction"

    if at == "undo":
        if surface in ARRANGEMENT_LIKE_SURFACES:
            return "playlist_edit"
        if surface == "PianoRoll":
            return "piano_roll_edit"
        if surface == "ChannelRack":
            return "channel_rack"
        if surface == "Mixer":
            return "mixer"
        if surface == "Plugin" or surface in EDIT_LIKE_SURFACES:
            return "plugin_interaction"
        return "playlist_edit" if surface else "unknown"

    if _is_input_action(at):
        if surface in ARRANGEMENT_LIKE_SURFACES:
            return "playlist_edit"
        if surface == "PianoRoll":
            return "piano_roll_edit"
        if surface == "ChannelRack":
            return "channel_rack"
        if surface == "Mixer":
            return "mixer"
        if surface == "Plugin":
            return "plugin_interaction"
        if surface is None:
            # Blind spot: may be Browser — interpret as browse at low confidence.
            return "browse"
        return "unknown"

    return "unknown"


def _segment_truth_confidence(activity: str, actions: list[CorrelatedAction]) -> tuple[str, str]:
    """Segment truth_level: interpreted for workflow labels; confidence = min of members."""
    conf_rank = {"high": 3, "medium": 2, "low": 1}
    if not actions:
        return "interpreted", "low"
    min_conf = min(actions, key=lambda a: conf_rank.get(a.confidence, 0)).confidence
    # Idle/background/transport_listening can be measured from transport+quiet rules.
    if activity in ("idle", "background", "transport_listening"):
        return "correlated", min_conf
    if activity in ("browse", "audition", "edit", "arrangement", "playlist_edit", "piano_roll_edit",
                    "channel_rack", "mixer", "plugin_interaction", "navigation", "unknown"):
        # Workflow meaning is interpreted even when inputs are measured.
        return "interpreted", min_conf
    return "interpreted", min_conf


def build_segments(
    actions: list[CorrelatedAction],
    events: list[NormalizedEvent],
    *,
    session_id: str,
    session_start_ns: int,
    session_end_ns: int,
) -> list[ActivitySegment]:
    """Build activity segments including idle and listening gaps.

    Idle contract:
      no relevant input + no relevant FL state change + transport not active → idle
    Listening contract:
      transport playing + no mouse/keyboard → transport_listening (NOT idle)
    """
    if session_end_ns < session_start_ns:
        session_end_ns = session_start_ns

    raw_spans: list[dict[str, Any]] = []

    def playing_at(t: int) -> bool:
        state = False
        for ev in events:
            if ev.event_type != "TRANSPORT":
                continue
            if ev.t_wall_ns > t:
                break
            state = bool(ev.props.get("playing")) or str(ev.props.get("event", "")).upper() == "PLAY"
            if str(ev.props.get("event", "")).upper() == "STOP":
                state = False
        return state

    def foreground_at(t: int) -> bool:
        # Default True until proven otherwise (matches correlate default).
        state = True
        for ev in events:
            if ev.event_type != "FG":
                continue
            if ev.t_wall_ns > t:
                break
            state = bool(ev.props.get("fl_foreground")) or str(
                ev.props.get("event", "")
            ).upper() == "FL_FOREGROUND"
            if str(ev.props.get("event", "")).upper() == "FL_BACKGROUND":
                state = False
        return state

    def is_relevant(a: CorrelatedAction) -> bool:
        if a.action_type.startswith("foreground"):
            return True
        if a.action_type.startswith("transport"):
            return True
        if a.action_type in ("surface_focus", "plugin_focus", "undo", "redo"):
            return True
        return _is_input_action(a.action_type)

    def classify_gap(
        gap_start: int,
        gap_end: int,
        *,
        last_relevant_ns: int,
        prev_activity: str | None,
        prev_surface: str | None,
        trailing: bool = False,
    ) -> list[dict[str, Any]]:
        """Fill [gap_start, gap_end) with background / listening / idle / active-carry.

        Intervals between interactions that are longer than SEGMENT_MERGE_GAP_NS but
        shorter than IDLE_QUIET_NS still count as active production time (carry).
        Background always wins over listening/idle (mirrors recorder ActivityTracker).
        """
        if gap_end <= gap_start:
            return []
        # Split gap at FG / TRANSPORT boundaries and at the idle threshold after
        # last relevant input so active-carry does not swallow true idle.
        cuts = {gap_start, gap_end}
        idle_at = last_relevant_ns + IDLE_QUIET_NS
        if gap_start < idle_at < gap_end:
            cuts.add(idle_at)
        for ev in events:
            if gap_start < ev.t_wall_ns < gap_end and ev.event_type in ("FG", "TRANSPORT"):
                cuts.add(ev.t_wall_ns)
        points = sorted(cuts)
        out: list[dict[str, Any]] = []
        for a, b in zip(points, points[1:]):
            # State immediately after `a` (include event at exactly `a`).
            fg = foreground_at(a)
            play = playing_at(a)
            quiet = a >= idle_at
            if not fg:
                out.append(
                    {
                        "start": a,
                        "end": b,
                        "activity": "background",
                        "actions": [],
                        "surface": None,
                        "reasons": ["foreground_lost"],
                    }
                )
            elif play:
                out.append(
                    {
                        "start": a,
                        "end": b,
                        "activity": "transport_listening",
                        "actions": [],
                        "surface": None,
                        "reasons": [
                            "playback_without_input_trailing"
                            if trailing
                            else "playback_without_input"
                        ],
                    }
                )
            elif quiet:
                out.append(
                    {
                        "start": a,
                        "end": b,
                        "activity": "idle",
                        "actions": [],
                        "surface": None,
                        "reasons": ["trailing_idle" if trailing else "no_input_no_transport"],
                    }
                )
            elif prev_activity and prev_activity not in ("idle", "background"):
                # Active carry: dwell continues in the prior production context.
                out.append(
                    {
                        "start": a,
                        "end": b,
                        "activity": prev_activity,
                        "actions": [],
                        "surface": prev_surface,
                        "reasons": ["active_gap_carry"],
                    }
                )
            # else: no prior context — leave unclassified (no span)
        return out

    cursor = session_start_ns
    last_relevant_ns = session_start_ns
    prev_activity: str | None = None
    prev_surface: str | None = None

    # FL semantic activity (even without Windows input) resets the idle clock,
    # matching the recorder idle contract: idle requires no relevant FL state change.
    fl_activity_times = sorted(
        e.t_wall_ns for e in events if e.event_type in _FL_ACTIVITY_EVENT_TYPES
    )

    def bump_relevant_through(t: int) -> None:
        nonlocal last_relevant_ns
        for tw in fl_activity_times:
            if tw > t:
                break
            if tw >= last_relevant_ns:
                last_relevant_ns = tw

    relevant = [a for a in actions if is_relevant(a)]

    for action in relevant:
        bump_relevant_through(action.start_wall_ns)
        gap_start = cursor
        gap_end = action.start_wall_ns
        raw_spans.extend(
            classify_gap(
                gap_start,
                gap_end,
                last_relevant_ns=last_relevant_ns,
                prev_activity=prev_activity,
                prev_surface=prev_surface,
            )
        )

        act = _activity_for_action(action, playing=playing_at(action.start_wall_ns))
        if action.action_type == "foreground_leave":
            act = "background"
        raw_spans.append(
            {
                "start": action.start_wall_ns,
                "end": max(action.end_wall_ns, action.start_wall_ns),
                "activity": act,
                "actions": [action],
                "surface": action.surface,
                "reasons": list(action.reasons),
            }
        )
        cursor = max(cursor, action.end_wall_ns, action.start_wall_ns)
        if act != "background":
            prev_activity = act
            prev_surface = action.surface or prev_surface
        if is_relevant(action) and not action.action_type.startswith("transport"):
            if action.action_type != "foreground_leave":
                last_relevant_ns = action.start_wall_ns

    bump_relevant_through(session_end_ns)
    raw_spans.extend(
        classify_gap(
            cursor,
            session_end_ns,
            last_relevant_ns=last_relevant_ns,
            prev_activity=prev_activity,
            prev_surface=prev_surface,
            trailing=True,
        )
    )

    # Merge adjacent compatible spans (including active-carry into prior activity).
    merged: list[dict[str, Any]] = []
    for span in raw_spans:
        if not merged:
            merged.append(span)
            continue
        prev = merged[-1]
        gap = span["start"] - prev["end"]
        same = span["activity"] == prev["activity"]
        if same and gap <= SEGMENT_MERGE_GAP_NS:
            prev["end"] = max(prev["end"], span["end"])
            prev["actions"].extend(span["actions"])
            prev["reasons"] = list(dict.fromkeys(prev["reasons"] + span["reasons"]))
            if span["surface"]:
                prev["surface"] = span["surface"]
        elif same and gap == 0:
            prev["end"] = max(prev["end"], span["end"])
            prev["actions"].extend(span["actions"])
            prev["reasons"] = list(dict.fromkeys(prev["reasons"] + span["reasons"]))
            if span["surface"]:
                prev["surface"] = span["surface"]
        else:
            if gap > 0 and gap <= SEGMENT_MERGE_GAP_NS and prev["activity"] not in ("idle", "background"):
                prev["end"] = span["start"]
            merged.append(span)

    segments: list[ActivitySegment] = []
    for i, span in enumerate(merged, start=1):
        acts: list[CorrelatedAction] = span["actions"]
        truth, conf = _segment_truth_confidence(span["activity"], acts)
        if span["activity"] in ("idle", "transport_listening") and not acts:
            conf = "high"
            truth = "correlated"
        segments.append(
            ActivitySegment(
                segment_id=f"s{i:05d}",
                session_id=session_id,
                start_wall_ns=int(span["start"]),
                end_wall_ns=int(span["end"]),
                activity=span["activity"],
                truth_level=truth,
                confidence=conf,
                surface=span.get("surface"),
                action_ids=[a.action_id for a in acts],
                reasons=list(span["reasons"]),
                props={"sb_context": _sb_from_activity(span["activity"])},
            )
        )
    return segments


def _sb_from_activity(activity: str) -> str | None:
    if activity in ("edit", "piano_roll_edit", "channel_rack", "plugin_interaction"):
        return "edit"
    if activity in ("arrangement", "playlist_edit"):
        return "arrangement"
    return None
