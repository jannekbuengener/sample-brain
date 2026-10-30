"""Correlate measured events into inspectable producer actions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .normalize import NormalizedEvent
from .rules import (
    ARRANGEMENT_LIKE_SURFACES,
    CORRELATION_WINDOW_NS,
    EDIT_LIKE_SURFACES,
    SURFACE_CONTEXT_STALE_NS,
)


@dataclass
class CorrelatedAction:
    action_id: str
    session_id: str
    start_wall_ns: int
    end_wall_ns: int
    action_type: str
    surface: str | None
    truth_level: str  # measured | correlated | interpreted
    confidence: str  # high | medium | low
    evidence_event_ids: list[int] = field(default_factory=list)
    evidence_types: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _confidence(
    *,
    has_fl_surface: bool,
    has_win_input: bool,
    surface_known: bool,
    blind_spot: bool,
    semantic_hint: bool,
) -> str:
    """Deterministic confidence from explicit rule inputs (no free probabilities)."""
    if blind_spot and not semantic_hint:
        return "low"
    if has_fl_surface and has_win_input and surface_known:
        return "high"
    if has_fl_surface and surface_known and not has_win_input:
        return "high" if not blind_spot else "medium"
    if has_win_input and surface_known:
        return "medium"
    if has_win_input and not surface_known:
        return "low"
    return "low"


def _sb_context(surface: str | None) -> str | None:
    if surface in EDIT_LIKE_SURFACES:
        return "edit"
    if surface in ARRANGEMENT_LIKE_SURFACES:
        return "arrangement"
    return None


def correlate_actions(events: list[NormalizedEvent]) -> list[CorrelatedAction]:
    """Walk a session timeline and emit correlated actions.

    Cross-plane ordering uses raw t_wall_ns (wall-clock authority from #1320).
    Windows inputs inherit the most recent FOCUS_SURFACE/FOCUS_FORM until replaced
    or FL background. Soft staleness (SURFACE_CONTEXT_STALE_NS) lowers confidence.
    Nearby FL edit signals within CORRELATION_WINDOW_NS support correlation reasons.
    """
    actions: list[CorrelatedAction] = []
    surface: str | None = None
    surface_at: int | None = None
    playing = False
    fl_foreground = True
    prev_undo_pos: int | None = None
    prev_undo_count: int | None = None
    pending_drag: NormalizedEvent | None = None
    seq = 0

    # Index FL edit signals for lookahead/lookback correlation.
    fl_edit_times: list[tuple[int, NormalizedEvent]] = [
        (e.t_wall_ns, e)
        for e in events
        if e.source == "fl" and e.event_type in ("UNDO", "REFRESH", "DIRTY_MIXER", "DIRTY_CHANNEL", "HINT")
    ]

    def nearby_fl_edits(t: int) -> list[NormalizedEvent]:
        out = []
        for tw, ev in fl_edit_times:
            if abs(tw - t) <= CORRELATION_WINDOW_NS:
                out.append(ev)
        return out

    def emit(**kwargs: Any) -> None:
        nonlocal seq
        seq += 1
        aid = f"a{seq:05d}"
        actions.append(CorrelatedAction(action_id=aid, **kwargs))

    for ev in events:
        if ev.event_type == "FOCUS_SURFACE":
            surface = ev.surface
            surface_at = ev.t_wall_ns
            blind = surface is None
            conf = _confidence(
                has_fl_surface=True,
                has_win_input=False,
                surface_known=surface is not None,
                blind_spot=blind,
                semantic_hint=False,
            )
            reasons = ["measured_focus_surface"]
            if blind:
                reasons.append("blind_spot_surface_unknown")
            emit(
                session_id=ev.session_id,
                start_wall_ns=ev.t_wall_ns,
                end_wall_ns=ev.t_wall_ns,
                action_type="surface_focus",
                surface=surface,
                truth_level="measured",
                confidence=conf,
                evidence_event_ids=[ev.event_id],
                evidence_types=[ev.event_type],
                reasons=reasons,
                props={"sb_context": _sb_context(surface), **ev.props},
            )
            continue

        if ev.event_type == "FOCUS_FORM":
            # FOCUS_FORM is measured and often denser than FOCUS_SURFACE; refresh
            # context carry without emitting a separate navigation action each time.
            if ev.surface:
                surface = ev.surface
                surface_at = ev.t_wall_ns
            continue

        if ev.event_type == "FOCUS_PLUGIN":
            plugin_present = bool(ev.props.get("plugin_present"))
            # Empty plugin name on a non-plugin surface is focus *loss*, not interaction.
            # Recorder emits FOCUS_PLUGIN whenever the name changes, including → "".
            measured_surface = ev.surface or surface
            if not plugin_present and measured_surface and measured_surface != "Plugin":
                surface = measured_surface
                surface_at = ev.t_wall_ns
                continue
            surface = "Plugin"
            surface_at = ev.t_wall_ns
            conf = "medium" if plugin_present else "low"
            reasons = ["measured_plugin_focus"]
            if not plugin_present:
                reasons.append("blind_spot_plugin_identity")
            emit(
                session_id=ev.session_id,
                start_wall_ns=ev.t_wall_ns,
                end_wall_ns=ev.t_wall_ns,
                action_type="plugin_focus",
                surface="Plugin",
                truth_level="measured",
                confidence=conf,
                evidence_event_ids=[ev.event_id],
                evidence_types=[ev.event_type],
                reasons=reasons,
                props={"sb_context": "edit", **ev.props},
            )
            continue

        if ev.event_type == "TRANSPORT":
            playing = bool(ev.props.get("playing")) or str(ev.props.get("event", "")).upper() == "PLAY"
            if str(ev.props.get("event", "")).upper() == "STOP":
                playing = False
            emit(
                session_id=ev.session_id,
                start_wall_ns=ev.t_wall_ns,
                end_wall_ns=ev.t_wall_ns,
                action_type="transport_play" if playing else "transport_stop",
                surface=surface,
                truth_level="measured",
                confidence="high",
                evidence_event_ids=[ev.event_id],
                evidence_types=[ev.event_type],
                reasons=["measured_transport"],
                props={"playing": playing, "sb_context": _sb_context(surface)},
            )
            continue

        if ev.event_type == "FG":
            fl_foreground = bool(ev.props.get("fl_foreground")) or str(
                ev.props.get("event", "")
            ).upper() == "FL_FOREGROUND"
            if str(ev.props.get("event", "")).upper() == "FL_BACKGROUND":
                fl_foreground = False
                surface = None
                surface_at = None
            emit(
                session_id=ev.session_id,
                start_wall_ns=ev.t_wall_ns,
                end_wall_ns=ev.t_wall_ns,
                action_type="foreground_enter" if fl_foreground else "foreground_leave",
                surface=surface,
                truth_level="measured",
                confidence="high",
                evidence_event_ids=[ev.event_id],
                evidence_types=[ev.event_type],
                reasons=["measured_foreground"],
                props={"fl_foreground": fl_foreground},
            )
            continue

        if ev.event_type == "UNDO":
            # Recorder emits UNDO on any history-field change (init, edit growth,
            # undo, redo). Only emit producer undo/redo when undo_pos moves
            # relative to a prior observation.
            pos_raw = ev.props.get("undo_pos")
            count_raw = ev.props.get("undo_count")
            try:
                pos = int(pos_raw) if pos_raw is not None else None
            except (TypeError, ValueError):
                pos = None
            try:
                count = int(count_raw) if count_raw is not None else None
            except (TypeError, ValueError):
                count = None

            if prev_undo_pos is None:
                prev_undo_pos, prev_undo_count = pos, count
                continue

            action_type: str | None = None
            reasons_u: list[str] = []
            if pos is not None and prev_undo_pos is not None and pos < prev_undo_pos:
                action_type = "undo"
                reasons_u = ["undo_pos_decreased"]
            elif (
                pos is not None
                and prev_undo_pos is not None
                and pos > prev_undo_pos
                and count is not None
                and prev_undo_count is not None
                and count == prev_undo_count
            ):
                action_type = "redo"
                reasons_u = ["undo_pos_increased_same_count"]
            # else: history growth / unrelated field churn — not an undo action

            prev_undo_pos, prev_undo_count = (
                pos if pos is not None else prev_undo_pos,
                count if count is not None else prev_undo_count,
            )
            if action_type is None:
                continue
            emit(
                session_id=ev.session_id,
                start_wall_ns=ev.t_wall_ns,
                end_wall_ns=ev.t_wall_ns,
                action_type=action_type,
                surface=surface,
                truth_level="measured",
                confidence="high",
                evidence_event_ids=[ev.event_id],
                evidence_types=[ev.event_type],
                reasons=reasons_u,
                props={"sb_context": _sb_context(surface), **ev.props},
            )
            continue

        if ev.source == "win" and ev.event_type in ("CLICK", "DRAG", "WHEEL", "KEY_CMD", "TEXT_ENTRY"):
            # Preserve drag intervals: start is held until end (or duration_ms).
            if ev.event_type == "DRAG" and str(ev.props.get("phase", "")).lower() == "start":
                pending_drag = ev
                continue

            start_ns = ev.t_wall_ns
            end_ns = ev.t_wall_ns
            evid_extra: list[NormalizedEvent] = []
            if ev.event_type == "DRAG":
                phase = str(ev.props.get("phase", "")).lower()
                if phase == "end" and pending_drag is not None:
                    start_ns = pending_drag.t_wall_ns
                    evid_extra.append(pending_drag)
                    pending_drag = None
                elif phase == "end":
                    dur_ms = ev.props.get("duration_ms")
                    try:
                        if dur_ms is not None and int(dur_ms) > 0:
                            start_ns = ev.t_wall_ns - int(dur_ms) * 1_000_000
                    except (TypeError, ValueError):
                        pass

            effective_surface = surface if fl_foreground else None
            stale = (
                effective_surface is not None
                and surface_at is not None
                and (ev.t_wall_ns - surface_at) > SURFACE_CONTEXT_STALE_NS
            )
            nearby = nearby_fl_edits(ev.t_wall_ns)
            has_hint = any(
                n.event_type == "HINT" and n.props.get("hint_class") for n in nearby
            )
            has_edit_sig = any(
                n.event_type in ("UNDO", "REFRESH", "DIRTY_MIXER", "DIRTY_CHANNEL") for n in nearby
            )
            blind = effective_surface is None
            if effective_surface is None:
                reasons_bs = ["win_input_without_fl_surface", "blind_spot_browser_or_surface"]
            else:
                reasons_bs = []

            conf = _confidence(
                has_fl_surface=effective_surface is not None,
                has_win_input=True,
                surface_known=effective_surface is not None,
                blind_spot=blind,
                semantic_hint=has_hint or has_edit_sig,
            )
            if stale and conf == "high":
                conf = "medium"
            truth = "correlated" if effective_surface is not None else "interpreted"
            if effective_surface is None:
                conf = "low"

            action_map = {
                "CLICK": "click",
                "DRAG": "drag",
                "WHEEL": "wheel",
                "KEY_CMD": "key_command",
                "TEXT_ENTRY": "text_entry",
            }
            atype = action_map[ev.event_type]
            if effective_surface:
                atype = f"{atype}_in_{effective_surface.lower()}"

            reasons = ["win_input"]
            if effective_surface is not None:
                reasons.append("fl_surface_context")
            if stale:
                reasons.append("surface_context_stale")
            if has_hint:
                reasons.append("nearby_hint")
            if has_edit_sig:
                reasons.append("nearby_edit_signal")
            if end_ns > start_ns:
                reasons.append("interval_action")
            reasons.extend(reasons_bs)

            evid_ids = [e.event_id for e in evid_extra] + [ev.event_id] + [n.event_id for n in nearby]
            evid_types = [e.event_type for e in evid_extra] + [ev.event_type] + [
                n.event_type for n in nearby
            ]
            emit(
                session_id=ev.session_id,
                start_wall_ns=start_ns,
                end_wall_ns=end_ns,
                action_type=atype,
                surface=effective_surface,
                truth_level=truth,
                confidence=conf,
                evidence_event_ids=evid_ids,
                evidence_types=evid_types,
                reasons=reasons,
                props={
                    "sb_context": _sb_context(effective_surface),
                    "playing": playing,
                    "fl_foreground": fl_foreground,
                    **ev.props,
                },
            )
            continue

        # HINT / REFRESH / DIRTY_* are consumed via nearby_fl_edits correlation
        # windows — not emitted as standalone producer actions (avoids HINT spam).

    return actions
