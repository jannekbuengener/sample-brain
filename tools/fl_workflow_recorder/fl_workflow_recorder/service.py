"""Zero-touch recorder service loop."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

from .fl_process import find_fl_process
from .health import write_health
from .midi_health import probe_midi_ports
from .paths import ObserverPaths
from .privacy import sanitize_event
from .retention import apply_retention
from .sessions import SessionManager
from .spool_ingest import SpoolIngestor
from .store import WorkflowStore

logger = logging.getLogger("fl_workflow_recorder")


class RecorderService:
    def __init__(
        self,
        paths: ObserverPaths | None = None,
        *,
        enable_windows_capture: bool = True,
        poll_interval_sec: float = 0.5,
        retention_days: int = 90,
        spool_rotate_bytes: int = 8_000_000,
    ) -> None:
        self.paths = paths or ObserverPaths()
        self.enable_windows_capture = enable_windows_capture and sys.platform == "win32"
        self.poll_interval_sec = poll_interval_sec
        self.retention_days = retention_days
        self.spool_rotate_bytes = spool_rotate_bytes
        self._stop = threading.Event()
        self._store: WorkflowStore | None = None
        self._sessions: SessionManager | None = None
        self._ingest: SpoolIngestor | None = None
        self._capture = None
        self._last_fl_event_wall: int | None = None
        self._last_win_event_wall: int | None = None
        self._ingest_errors = 0
        self._fl_script_silent = True
        self._last_retention = 0.0

    def _setup_logging(self) -> None:
        self.paths.ensure()
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            handlers=[
                logging.FileHandler(self.paths.log_file, encoding="utf-8"),
            ],
        )

    def _write_pid(self) -> None:
        self.paths.pid_file.write_text(str(os.getpid()), encoding="utf-8")

    def _clear_pid(self) -> None:
        try:
            if self.paths.pid_file.exists():
                self.paths.pid_file.unlink()
        except OSError:
            pass

    def _emit_observer(self, event_type: str, props: dict | None = None) -> None:
        """Append observer lifecycle events into windows spool? Prefer dedicated observer lines via store."""
        assert self._store is not None and self._sessions is not None
        sid = self._sessions.current_session_id
        if not sid:
            return
        wall = time.time_ns()
        raw = {
            "source": "observer",
            "seq": int(wall % 1_000_000_000),
            "t_wall_ns": wall,
            "t_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "t_mono_ns": time.monotonic_ns(),
            "type": event_type,
            "props": props or {},
        }
        event = sanitize_event(raw)
        if event:
            self._store.insert_event(sid, event)

    def _read_fl_meta(self) -> tuple[str | None, str | None]:
        meta_path = self.paths.root / "fl-recorder-meta.json"
        if not meta_path.exists():
            # Probe-compatible fallback name used by device script.
            meta_path = self.paths.root / "fl-meta.json"
        if not meta_path.exists():
            return None, None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return (
                str(data["FL_VERSION"]) if data.get("FL_VERSION") is not None else None,
                str(data["MIDI_SCRIPT_API_VERSION"])
                if data.get("MIDI_SCRIPT_API_VERSION") is not None
                else None,
            )
        except (OSError, json.JSONDecodeError, KeyError):
            return None, None

    def _update_health(self, fl_info) -> None:
        assert self._store is not None and self._sessions is not None
        midi = probe_midi_ports()
        fl_ver, midi_api = self._read_fl_meta()
        payload = {
            "recorder_running": not self._stop.is_set(),
            "pid": os.getpid(),
            "db_path_status": "ok" if self.paths.db.exists() else "missing",
            "db_exists": self.paths.db.exists(),
            "fl_detected": bool(fl_info.alive),
            "fl_pid": fl_info.pid,
            "fl_version": fl_ver,
            "midi_script_api_version": midi_api,
            "fl_script_active": not self._fl_script_silent,
            "windows_observer_active": bool(self._capture is not None),
            "current_session_id": self._sessions.current_session_id,
            "last_fl_event_wall_ns": self._last_fl_event_wall,
            "last_win_event_wall_ns": self._last_win_event_wall,
            "ingest_errors": self._ingest_errors,
            "midi": {
                "available": midi.available,
                "observer_in_present": midi.observer_in_present,
                "observer_out_present": midi.observer_out_present,
                "input_count": midi.input_count,
                "output_count": midi.output_count,
                "detail": midi.detail,
            },
            "activity": self._sessions.activity.current,
            "root_kind": "localappdata_workflow_observer",
        }
        write_health(self.paths.health, payload)

    def _ingest_once(self) -> None:
        assert self._ingest is not None and self._sessions is not None
        sid = self._sessions.current_session_id
        if not sid:
            return
        try:
            on_ev = self._sessions.on_ingested_event
            fl_res = self._ingest.ingest_file(
                self.paths.fl_spool,
                spool_name="fl-events.jsonl",
                session_id=sid,
                rotate_after_commit=True,
                rotate_keep_bytes=self.spool_rotate_bytes,
                on_event=on_ev,
            )
            win_res = self._ingest.ingest_file(
                self.paths.win_spool,
                spool_name="windows-events.jsonl",
                session_id=sid,
                rotate_after_commit=True,
                rotate_keep_bytes=self.spool_rotate_bytes,
                on_event=on_ev,
            )
            if fl_res.inserted:
                self._fl_script_silent = False
                self._last_fl_event_wall = self._store.last_event_wall_ns(sid)  # type: ignore[union-attr]
            if win_res.inserted:
                self._last_win_event_wall = self._store.last_event_wall_ns(sid)  # type: ignore[union-attr]
            # Feed activity tracker from recent types via session counters only —
            # detailed note_event happens best-effort from last ingest by re-reading is heavy;
            # instead update FG/playing from health tick using capture + fl meta.
        except Exception:
            self._ingest_errors += 1
            logger.exception("ingest failed")

    def run(self) -> int:
        self._setup_logging()
        self.paths.ensure()
        self._write_pid()
        self._store = WorkflowStore(self.paths.db)
        self._store.connect()
        self._sessions = SessionManager(self._store)
        self._ingest = SpoolIngestor(self._store)

        fl0 = find_fl_process()
        self._sessions.recover_stale_on_startup(fl_alive=fl0.alive, fl_pid=fl0.pid)
        if fl0.alive:
            fl_ver, midi_api = self._read_fl_meta()
            self._sessions.ensure_session(
                fl_alive=True, fl_pid=fl0.pid, fl_version=fl_ver, midi_api=midi_api
            )

        if self.enable_windows_capture:
            try:
                from .windows_capture import WindowsCapture

                self._capture = WindowsCapture(self.paths.win_spool)
                self._capture.start()
            except Exception:
                logger.exception("windows capture failed to start; continuing without it")
                self._capture = None

        def _handle_stop(signum, frame):  # noqa: ARG001
            self._stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handle_stop)
            except Exception:
                pass

        logger.info("recorder started root=%s", self.paths.root)
        try:
            while not self._stop.is_set():
                fl = find_fl_process()
                fl_ver, midi_api = self._read_fl_meta()
                prev = self._sessions.current_session_id
                sid = self._sessions.ensure_session(
                    fl_alive=fl.alive,
                    fl_pid=fl.pid,
                    fl_version=fl_ver,
                    midi_api=midi_api,
                )
                if sid and sid != prev:
                    self._emit_observer("SESSION_OPEN", {"fl_pid": fl.pid})

                # Sync FG/playing hints into activity tracker.
                if self._capture is not None:
                    self._sessions.activity.fl_foreground = bool(self._capture.fl_foreground)
                    self._last_win_event_wall = self._capture.last_event_wall_ns or self._last_win_event_wall

                # Detect silence of FL script: no fl spool growth / no recent fl events.
                if self.paths.fl_spool.exists():
                    # Soft: if file mtime older than 30s while FL alive → silent warning in health.
                    age = time.time() - self.paths.fl_spool.stat().st_mtime
                    if fl.alive and age > 30 and self._last_fl_event_wall is None:
                        self._fl_script_silent = True

                self._ingest_once()
                self._sessions.tick(fl_alive=fl.alive)
                self._update_health(fl)

                if time.monotonic() - self._last_retention > 3600:
                    try:
                        apply_retention(
                            self._store,
                            days=self.retention_days,
                            keep_session_ids=[sid] if sid else [],
                        )
                    except Exception:
                        logger.exception("retention failed")
                    self._last_retention = time.monotonic()

                self._stop.wait(self.poll_interval_sec)
        finally:
            if self._sessions and self._sessions.current_session_id:
                # Leave session open so restart can continue; only close if FL gone.
                fl = find_fl_process()
                if not fl.alive:
                    self._sessions.close_current(close_reason="recorder_stop_fl_gone")
            if self._capture is not None:
                try:
                    self._capture.stop()
                except Exception:
                    pass
            try:
                self._update_health(find_fl_process())
            except Exception:
                pass
            self._clear_pid()
            if self._store:
                self._store.close()
            logger.info("recorder stopped")
        return 0


def run_service(root: Path | None = None, **kwargs) -> int:
    paths = ObserverPaths(root) if root is not None else ObserverPaths()
    return RecorderService(paths, **kwargs).run()
