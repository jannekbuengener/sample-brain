"""Tests for #1321 FL workflow zero-touch recorder (schema/spool/session/privacy)."""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "tools" / "fl_workflow_recorder"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from fl_workflow_recorder.paths import ObserverPaths  # noqa: E402
from fl_workflow_recorder.privacy import sanitize_event  # noqa: E402
from fl_workflow_recorder.retention import apply_retention, retention_cutoff_wall_ns  # noqa: E402
from fl_workflow_recorder.sessions import ActivityTracker, SessionManager  # noqa: E402
from fl_workflow_recorder.spool_ingest import SpoolIngestor  # noqa: E402
from fl_workflow_recorder.store import WorkflowStore  # noqa: E402
from fl_workflow_recorder import SCHEMA_VERSION  # noqa: E402


def _evt(
    *,
    source: str,
    seq: int,
    etype: str,
    props: dict | None = None,
    wall: int | None = None,
) -> dict:
    wall_ns = wall if wall is not None else time.time_ns()
    return {
        "schema": "sb.fl_workflow_recorder.event.v1",
        "seq": seq,
        "t_mono_ns": wall_ns - 10,
        "t_wall_ns": wall_ns,
        "t_utc": "2026-01-01T00:00:00.000Z",
        "source": source,
        "type": etype,
        "props": props or {},
    }


@pytest.fixture
def observer_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ObserverPaths:
    root = tmp_path / "workflow-observer"
    monkeypatch.setenv("SAMPLE_BRAIN_WORKFLOW_OBSERVER_DIR", str(root))
    paths = ObserverPaths(root)
    paths.ensure()
    return paths


# ---------------------------------------------------------------------------
# Schema / storage
# ---------------------------------------------------------------------------


def test_db_bootstrap_and_schema_version(observer_root: ObserverPaths) -> None:
    store = WorkflowStore(observer_root.db)
    assert store.schema_version() == SCHEMA_VERSION
    store.close()
    # reopen existing
    store2 = WorkflowStore(observer_root.db)
    assert store2.schema_version() == SCHEMA_VERSION
    store2.close()


def test_event_insert_ordering_and_duplicate_prevention(observer_root: ObserverPaths) -> None:
    store = WorkflowStore(observer_root.db)
    sid = str(uuid.uuid4())
    store.create_session(sid)
    w0 = 1_000_000_000
    e1 = sanitize_event(_evt(source="fl", seq=1, etype="TRANSPORT", props={"playing": True}, wall=w0))
    e2 = sanitize_event(_evt(source="fl", seq=2, etype="FOCUS_SURFACE", props={"surface": "Playlist"}, wall=w0 + 1))
    assert e1 and e2
    assert store.insert_event(sid, e1) is True
    assert store.insert_event(sid, e2) is True
    assert store.insert_event(sid, e1) is False  # duplicate
    rows = store.connect().execute(
        "SELECT source_seq, event_type FROM events WHERE session_id=? ORDER BY t_wall_ns, id",
        (sid,),
    ).fetchall()
    assert [r["event_type"] for r in rows] == ["TRANSPORT", "FOCUS_SURFACE"]
    sess = store.get_session(sid)
    assert sess["fl_event_count"] == 2
    store.close()


def test_malformed_payload_rejected(observer_root: ObserverPaths) -> None:
    assert sanitize_event({"source": "fl", "type": "TRANSPORT"}) is None  # missing times
    assert sanitize_event("not-a-dict") is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Spool ingest
# ---------------------------------------------------------------------------


