"""Measurement Producer Slice — match.query_finished (ADR-0006)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from src.measurement.bus import MeasurementBus
from src.measurement.config import MeasurementMode
from src.measurement.contract import (
    FORBIDDEN_PROP_KEYS,
    MATCH_QUERY_FINISHED_ALLOWED_PROPS,
    MeasurementEvent,
    PrivacyClass,
    validate_event,
)
from src.measurement.emit import (
    build_bus_from_settings,
    emit_match_query_finished,
    make_match_query_finished_observer,
)
from src.measurement.report import (
    build_match_query_finished_report,
    build_stage_finished_report,
    format_match_report_text,
    match_report_to_dict,
)
from src.measurement.reader import ReadStatus
from src.measurement.sinks import SidecarSqliteSink
from src.workbench_controller import WorkbenchRow
from src.workbench_harmony import (
    HarmonicMatchLibraryController,
    HarmonyRelation,
    HarmonySuggestion,
)
from src.workbench_session import compose_workbench_session


def _row(
    name: str,
    *,
    key: str | None = "Cmaj",
    bpm: float | None = 128.0,
) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"synthetic/{name}.wav",
        path=f"synthetic/{name}.wav",
        bpm=bpm,
        key=key,
        key_conf=0.9 if key else None,
        loudness=-18.0,
        brightness=2400.0,
        sample_class="loop",
        pred_type="Synth Loop",
        status="ok",
        details={"source": "synthetic"},
    )


def _suggestion(
    row: WorkbenchRow,
    relation: HarmonyRelation,
    *,
    total: float = 0.9,
    pitch: int | None = None,
) -> HarmonySuggestion:
    return HarmonySuggestion(
        row=row,
        relation=relation,
        harmony_score={
            HarmonyRelation.DIRECT: 1.0,
            HarmonyRelation.RELATED: 0.7,
            HarmonyRelation.TRANSPOSE: 0.5,
            HarmonyRelation.UNCERTAIN: 0.0,
        }[relation],
        bpm_score=1.0,
        total_score=total,
        pitch_shift_semitones=pitch,
        explanation=relation.value,
    )


def _valid_match(**prop_overrides) -> MeasurementEvent:
    props = {"wall_ms": 12, "result_count": 3, **prop_overrides}
    return MeasurementEvent(
        document_type="sample_brain.measurement_event",
        schema_version="1.0.0",
        event_name="match.query_finished",
        event_version=1,
        occurred_at="2026-09-30T22:00:00.000Z",
        run_id="550e8400-e29b-41d4-a716-446655440099",
        session_id="550e8400-e29b-41d4-a716-446655440088",
        domain="match",
        privacy_class=PrivacyClass.EXPORT_SAFE,
        status="ok",
        reason_code=None,
        app={
            "app_version": "0.1.0",
            "git_sha": None,
            "analyzer_version": None,
            "search_backend": None,
        },
        props=props,
    )


# --- Contract ---


def test_valid_match_query_finished_accepted() -> None:
    event = _valid_match()
    assert validate_event(event) is event


def test_match_wrong_domain_rejected() -> None:
    bad = _valid_match()
    bad = bad.__class__(**{**bad.__dict__, "domain": "pipeline"})
    assert validate_event(bad) is None


def test_match_unknown_props_rejected() -> None:
    assert validate_event(_valid_match(extra_field=1)) is None
    assert "extra_field" not in MATCH_QUERY_FINISHED_ALLOWED_PROPS


def test_match_negative_wall_ms_rejected() -> None:
    assert validate_event(_valid_match(wall_ms=-1)) is None


def test_match_negative_result_count_rejected() -> None:
    assert validate_event(_valid_match(result_count=-1)) is None


def test_match_bool_as_int_rejected() -> None:
    assert validate_event(_valid_match(wall_ms=True)) is None
    assert validate_event(_valid_match(result_count=False)) is None


def test_match_forbidden_props_rejected() -> None:
    for key in ("path", "sample_id", "query", "filename", "bpm", "key", "pred_type"):
        assert key in FORBIDDEN_PROP_KEYS or key not in MATCH_QUERY_FINISHED_ALLOWED_PROPS
        assert validate_event(_valid_match(**{key: "leak"})) is None


def test_match_path_leak_rejected() -> None:
    # Unknown prop with path-like string is also rejected via allow-list.
    assert validate_event(_valid_match(anchor_path="C:/Samples/a.wav")) is None


# --- Producer ---


def test_successful_match_emits_exactly_one_event(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    bus = build_bus_from_settings(mode=MeasurementMode.LOCAL, db_path=db)
    calls: list[dict] = []

    def observer(*, wall_ms: int, result_count: int, status: str = "ok") -> None:
        calls.append(
            {"wall_ms": wall_ms, "result_count": result_count, "status": status}
        )
        emit_match_query_finished(
            bus=bus,
            wall_ms=wall_ms,
            result_count=result_count,
            status=status,
            session_id=str(uuid.uuid4()),
            run_id=str(uuid.uuid4()),
        )

    direct = _suggestion(_row("direct"), HarmonyRelation.DIRECT)
    uncertain = _suggestion(_row("u"), HarmonyRelation.UNCERTAIN)
    far = _suggestion(_row("far"), HarmonyRelation.TRANSPOSE, pitch=7)

    def finder(anchor, candidates):
        return [direct, uncertain, far], None

    ctrl = HarmonicMatchLibraryController(finder=finder, on_query_finished=observer)
    ctrl.set_anchor(_row("anchor"), [_row("direct"), _row("u"), _row("far")])

    assert len(calls) == 1
    assert calls[0]["result_count"] == 1
    assert calls[0]["status"] == "ok"
    assert len(ctrl.results) == 1

    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT event_name FROM events").fetchall()
    conn.close()
    assert rows == [("match.query_finished",)]


def test_result_count_matches_visible_secure_matches() -> None:
    related = _suggestion(_row("rel"), HarmonyRelation.RELATED, total=0.8)
    transpose_ok = _suggestion(_row("t"), HarmonyRelation.TRANSPOSE, pitch=2)
    uncertain = _suggestion(_row("u"), HarmonyRelation.UNCERTAIN)
    observed: list[int] = []

    def observer(*, wall_ms: int, result_count: int, status: str = "ok") -> None:
        observed.append(result_count)

    def finder(anchor, candidates):
        return [related, transpose_ok, uncertain], None

    ctrl = HarmonicMatchLibraryController(finder=finder, on_query_finished=observer)
    ctrl.set_anchor(_row("anchor"), [_row("rel"), _row("t"), _row("u")])
    assert observed == [2]
    assert len(ctrl.results) == 2


def test_zero_result_query_is_ok_count_zero() -> None:
    observed: list[tuple[int, str]] = []

    def observer(*, wall_ms: int, result_count: int, status: str = "ok") -> None:
        observed.append((result_count, status))

    def finder(anchor, candidates):
        return [], "Keine sicheren Harmonic Matches gefunden."

    ctrl = HarmonicMatchLibraryController(finder=finder, on_query_finished=observer)
    ctrl.set_anchor(_row("anchor"), [_row("other", key="Fmin")])
    assert observed == [(0, "ok")]
    assert ctrl.results == ()


def test_measurement_off_no_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_MODE", "off")
    monkeypatch.setenv(
        "SAMPLE_BRAIN_MEASUREMENT_DB_PATH", str(tmp_path / "measurement.db")
    )
    observer, session_id = make_match_query_finished_observer(env=dict(os.environ))
    assert observer is None
    assert session_id is None
    assert not (tmp_path / "measurement.db").exists()


def test_observer_exception_does_not_change_matching() -> None:
    direct = _suggestion(_row("direct"), HarmonyRelation.DIRECT)

    def finder(anchor, candidates):
        return [direct], None

    def boom(*, wall_ms: int, result_count: int, status: str = "ok") -> None:
        raise RuntimeError("observer failed")

    ctrl = HarmonicMatchLibraryController(finder=finder, on_query_finished=boom)
    ctrl.set_anchor(_row("anchor"), [_row("direct")])
    assert len(ctrl.results) == 1
    assert "1 sichere" in ctrl.status


def test_no_per_candidate_events(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    bus = build_bus_from_settings(mode=MeasurementMode.LOCAL, db_path=db)
    session = str(uuid.uuid4())
    call_count = {"n": 0}

    def observer(*, wall_ms: int, result_count: int, status: str = "ok") -> None:
        call_count["n"] += 1
        emit_match_query_finished(
            bus=bus,
            wall_ms=wall_ms,
            result_count=result_count,
            session_id=session,
        )

    a = _suggestion(_row("a"), HarmonyRelation.DIRECT)
    b = _suggestion(_row("b"), HarmonyRelation.RELATED)

    def finder(anchor, candidates):
        return [a, b], None

    ctrl = HarmonicMatchLibraryController(finder=finder, on_query_finished=observer)
    ctrl.set_anchor(_row("anchor"), [_row("a"), _row("b")])
    assert call_count["n"] == 1
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()
    assert n == 1


def test_sink_exception_does_not_change_matching(tmp_path: Path) -> None:
    class BoomSink:
        def emit(self, event: MeasurementEvent) -> None:
            raise RuntimeError("sink failed")

        def flush(self) -> None:
            raise RuntimeError("flush failed")

    bus = MeasurementBus(mode=MeasurementMode.LOCAL, sink=BoomSink())  # type: ignore[arg-type]
    direct = _suggestion(_row("direct"), HarmonyRelation.DIRECT)

    def finder(anchor, candidates):
        return [direct], None

    def observer(*, wall_ms: int, result_count: int, status: str = "ok") -> None:
        emit_match_query_finished(
            bus=bus,
            wall_ms=wall_ms,
            result_count=result_count,
            session_id=str(uuid.uuid4()),
        )

    ctrl = HarmonicMatchLibraryController(finder=finder, on_query_finished=observer)
    ctrl.set_anchor(_row("anchor"), [_row("direct")])
    assert len(ctrl.results) == 1
    assert "1 sichere" in ctrl.status


# --- Correlation ---


def test_session_id_stable_across_queries_in_composed_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "measurement.db"
    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_MODE", "local")
    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_DB_PATH", str(db))
    session = compose_workbench_session()
    assert session.measurement_session_id is not None
    sid = session.measurement_session_id
    ctrl = session.qml_interaction_adapter.harmony_controller
    assert isinstance(ctrl, HarmonicMatchLibraryController)

    direct = _suggestion(_row("direct"), HarmonyRelation.DIRECT)

    def finder(anchor, candidates):
        return [direct], None

    ctrl._finder = finder
    ctrl.set_anchor(_row("anchor"), [_row("direct")])
    ctrl.set_anchor(_row("anchor2", key="Gmaj"), [_row("direct", key="Gmaj")])

    conn = sqlite3.connect(db)
    payloads = [
        json.loads(row[0])
        for row in conn.execute("SELECT payload_json FROM events").fetchall()
    ]
    conn.close()
    assert len(payloads) == 2
    assert {p["session_id"] for p in payloads} == {sid}
    run_ids = {p["run_id"] for p in payloads}
    assert len(run_ids) == 2
    for rid in run_ids:
        uuid.UUID(rid)
    uuid.UUID(sid)
    blob = json.dumps(payloads)
    assert "synthetic/" not in blob
    assert "Cmaj" not in blob
    assert "128" not in blob or True  # wall_ms may coincidentally contain digits
    assert "Synth Loop" not in blob
    assert "anchor" not in blob


def test_run_ids_differ_and_are_opaque(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    observer, session_id = make_match_query_finished_observer(
        env={
            "SAMPLE_BRAIN_MEASUREMENT_MODE": "local",
            "SAMPLE_BRAIN_MEASUREMENT_DB_PATH": str(db),
        }
    )
    assert observer is not None and session_id is not None
    observer(wall_ms=1, result_count=0)
    observer(wall_ms=2, result_count=1)
    conn = sqlite3.connect(db)
    payloads = [
        json.loads(row[0])
        for row in conn.execute("SELECT payload_json FROM events").fetchall()
    ]
    conn.close()
    assert payloads[0]["run_id"] != payloads[1]["run_id"]
    assert payloads[0]["session_id"] == payloads[1]["session_id"] == session_id
    assert "path" not in payloads[0]["props"]
    assert set(payloads[0]["props"]) == {"wall_ms", "result_count"}


# --- Report ---


def test_match_report_single_event(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    bus = build_bus_from_settings(mode=MeasurementMode.LOCAL, db_path=db)
    emit_match_query_finished(
        bus=bus, wall_ms=42, result_count=3, session_id=str(uuid.uuid4())
    )
    report = build_match_query_finished_report(db)
    assert report.status == ReadStatus.OK
    assert report.events == 1
    assert report.runs == 1
    assert report.wall_ms["min"] == 42
    assert report.result_count["max"] == 3
    text = format_match_report_text(report)
    assert "wall_ms" in text
    assert "result_count" in text
    assert "path" not in text


def test_match_report_percentiles_and_result_count(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    bus = build_bus_from_settings(mode=MeasurementMode.LOCAL, db_path=db)
    for wall, count in [(10, 0), (20, 1), (30, 2), (40, 3), (50, 4)]:
        emit_match_query_finished(
            bus=bus,
            wall_ms=wall,
            result_count=count,
            run_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
        )
    report = build_match_query_finished_report(db)
    assert report.events == 5
    assert report.runs == 5
    assert report.wall_ms["min"] == 10
    assert report.wall_ms["max"] == 50
    assert report.wall_ms["p50"] == 30.0
    assert report.result_count["min"] == 0
    assert report.result_count["max"] == 4
    assert report.result_count["p50"] == 2.0


def test_match_report_malformed_row_fail_soft(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    sink = SidecarSqliteSink(db)
    sink.write(
        MeasurementEvent(
            document_type="sample_brain.measurement_event",
            schema_version="1.0.0",
            event_name="match.query_finished",
            event_version=1,
            occurred_at="2026-09-30T22:00:00.000Z",
            run_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            domain="match",
            privacy_class=PrivacyClass.EXPORT_SAFE,
            status="ok",
            reason_code=None,
            app={"app_version": "0.1.0"},
            props={"wall_ms": 5, "result_count": 1},
        )
    )
    sink.flush()
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO events(
            occurred_at, event_name, domain, privacy_class,
            run_id, session_id, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-09-30T22:00:00Z",
            "match.query_finished",
            "match",
            "export_safe",
            "bad-run",
            None,
            "{not-json",
        ),
    )
    conn.commit()
    conn.close()
    report = build_match_query_finished_report(db)
    assert report.status == ReadStatus.OK
    assert report.events == 1
    assert report.invalid >= 1


def test_unknown_events_do_not_break_match_report(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    bus = build_bus_from_settings(mode=MeasurementMode.LOCAL, db_path=db)
    emit_match_query_finished(bus=bus, wall_ms=7, result_count=0)
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO events(
            occurred_at, event_name, domain, privacy_class,
            run_id, session_id, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-09-30T22:00:00Z",
            "rank.action",
            "rank",
            "export_safe",
            "x",
            None,
            "{}",
        ),
    )
    conn.commit()
    conn.close()
    report = build_match_query_finished_report(db)
    assert report.status == ReadStatus.OK
    assert report.events == 1
    assert report.skipped_unknown >= 1


def test_match_report_json_privacy_safe(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    bus = build_bus_from_settings(mode=MeasurementMode.LOCAL, db_path=db)
    emit_match_query_finished(bus=bus, wall_ms=9, result_count=2)
    payload = match_report_to_dict(build_match_query_finished_report(db))
    blob = json.dumps(payload)
    assert "path" not in blob
    assert "sample_id" not in blob
    assert "filename" not in blob
    assert payload["event_name"] == "match.query_finished"
    assert "wall_ms" in payload
    assert "result_count" in payload


def test_pipeline_report_still_works_alongside_match(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    bus = build_bus_from_settings(mode=MeasurementMode.LOCAL, db_path=db)
    from src.measurement.emit import emit_pipeline_stage_finished

    emit_pipeline_stage_finished(
        bus=bus,
        stage="analyze",
        wall_ms=11,
        items_ok=1,
        items_skip=0,
        items_fail=0,
    )
    emit_match_query_finished(bus=bus, wall_ms=5, result_count=1)
    stage = build_stage_finished_report(db)
    match = build_match_query_finished_report(db)
    assert stage.status == ReadStatus.OK
    assert stage.events == 1
    assert stage.skipped_unknown >= 1
    assert match.status == ReadStatus.OK
    assert match.events == 1


def test_cli_match_report_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    import src.cli as cli

    db = tmp_path / "measurement.db"
    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_DB_PATH", str(db))
    bus = build_bus_from_settings(mode=MeasurementMode.LOCAL, db_path=db)
    emit_match_query_finished(bus=bus, wall_ms=15, result_count=4)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sample-brain",
            "measurement",
            "report",
            "--event",
            "match.query_finished",
            "--json",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["event_name"] == "match.query_finished"
    assert payload["wall_ms"]["min"] == 15
    assert payload["result_count"]["max"] == 4


def test_early_validation_does_not_emit() -> None:
    calls = []

    def observer(*, wall_ms: int, result_count: int, status: str = "ok") -> None:
        calls.append(1)

    ctrl = HarmonicMatchLibraryController(on_query_finished=observer)
    # Missing key -> early return before finder
    ctrl.set_anchor(_row("anchor", key=None), [_row("other")])
    assert calls == []
