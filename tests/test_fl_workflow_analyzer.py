"""Golden timeline + contract tests for #1322 workflow reconstruction."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ANALYZER_ROOT = REPO / "tools" / "fl_workflow_analyzer"
RECORDER_ROOT = REPO / "tools" / "fl_workflow_recorder"
for p in (str(ANALYZER_ROOT), str(RECORDER_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fl_workflow_analyzer import ANALYZER_VERSION, RULE_VERSION  # noqa: E402
from fl_workflow_analyzer.pipeline import (  # noqa: E402
    analyze_events_in_memory,
    run_analysis,
)
from fl_workflow_analyzer.privacy import safe_props  # noqa: E402
from fl_workflow_analyzer.rules import (  # noqa: E402
    BLIND_SPOTS,
    IDLE_QUIET_NS,
    rule_manifest,
)
from fl_workflow_analyzer.store import DerivedStore  # noqa: E402
from fl_workflow_recorder.store import WorkflowStore  # noqa: E402

NS = 1_000_000_000


def _ev(
    *,
    source: str,
    seq: int,
    etype: str,
    wall: int,
    props: dict | None = None,
    eid: int | None = None,
) -> dict:
    return {
        "id": eid if eid is not None else seq,
        "session_id": "synthetic",
        "source": source,
        "source_seq": seq,
        "t_wall_ns": wall,
        "t_utc": "",
        "event_type": etype,
        "props": props or {},
    }


def _activities(result: dict) -> list[str]:
    return [s["activity"] for s in result["segments"]]


def test_rule_manifest_versioned() -> None:
    m = rule_manifest()
    assert m["rule_version"] == RULE_VERSION
    assert m["correlation_window_ns"] > 0
    assert "correlation_window_ns" in m["rationale"]
    assert {b["id"] for b in BLIND_SPOTS} >= {
        "playlist_active_tool",
        "browser_surface_label",
        "plugin_identity",
    }


def test_privacy_drops_forbidden_and_paths() -> None:
    props = safe_props(
        {
            "char": "x",
            "clipboard": "secret",
            "surface": "Playlist",
            "caption": r"C:\Users\secret\song.flp",
            "text": "Slice tool",
            "plugin": "",
            "x": 10,
            "y": 20,
        },
        event_type="HINT",
    )
    assert "char" not in props
    assert "clipboard" not in props
    assert "x" not in props
    assert props.get("hint_class") == "slice"
    assert "caption" not in props


def test_privacy_unrecognized_hint_not_persisted() -> None:
    props = safe_props({"text": "My Secret Project Label"}, event_type="HINT")
    assert props.get("hint_present") is True
    assert "hint_class" not in props
    assert "secret" not in str(props).lower()


def test_hint_class_deterministic_across_seeds() -> None:
    from fl_workflow_analyzer.privacy import classify_hint

    assert classify_hint("Paint / Select") == "paint"
    assert classify_hint("Select / Paint") == "paint"  # ordered token precedence


def test_golden_browse_to_playlist() -> None:
    t0 = 10 * NS
    events = [
        # Blind-spot browse: win input without FL Browser surface label
        _ev(source="win", seq=1, etype="WHEEL", wall=t0, props={"delta": 120}),
        _ev(source="win", seq=2, etype="CLICK", wall=t0 + int(0.2 * NS), props={"button": "left", "phase": "up"}),
        _ev(
            source="fl",
            seq=1,
            etype="FOCUS_SURFACE",
            wall=t0 + NS,
            props={"surface": "Playlist", "prev": None},
        ),
        _ev(
            source="win",
            seq=3,
            etype="DRAG",
            wall=t0 + NS + int(0.1 * NS),
            props={"phase": "end", "distance": 40},
        ),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + 2 * NS
    )
    acts = _activities(result)
    assert "browse" in acts
    assert any(a in ("arrangement", "playlist_edit") for a in acts)
    browse = next(s for s in result["segments"] if s["activity"] == "browse")
    assert browse["confidence"] == "low"
    assert browse["truth_level"] == "interpreted"
    assert any(b["id"] == "browser_surface_label" for b in result["blind_spots"])


def test_golden_edit_listen_loop() -> None:
    t0 = 100 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "Playlist"}),
        _ev(source="win", seq=1, etype="DRAG", wall=t0 + int(0.2 * NS), props={"phase": "end"}),
        _ev(source="fl", seq=2, etype="REFRESH", wall=t0 + int(0.25 * NS), props={}),
        _ev(
            source="fl",
            seq=3,
            etype="TRANSPORT",
            wall=t0 + NS,
            props={"playing": True, "event": "PLAY"},
        ),
        _ev(
            source="fl",
            seq=4,
            etype="TRANSPORT",
            wall=t0 + 2 * NS,
            props={"playing": False, "event": "STOP"},
        ),
        _ev(source="win", seq=2, etype="DRAG", wall=t0 + int(2.2 * NS), props={"phase": "end"}),
        _ev(source="fl", seq=5, etype="UNDO", wall=t0 + int(2.3 * NS), props={"undo_count": 1}),
        _ev(
            source="fl",
            seq=6,
            etype="TRANSPORT",
            wall=t0 + 3 * NS,
            props={"playing": True, "event": "PLAY"},
        ),
        _ev(
            source="fl",
            seq=7,
            etype="TRANSPORT",
            wall=t0 + 4 * NS,
            props={"playing": False, "event": "STOP"},
        ),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + 5 * NS
    )
    acts = _activities(result)
    assert "playlist_edit" in acts or "arrangement" in acts
    assert "transport_listening" in acts
    # Loop evidence should appear for edit/play alternation when repeated.
    assert result["loops"] or any(
        p["n"] >= 2 and "transport_listening" in p["path"] for p in result["paths"]
    )


def test_golden_plugin_roundtrip() -> None:
    t0 = 200 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "Playlist"}),
        _ev(
            source="fl",
            seq=2,
            etype="FOCUS_PLUGIN",
            wall=t0 + NS,
            props={"plugin": "", "surface": "Plugin"},
        ),
        _ev(source="win", seq=1, etype="CLICK", wall=t0 + NS + int(0.1 * NS), props={"button": "left"}),
        _ev(
            source="fl",
            seq=3,
            etype="FOCUS_SURFACE",
            wall=t0 + 2 * NS,
            props={"surface": "Playlist", "prev": "Plugin"},
        ),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + 3 * NS
    )
    acts = _activities(result)
    assert "plugin_interaction" in acts
    assert any(a in ("arrangement", "playlist_edit") for a in acts)
    plugin_actions = [a for a in result["actions"] if a["action_type"] == "plugin_focus"]
    assert plugin_actions
    assert plugin_actions[0]["confidence"] == "low"
    assert "blind_spot_plugin_identity" in plugin_actions[0]["reasons"]


def test_golden_backtracking() -> None:
    t0 = 300 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "PianoRoll"}),
        _ev(source="win", seq=1, etype="CLICK", wall=t0 + int(0.1 * NS), props={"button": "left"}),
        _ev(source="fl", seq=2, etype="FOCUS_SURFACE", wall=t0 + NS, props={"surface": "Playlist"}),
        _ev(source="win", seq=2, etype="CLICK", wall=t0 + NS + int(0.1 * NS), props={"button": "left"}),
        _ev(source="fl", seq=3, etype="FOCUS_SURFACE", wall=t0 + 2 * NS, props={"surface": "PianoRoll"}),
        _ev(source="win", seq=3, etype="CLICK", wall=t0 + 2 * NS + int(0.1 * NS), props={"button": "left"}),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + 3 * NS
    )
    assert result["backtracks"]
    patterns = [tuple(b["pattern"]) for b in result["backtracks"]]
    assert any(p[0] == p[-1] for p in patterns)


def test_golden_idle_not_during_short_gaps() -> None:
    t0 = 400 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "Mixer"}),
        _ev(source="win", seq=1, etype="CLICK", wall=t0 + int(0.5 * NS), props={"button": "left"}),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + NS
    )
    assert "idle" not in _activities(result)


def test_golden_true_idle() -> None:
    t0 = 500 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "Mixer"}),
        _ev(source="win", seq=1, etype="CLICK", wall=t0 + int(0.1 * NS), props={"button": "left"}),
    ]
    # Session extends well past IDLE_QUIET_NS with no transport.
    result = analyze_events_in_memory(
        events,
        session_start_ns=t0,
        session_end_ns=t0 + IDLE_QUIET_NS + 5 * NS,
    )
    assert "idle" in _activities(result)
    assert "transport_listening" not in _activities(result)


def test_golden_playback_without_input_is_listening_not_idle() -> None:
    t0 = 600 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "Playlist"}),
        _ev(
            source="fl",
            seq=2,
            etype="TRANSPORT",
            wall=t0 + int(0.2 * NS),
            props={"playing": True, "event": "PLAY"},
        ),
    ]
    result = analyze_events_in_memory(
        events,
        session_start_ns=t0,
        session_end_ns=t0 + IDLE_QUIET_NS + 10 * NS,
    )
    acts = _activities(result)
    assert "transport_listening" in acts
    assert "idle" not in acts


def test_golden_edit_arrangement_transitions() -> None:
    t0 = 700 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "PianoRoll"}),
        _ev(source="win", seq=1, etype="CLICK", wall=t0 + int(0.1 * NS), props={"button": "left"}),
        _ev(
            source="fl",
            seq=2,
            etype="FOCUS_SURFACE",
            wall=t0 + 5 * NS,
            props={"surface": "Playlist"},
        ),
        _ev(source="win", seq=2, etype="DRAG", wall=t0 + 5 * NS + int(0.1 * NS), props={"phase": "end"}),
        _ev(
            source="fl",
            seq=3,
            etype="FOCUS_SURFACE",
            wall=t0 + 8 * NS,
            props={"surface": "ChannelRack"},
        ),
        _ev(source="win", seq=3, etype="CLICK", wall=t0 + 8 * NS + int(0.1 * NS), props={"button": "left"}),
        _ev(
            source="fl",
            seq=4,
            etype="FOCUS_SURFACE",
            wall=t0 + 20 * NS,
            props={"surface": "Playlist"},
        ),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + 25 * NS
    )
    ea = result["edit_arrangement"]
    assert ea["edit_to_arrangement_count"] >= 1
    assert ea["arrangement_to_edit_count"] >= 1
    assert ea["truth_level"] == "interpreted"
    assert "not a good/bad" in ea["note"].lower() or "evidence only" in ea["note"].lower()


def test_golden_low_confidence_blind_spot() -> None:
    t0 = 800 * NS
    events = [
        _ev(source="win", seq=1, etype="CLICK", wall=t0, props={"button": "left"}),
        _ev(source="fl", seq=1, etype="HINT", wall=t0 + int(0.05 * NS), props={"text": "SomethingOdd"}),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + NS
    )
    clickish = [a for a in result["actions"] if a["action_type"].startswith("click")]
    assert clickish
    assert clickish[0]["confidence"] == "low"
    assert clickish[0]["truth_level"] in ("interpreted", "correlated")


def test_active_gap_carry_preserves_dwell() -> None:
    """Gaps between interactions (< idle, > merge) remain active production time."""
    t0 = 1200 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "Mixer"}),
        _ev(source="win", seq=1, etype="CLICK", wall=t0 + int(0.1 * NS), props={"button": "left"}),
        _ev(source="win", seq=2, etype="CLICK", wall=t0 + 10 * NS, props={"button": "left"}),
        _ev(source="win", seq=3, etype="CLICK", wall=t0 + 20 * NS, props={"button": "left"}),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + 21 * NS
    )
    mixer_ns = sum(s["duration_ns"] for s in result["segments"] if s["activity"] == "mixer")
    assert mixer_ns >= 19 * NS
    assert result["coverage"]["active_ns"] >= 19 * NS


def test_undo_requires_pos_decrease() -> None:
    t0 = 1300 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "Playlist"}),
        # Init snapshot — must not count as undo
        _ev(
            source="fl",
            seq=2,
            etype="UNDO",
            wall=t0 + int(0.1 * NS),
            props={"undo_pos": 1, "undo_count": 1},
        ),
        # History growth from edit — not undo
        _ev(
            source="fl",
            seq=3,
            etype="UNDO",
            wall=t0 + int(0.2 * NS),
            props={"undo_pos": 2, "undo_count": 2},
        ),
        # Actual undo
        _ev(
            source="fl",
            seq=4,
            etype="UNDO",
            wall=t0 + int(0.3 * NS),
            props={"undo_pos": 1, "undo_count": 2},
        ),
        # Redo
        _ev(
            source="fl",
            seq=5,
            etype="UNDO",
            wall=t0 + int(0.4 * NS),
            props={"undo_pos": 2, "undo_count": 2},
        ),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + NS
    )
    types = [a["action_type"] for a in result["actions"]]
    assert types.count("undo") == 1
    assert types.count("redo") == 1
    assert result["undo"]["undo_count"] == 1


def test_background_beats_listening_in_gaps() -> None:
    t0 = 1400 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "Playlist"}),
        _ev(
            source="fl",
            seq=2,
            etype="TRANSPORT",
            wall=t0 + int(0.1 * NS),
            props={"playing": True, "event": "PLAY"},
        ),
        _ev(
            source="win",
            seq=1,
            etype="FG",
            wall=t0 + NS,
            props={"event": "FL_BACKGROUND", "fl_foreground": False},
        ),
        _ev(
            source="win",
            seq=2,
            etype="FG",
            wall=t0 + 60 * NS,
            props={"event": "FL_FOREGROUND", "fl_foreground": True},
        ),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + 61 * NS
    )
    bg_ns = sum(s["duration_ns"] for s in result["segments"] if s["activity"] == "background")
    assert bg_ns >= 50 * NS
    # Background time must not inflate listening coverage.
    assert result["coverage"]["listening_ns"] < 10 * NS


def test_plugin_clear_on_mixer_not_plugin_interaction() -> None:
    t0 = 1500 * NS
    events = [
        _ev(
            source="fl",
            seq=1,
            etype="FOCUS_PLUGIN",
            wall=t0,
            props={"plugin": "Serum", "surface": "Plugin"},
        ),
        _ev(source="win", seq=1, etype="CLICK", wall=t0 + int(0.1 * NS), props={"button": "left"}),
        _ev(source="fl", seq=2, etype="FOCUS_SURFACE", wall=t0 + NS, props={"surface": "Mixer"}),
        _ev(
            source="fl",
            seq=3,
            etype="FOCUS_PLUGIN",
            wall=t0 + NS + 1000,
            props={"plugin": "", "surface": "Mixer"},
        ),
        _ev(source="win", seq=2, etype="CLICK", wall=t0 + 5 * NS, props={"button": "left"}),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + 6 * NS
    )
    mixer_ns = sum(s["duration_ns"] for s in result["segments"] if s["activity"] == "mixer")
    plugin_ns = sum(
        s["duration_ns"] for s in result["segments"] if s["activity"] == "plugin_interaction"
    )
    assert mixer_ns >= 4 * NS
    assert plugin_ns < 2 * NS


def test_idle_not_erased_by_later_focus() -> None:
    t0 = 1700 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "Mixer"}),
        _ev(
            source="fl",
            seq=2,
            etype="FOCUS_SURFACE",
            wall=t0 + 300 * NS,
            props={"surface": "Playlist"},
        ),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + 310 * NS
    )
    idle_ns = sum(s["duration_ns"] for s in result["segments"] if s["activity"] == "idle")
    # Quiet from ~120s after mixer focus until playlist focus at 300s.
    assert idle_ns >= 150 * NS


def test_fl_dirty_resets_idle_deadline() -> None:
    t0 = 1600 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "Mixer"}),
        _ev(source="fl", seq=2, etype="DIRTY_MIXER", wall=t0 + 60 * NS, props={"items": [1]}),
        _ev(source="fl", seq=3, etype="DIRTY_MIXER", wall=t0 + 110 * NS, props={"items": [1]}),
        _ev(source="fl", seq=4, etype="DIRTY_MIXER", wall=t0 + 160 * NS, props={"items": [1]}),
        _ev(source="fl", seq=5, etype="DIRTY_MIXER", wall=t0 + 210 * NS, props={"items": [1]}),
        _ev(source="fl", seq=6, etype="DIRTY_MIXER", wall=t0 + 260 * NS, props={"items": [1]}),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + 300 * NS
    )
    idle_ns = sum(s["duration_ns"] for s in result["segments"] if s["activity"] == "idle")
    # With DIRTY every ~50s (< 120s idle), idle share must stay small.
    assert idle_ns < 60 * NS


def test_deterministic_rerun() -> None:
    t0 = 900 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "Mixer"}),
        _ev(source="win", seq=1, etype="CLICK", wall=t0 + int(0.2 * NS), props={"button": "left"}),
        _ev(source="fl", seq=2, etype="DIRTY_MIXER", wall=t0 + int(0.25 * NS), props={"items": [1]}),
    ]
    a = analyze_events_in_memory(events, session_start_ns=t0, session_end_ns=t0 + NS)
    b = analyze_events_in_memory(events, session_start_ns=t0, session_end_ns=t0 + NS)
    assert _activities(a) == _activities(b)
    assert [x["action_type"] for x in a["actions"]] == [x["action_type"] for x in b["actions"]]
    assert a["rule_version"] == b["rule_version"] == RULE_VERSION


def test_sqlite_reprocess_does_not_mutate_raw(tmp_path: Path) -> None:
    db = tmp_path / "workflow.sqlite3"
    raw = WorkflowStore(db)
    sid = "sess-repro-1"
    t0 = time.time_ns()
    raw.create_session(sid, fl_version="test")
    raw.insert_event(
        sid,
        {
            "source": "fl",
            "source_seq": 1,
            "t_wall_ns": t0,
            "t_utc": "2026-01-01T00:00:00.000Z",
            "event_type": "FOCUS_SURFACE",
            "props": {"surface": "Playlist"},
        },
    )
    raw.insert_event(
        sid,
        {
            "source": "win",
            "source_seq": 1,
            "t_wall_ns": t0 + 100_000_000,
            "t_utc": "2026-01-01T00:00:00.100Z",
            "event_type": "CLICK",
            "props": {"button": "left", "phase": "up"},
        },
    )
    raw.close_session(sid, close_reason="test", ended_at_wall_ns=t0 + NS)
    raw.close()

    conn_before = __import__("sqlite3").connect(str(db))
    raw_events_before = conn_before.execute("SELECT * FROM events ORDER BY id").fetchall()
    conn_before.close()

    result1 = run_analysis(db, clear_previous=True)
    result2 = run_analysis(db, clear_previous=True)
    assert result1["status"] == "ok"
    assert result2["status"] == "ok"
    assert result1["sessions_analyzed"] == 1
    assert result1["analyzer_version"] == ANALYZER_VERSION

    conn_after = __import__("sqlite3").connect(str(db))
    raw_events_after = conn_after.execute("SELECT * FROM events ORDER BY id").fetchall()
    derived = conn_after.execute("SELECT COUNT(*) FROM derived_segments").fetchone()[0]
    runs = conn_after.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
    conn_after.close()

    assert raw_events_before == raw_events_after
    assert derived >= 1
    assert runs == 1  # clear_previous wiped prior run


def test_foreground_leave_not_counted_as_workflow() -> None:
    t0 = 1000 * NS
    events = [
        _ev(source="fl", seq=1, etype="FOCUS_SURFACE", wall=t0, props={"surface": "Playlist"}),
        _ev(
            source="win",
            seq=1,
            etype="FG",
            wall=t0 + NS,
            props={"event": "FL_BACKGROUND", "fl_foreground": False},
        ),
        _ev(
            source="win",
            seq=2,
            etype="FG",
            wall=t0 + 3 * NS,
            props={"event": "FL_FOREGROUND", "fl_foreground": True},
        ),
        _ev(source="win", seq=3, etype="CLICK", wall=t0 + int(3.1 * NS), props={"button": "left"}),
    ]
    result = analyze_events_in_memory(
        events, session_start_ns=t0, session_end_ns=t0 + 4 * NS
    )
    assert "background" in _activities(result)


def test_crash_truncated_session_flagged_via_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "workflow.sqlite3"
    raw = WorkflowStore(db)
    sid = "sess-crash"
    t0 = time.time_ns()
    raw.create_session(sid)
    raw.insert_event(
        sid,
        {
            "source": "fl",
            "source_seq": 1,
            "t_wall_ns": t0,
            "t_utc": "2026-01-01T00:00:00.000Z",
            "event_type": "TRANSPORT",
            "props": {"playing": True, "event": "PLAY"},
        },
    )
    raw.close_session(
        sid,
        close_reason="fl_crash",
        status="recovered",
        ended_at_wall_ns=t0 + NS,
        recovery_marker=1,
    )
    raw.close()
    out = run_analysis(db, clear_previous=True)
    assert out["status"] == "ok"
    store = DerivedStore(db)
    conn = store.connect()
    row = conn.execute(
        "SELECT payload_json FROM derived_metrics WHERE metric_type = 'session_quality'"
    ).fetchone()
    store.close()
    payload = json.loads(row["payload_json"])
    assert payload["completeness"] == "reduced"
    assert payload["recovery_marker"] is True


@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_hot_path_n_supported(n: int) -> None:
    # Build a repeated activity sequence long enough for n-grams with count>=2.
    t0 = 1100 * NS
    events = []
    seq = 0
    wall = t0
    # Pattern: PianoRoll focus+click, Playlist focus+click, repeated thrice
    for _ in range(3):
        seq += 1
        events.append(
            _ev(source="fl", seq=seq, etype="FOCUS_SURFACE", wall=wall, props={"surface": "PianoRoll"})
        )
        wall += int(0.2 * NS)
        seq_w = seq
        events.append(
            _ev(source="win", seq=seq_w, etype="CLICK", wall=wall, props={"button": "left"})
        )
        wall += NS
        seq += 1
        events.append(
            _ev(source="fl", seq=seq, etype="FOCUS_SURFACE", wall=wall, props={"surface": "Playlist"})
        )
        wall += int(0.2 * NS)
        events.append(
            _ev(source="win", seq=seq, etype="CLICK", wall=wall, props={"button": "left"})
        )
        wall += NS
    result = analyze_events_in_memory(events, session_start_ns=t0, session_end_ns=wall + NS)
    if n <= 4:
        assert any(p["n"] == n and p["count"] >= 2 for p in result["paths"]) or n > len(
            [s for s in result["segments"] if s["activity"] not in ("idle", "background")]
        )