def test_incremental_ingest_partial_line_malformed_and_replay(observer_root: ObserverPaths) -> None:
    store = WorkflowStore(observer_root.db)
    sid = str(uuid.uuid4())
    store.create_session(sid)
    ing = SpoolIngestor(store)
    spool = observer_root.fl_spool

    e1 = _evt(source="fl", seq=1, etype="HINT", props={"text": "Brush"}, wall=100)
    e2 = _evt(source="fl", seq=2, etype="UNDO", props={"undo_count": 1}, wall=200)
    spool.write_text(
        json.dumps(e1) + "\n" + "{not-json\n" + json.dumps(e2) + "\n" + '{"seq":3,"source":"fl"',
        encoding="utf-8",
    )
    # last line incomplete (no newline)
    r1 = ing.ingest_file(spool, spool_name="fl-events.jsonl", session_id=sid)
    assert r1.inserted == 2
    assert r1.quarantined == 1
    assert r1.partial_tail is True

    # complete the partial line + duplicate replay of earlier content
    with spool.open("ab") as fh:
        fh.write(b',"type":"TRANSPORT","t_wall_ns":300,"props":{"playing":false}}\n')
    r2 = ing.ingest_file(spool, spool_name="fl-events.jsonl", session_id=sid)
    assert r2.inserted == 1
    # Re-ingest same file from cursor end — no new rows
    r3 = ing.ingest_file(spool, spool_name="fl-events.jsonl", session_id=sid)
    assert r3.inserted == 0

    # Full file rewrite replay with same events → duplicates ignored via UNIQUE
    spool.write_text(json.dumps(e1) + "\n" + json.dumps(e2) + "\n", encoding="utf-8")
    store.set_cursor("fl-events.jsonl", 0)
    r4 = ing.ingest_file(spool, spool_name="fl-events.jsonl", session_id=sid)
    assert r4.duplicates >= 2
    assert store.connect().execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"] == 3
    store.close()


def test_spool_reclaim_only_when_fully_ingested(observer_root: ObserverPaths) -> None:
    """Fully ingested spool may be archived; concurrent-safe path requires EOF cursor."""
    store = WorkflowStore(observer_root.db)
    sid = str(uuid.uuid4())
    store.create_session(sid)
    ing = SpoolIngestor(store)
    spool = observer_root.win_spool
    lines = [
        json.dumps(_evt(source="win", seq=i, etype="CLICK", props={"button": "left", "phase": "down"}, wall=i))
        for i in range(1, 6)
    ]
    body = "\n".join(lines) + "\n"
    spool.write_text(body, encoding="utf-8")
    # Without rotate: file retained, cursor advanced.
    r = ing.ingest_file(
        spool,
        spool_name="windows-events.jsonl",
        session_id=sid,
        rotate_after_commit=False,
    )
    assert r.inserted == 5
    assert spool.stat().st_size > 0
    # With rotate after full ingest: reclaim empties active file.
    r2 = ing.ingest_file(
        spool,
        spool_name="windows-events.jsonl",
        session_id=sid,
        rotate_after_commit=True,
        rotate_keep_bytes=0,
    )
    assert r2.inserted == 0
    assert spool.stat().st_size == 0
    assert store.get_cursor("windows-events.jsonl") == 0
    store.close()


def test_quarantine_excerpt_is_redacted(observer_root: ObserverPaths) -> None:
    store = WorkflowStore(observer_root.db)
    sid = str(uuid.uuid4())
    store.create_session(sid)
    ing = SpoolIngestor(store)
    spool = observer_root.fl_spool
    secret = json.dumps(
        {"source": "win", "seq": 1, "type": "CLIPBOARD", "t_wall_ns": 1, "props": {"clipboard": "SECRET"}}
    )
    spool.write_text(secret + "\n", encoding="utf-8")
    ing.ingest_file(spool, spool_name="fl-events.jsonl", session_id=sid)
    row = store.connect().execute("SELECT raw_excerpt, reason FROM spool_quarantine").fetchone()
    assert row is not None
    assert "SECRET" not in row["raw_excerpt"]
    assert "redacted=true" in row["raw_excerpt"]
    store.close()


def test_missing_spool_file_ok(observer_root: ObserverPaths) -> None:
    store = WorkflowStore(observer_root.db)
    sid = str(uuid.uuid4())
    store.create_session(sid)
    ing = SpoolIngestor(store)
    r = ing.ingest_file(
        observer_root.fl_spool,
        spool_name="fl-events.jsonl",
        session_id=sid,
    )
    assert r.inserted == 0
    store.close()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def test_session_focus_leave_does_not_split(observer_root: ObserverPaths) -> None:
    store = WorkflowStore(observer_root.db)
    mgr = SessionManager(store)
    sid1 = mgr.ensure_session(fl_alive=True, fl_pid=42)
    assert sid1
    # focus leave is not a session close
    mgr.activity.fl_foreground = False
    mgr.tick(fl_alive=True)
    sid2 = mgr.ensure_session(fl_alive=True, fl_pid=42)
    assert sid2 == sid1
    store.close()


