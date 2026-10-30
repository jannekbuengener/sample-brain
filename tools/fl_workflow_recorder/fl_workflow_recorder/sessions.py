"""Deterministic FL session lifecycle (zero-touch)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from .store import WorkflowStore

ActivityKind = Literal["active", "listening", "idle", "background"]

# Focus leave does not split sessions. Stale open sessions recovered after grace.
DEFAULT_STALE_GRACE_NS = 90 * 1_000_000_000  # 90s without FL process + no events
DEFAULT_IDLE_AFTER_NS = 120 * 1_000_000_000  # 2 min quiet → idle (unless playing)
ACTIVE_EVENT_TYPES = frozenset(
    {
        "CLICK",
        "DRAG",
        "WHEEL",
        "KEY_CMD",
        "TEXT_ENTRY",
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
class ActivityTracker:
    active_ns: int = 0
    listening_ns: int = 0
    idle_ns: int = 0
    last_tick_wall_ns: int | None = None
    last_input_wall_ns: int | None = None
    playing: bool = False
    fl_foreground: bool = False
    current: ActivityKind = "idle"

    def note_event(self, event_type: str, props: dict, t_wall_ns: int) -> None:
        if event_type == "TRANSPORT":
            self.playing = bool(props.get("playing")) or str(props.get("event", "")).upper() == "PLAY"
            if str(props.get("event", "")).upper() == "STOP":
                self.playing = False
        if event_type == "FG":
            self.fl_foreground = bool(props.get("fl_foreground")) or str(
                props.get("event", "")
            ).upper() == "FL_FOREGROUND"
            if str(props.get("event", "")).upper() == "FL_BACKGROUND":
                self.fl_foreground = False
        if event_type in ACTIVE_EVENT_TYPES:
            self.last_input_wall_ns = t_wall_ns

    def tick(self, now_wall_ns: int, *, fl_alive: bool) -> ActivityKind:
        if self.last_tick_wall_ns is None:
            self.last_tick_wall_ns = now_wall_ns
            self.current = self._classify(now_wall_ns, fl_alive=fl_alive)
            return self.current
        dt = max(0, now_wall_ns - self.last_tick_wall_ns)
        kind = self._classify(now_wall_ns, fl_alive=fl_alive)
        if kind == "active":
            self.active_ns += dt
        elif kind == "listening":
            self.listening_ns += dt
        elif kind == "idle":
            self.idle_ns += dt
        # background time is not counted as active/listening/idle production
        self.last_tick_wall_ns = now_wall_ns
        self.current = kind
        return kind

    def _classify(self, now_wall_ns: int, *, fl_alive: bool) -> ActivityKind:
        if not fl_alive:
            return "idle"
        if not self.fl_foreground:
            return "background"
        last_in = self.last_input_wall_ns
        recent = last_in is not None and (now_wall_ns - last_in) < DEFAULT_IDLE_AFTER_NS
        if recent:
            return "active"
        if self.playing:
            return "listening"
        return "idle"

    def durations(self) -> dict[str, int]:
        return {
            "active_duration_ns": self.active_ns,
            "listening_duration_ns": self.listening_ns,
            "idle_duration_ns": self.idle_ns,
        }


@dataclass
class SessionManager:
    store: WorkflowStore
    stale_grace_ns: int = DEFAULT_STALE_GRACE_NS
    activity: ActivityTracker = field(default_factory=ActivityTracker)
    current_session_id: str | None = None

    def recover_stale_on_startup(self, *, fl_alive: bool, fl_pid: int | None) -> list[str]:
        """Close stale open sessions. If FL still alive with matching pid, keep one open."""
        recovered: list[str] = []
        now = time.time_ns()
        open_rows = self.store.open_sessions()
        keep_id = None
        if fl_alive and fl_pid is not None:
            for row in open_rows:
                if row["fl_pid"] is not None and int(row["fl_pid"]) == int(fl_pid):
                    keep_id = row["id"]
                    break
            # If FL alive but no pid match, still prefer newest open session to continue.
            if keep_id is None and open_rows:
                keep_id = open_rows[-1]["id"]
                self.store.update_session_meta(keep_id, fl_pid=fl_pid)

        for row in open_rows:
            sid = row["id"]
            if sid == keep_id:
                self.current_session_id = sid
                continue
            last_ev = self.store.last_event_wall_ns(sid) or int(row["started_at_wall_ns"])
            # If FL is gone, or session is old without keep — recover.
            if not fl_alive or (now - last_ev) > self.stale_grace_ns:
                self.store.close_session(
                    sid,
                    close_reason="stale_recovery",
                    status="recovered",
                    ended_at_wall_ns=last_ev,
                    recovery_marker=1,
                )
                recovered.append(sid)
            else:
                # FL gone but within grace — still close as crash recovery.
                if not fl_alive:
                    self.store.close_session(
                        sid,
                        close_reason="fl_crash",
                        status="recovered",
                        ended_at_wall_ns=last_ev,
                        recovery_marker=1,
                    )
                    recovered.append(sid)
        return recovered

    def ensure_session(
        self,
        *,
        fl_alive: bool,
        fl_pid: int | None,
        fl_version: str | None = None,
        midi_api: str | None = None,
    ) -> str | None:
        if not fl_alive:
            if self.current_session_id:
                self.close_current(close_reason="fl_exit", status="closed")
            return None
        if self.current_session_id:
            open_row = self.store.get_session(self.current_session_id)
            if open_row and open_row["status"] == "open":
                self.store.update_session_meta(
                    self.current_session_id,
                    fl_version=fl_version,
                    midi_script_api_version=midi_api,
                    fl_pid=fl_pid,
                    durations=self.activity.durations(),
                )
                return self.current_session_id
        # Open new session.
        sid = str(uuid.uuid4())
        self.store.create_session(
            sid,
            fl_version=fl_version,
            midi_script_api_version=midi_api,
            fl_pid=fl_pid,
        )
        self.current_session_id = sid
        self.activity = ActivityTracker()
        return sid

    def close_current(
        self,
        *,
        close_reason: str,
        status: str = "closed",
        ended_at_wall_ns: int | None = None,
    ) -> None:
        if not self.current_session_id:
            return
        self.store.close_session(
            self.current_session_id,
            close_reason=close_reason,
            status=status,
            ended_at_wall_ns=ended_at_wall_ns,
            recovery_marker=1 if status == "recovered" else 0,
            durations=self.activity.durations(),
        )
        self.current_session_id = None

    def on_ingested_event(self, event: dict) -> None:
        self.activity.note_event(
            event["event_type"],
            event.get("props") or {},
            int(event["t_wall_ns"]),
        )

    def tick(self, *, fl_alive: bool) -> None:
        self.activity.tick(time.time_ns(), fl_alive=fl_alive)
        if self.current_session_id:
            self.store.update_session_meta(
                self.current_session_id,
                durations=self.activity.durations(),
            )