def test_fl_exit_closes_session(observer_root: ObserverPaths) -> None:
    store = WorkflowStore(observer_root.db)
    mgr = SessionManager(store)
    sid = mgr.ensure_session(fl_alive=True, fl_pid=7)
    assert sid
    mgr.ensure_session(fl_alive=False, fl_pid=None)
    row = store.get_session(sid)
    assert row["status"] == "closed"
    assert row["close_reason"] == "fl_exit"
    store.close()


def test_stale_open_session_recovery(observer_root: ObserverPaths) -> None:
    store = WorkflowStore(observer_root.db)
    old = str(uuid.uuid4())
    store.create_session(old, fl_pid=1, started_at_wall_ns=1)
    # No events; FL not alive → recover
    mgr = SessionManager(store, stale_grace_ns=0)
    recovered = mgr.recover_stale_on_startup(fl_alive=False, fl_pid=None)
    assert old in recovered
    row = store.get_session(old)
    assert row["status"] == "recovered"
    store.close()


def test_recorder_restart_continues_matching_fl_pid(observer_root: ObserverPaths) -> None:
    store = WorkflowStore(observer_root.db)
    sid = str(uuid.uuid4())
    store.create_session(sid, fl_pid=99)
    store.update_session_meta(
        sid,
        durations={
            "active_duration_ns": 111,
            "listening_duration_ns": 222,
            "idle_duration_ns": 333,
        },
    )
    mgr = SessionManager(store)
    recovered = mgr.recover_stale_on_startup(fl_alive=True, fl_pid=99)
    assert recovered == []
    assert mgr.current_session_id == sid
    assert mgr.activity.active_ns == 111
    assert mgr.activity.listening_ns == 222
    assert mgr.activity.idle_ns == 333
    store.close()


def test_pid_mismatch_recovers_old_session(observer_root: ObserverPaths) -> None:
    store = WorkflowStore(observer_root.db)
    old = str(uuid.uuid4())
    store.create_session(old, fl_pid=11)
    mgr = SessionManager(store, stale_grace_ns=0)
    recovered = mgr.recover_stale_on_startup(fl_alive=True, fl_pid=99)
    assert old in recovered
    assert mgr.current_session_id is None
    store.close()


def test_numpad_redaction_present_in_windows_capture() -> None:
    src = (
        ROOT / "tools" / "fl_workflow_recorder" / "fl_workflow_recorder" / "windows_capture.py"
    ).read_text(encoding="utf-8")
    assert "0x60 <= vk <= 0x69" in src
    assert "CallNextHookEx.argtypes" in src


def test_activity_listening_not_idle_while_playing(observer_root: ObserverPaths) -> None:
    tracker = ActivityTracker()
    now = time.time_ns()
    tracker.fl_foreground = True
    tracker.note_event("TRANSPORT", {"playing": True, "event": "PLAY"}, now)
    # First tick arms the clock; second accumulates listening (no recent input).
    assert tracker.tick(now, fl_alive=True) == "listening"
    kind = tracker.tick(now + 180_000_000_000, fl_alive=True)
    assert kind == "listening"
    assert tracker.listening_ns > 0


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------


def test_text_entry_strips_character_values() -> None:
    raw = _evt(
        source="win",
        seq=1,
        etype="TEXT_ENTRY",
        props={"redacted": True, "char": "x", "character": "y", "mods": {"ctrl": False}},
    )
    clean = sanitize_event(raw)
    assert clean is not None
    assert clean["props"].get("redacted") is True
    assert "char" not in clean["props"]
    assert "character" not in clean["props"]


def test_path_like_props_redacted() -> None:
    raw = _evt(
        source="fl",
        seq=1,
        etype="FOCUS_FORM",
        props={"caption": r"C:\Users\secret\song.flp", "form_id": 1},
    )
    clean = sanitize_event(raw)
    assert clean is not None
    assert clean["props"]["caption"] == "[redacted_path_like]"


def test_disallowed_event_types_dropped() -> None:
    raw = _evt(source="win", seq=1, etype="CLIPBOARD", props={"text": "secret"})
    assert sanitize_event(raw) is None


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def test_retention_skips_open_session(observer_root: ObserverPaths) -> None:
    store = WorkflowStore(observer_root.db)
    open_id = str(uuid.uuid4())
    old_id = str(uuid.uuid4())
    store.create_session(open_id)
    store.create_session(old_id, started_at_wall_ns=1)
    store.close_session(old_id, close_reason="normal", ended_at_wall_ns=2)
    e = sanitize_event(_evt(source="fl", seq=1, etype="HINT", props={"text": "x"}, wall=2))
    assert e
    store.insert_event(old_id, e)
    # Cutoff after old session end
    stats = apply_retention(store, days=0, keep_session_ids=[open_id])
    # days=0 → cutoff ≈ now; old closed session eligible
    assert stats["deleted_sessions"] >= 1
    assert store.get_session(open_id) is not None
    assert store.get_session(open_id)["status"] == "open"
    store.close()


def test_retention_cutoff_helper() -> None:
    now = 1_000_000_000_000
    cut = retention_cutoff_wall_ns(90, now=now)
    assert cut < now


# ---------------------------------------------------------------------------
# Package / install layout
# ---------------------------------------------------------------------------


def test_install_layout_present() -> None:
    base = ROOT / "tools" / "fl_workflow_recorder"
    assert (base / "SBWorkflowObserver" / "device_SBWorkflowObserver.py").is_file()
    assert (base / "install.ps1").is_file()
    assert (base / "install_autostart.ps1").is_file()
    assert (base / "uninstall_autostart.ps1").is_file()
    assert (base / "fl_workflow_recorder" / "service.py").is_file()
    install = (base / "install.ps1").read_text(encoding="utf-8")
    assert "SBWorkflowSignalProbe" in install
    assert "device_SBWorkflowSignalProbe.py" in install
    device = (base / "SBWorkflowObserver" / "device_SBWorkflowObserver.py").read_text(
        encoding="utf-8"
    )
    assert "selectTool(" not in device
    assert "Never calls playlist.selectTool" in device
    assert "workflow-observer" in device
    assert "fl-events.jsonl" in device


def test_docs_contract_present() -> None:
    doc = ROOT / "docs" / "rnd" / "FL_WORKFLOW_RECORDER_1321.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "FL_WORKFLOW_ZERO_TOUCH_RECORDER_READY" in text
    assert "workflow.sqlite3" in text


def test_artifact_policy_mentions_workflow_observer() -> None:
    policy = (ROOT / "docs" / "DATA_AND_ARTIFACT_POLICY.md").read_text(encoding="utf-8")
    assert "workflow-observer" in policy
    assert "SAMPLE_BRAIN_WORKFLOW_OBSERVER_DIR" in policy


def test_midi_health_fail_soft() -> None:
    from fl_workflow_recorder.midi_health import probe_midi_ports

    h = probe_midi_ports()
    # Must not raise; structure always present.
    assert hasattr(h, "available")
    assert hasattr(h, "observer_in_present")


def test_service_runs_briefly_without_fl(observer_root: ObserverPaths, monkeypatch: pytest.MonkeyPatch) -> None:
    from fl_workflow_recorder.fl_process import FlProcessInfo
    from fl_workflow_recorder.service import RecorderService

    monkeypatch.setattr(
        "fl_workflow_recorder.service.find_fl_process",
        lambda: FlProcessInfo(alive=False),
    )
    svc = RecorderService(
        observer_root,
        enable_windows_capture=False,
        poll_interval_sec=0.05,
    )

    def stop_soon():
        time.sleep(0.2)
        svc._stop.set()

    import threading

    threading.Thread(target=stop_soon, daemon=True).start()
    rc = svc.run()
    assert rc == 0
    assert observer_root.health.exists()
    health = json.loads(observer_root.health.read_text(encoding="utf-8"))
    assert "pid" in health
    assert health.get("fl_detected") is False
    assert observer_root.db.exists()
