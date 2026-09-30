"""Measurement Local Report v1 — read/aggregation path tests."""

from __future__ import annotations

import ast
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

from src.measurement.config import MeasurementMode, resolve_measurement_mode
from src.measurement.contract import DOCUMENT_TYPE, SCHEMA_VERSION, MeasurementEvent, PrivacyClass
from src.measurement.sinks import SidecarSqliteSink
from src.measurement.stats import percentile
from src.measurement.report import (
    build_stage_finished_report,
    format_report_text,
    report_to_dict,
)
from src.measurement.reader import ReadStatus


REPO_ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_PKG = REPO_ROOT / "src" / "measurement"


def _stage_event(
    *,
    run_id: str = "550e8400-e29b-41d4-a716-446655440000",
    wall_ms: int = 100,
    items_ok: int = 1,
    items_skip: int = 0,
    items_fail: int = 0,
    status: str = "ok",
    app_version: str = "0.1.0",
    analyzer_version: str | None = "an-1",
    git_sha: str | None = "abc1234",
) -> MeasurementEvent:
    return MeasurementEvent(
        document_type=DOCUMENT_TYPE,
        schema_version=SCHEMA_VERSION,
        event_name="pipeline.stage_finished",
        event_version=1,
        occurred_at="2026-09-30T20:15:00.123Z",
        run_id=run_id,
        session_id=None,
        domain="pipeline",
        privacy_class=PrivacyClass.EXPORT_SAFE,
        status=status,
        reason_code=None,
        app={
            "app_version": app_version,
            "git_sha": git_sha,
            "analyzer_version": analyzer_version,
            "search_backend": None,
        },
        props={
            "stage": "analyze",
            "wall_ms": wall_ms,
            "items_ok": items_ok,
            "items_skip": items_skip,
            "items_fail": items_fail,
        },
    )


def test_percentile_empty_one_many() -> None:
    assert percentile([], 50) is None
    assert percentile([], 95) is None
    assert percentile([7], 50) == 7.0
    assert percentile([7], 95) == 7.0
    vals = [10, 20, 30, 40, 50]
    assert percentile(vals, 50) == 30.0
    assert percentile(vals, 0) == 10.0
    assert percentile(vals, 100) == 50.0
    p95 = percentile(vals, 95)
    assert p95 is not None
    assert 40.0 <= p95 <= 50.0


def test_missing_sidecar_db(tmp_path: Path) -> None:
    missing = tmp_path / "nope" / "measurement.db"
    report = build_stage_finished_report(missing)
    assert report.status == ReadStatus.MISSING_DB
    d = report_to_dict(report)
    assert d["status"] == "missing_db"
    assert "db_path" not in d


def test_empty_sidecar_db(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    SidecarSqliteSink(db).flush()
    report = build_stage_finished_report(db)
    assert report.status == ReadStatus.NO_DATA
    assert report.events == 0
    assert report.invalid == 0


def test_one_valid_stage_finished(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    sink = SidecarSqliteSink(db)
    sink.write(_stage_event(wall_ms=42, items_ok=3, items_fail=1))
    sink.flush()
    report = build_stage_finished_report(db)
    assert report.status == ReadStatus.OK
    assert report.events == 1
    assert report.runs == 1
    assert report.status_counts.get("ok") == 1
    analyze = report.by_stage["analyze"]
    assert analyze["items_ok_sum"] == 3
    assert analyze["items_fail_sum"] == 1
    assert analyze["wall_ms"]["min"] == 42
    assert analyze["wall_ms"]["p50"] == 42
    assert analyze["wall_ms"]["p95"] == 42
    assert analyze["wall_ms"]["max"] == 42


def test_multiple_analyze_events_aggregates(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    sink = SidecarSqliteSink(db)
    sink.write(_stage_event(run_id="r1", wall_ms=10, items_ok=1, status="ok"))
    sink.write(_stage_event(run_id="r2", wall_ms=30, items_ok=2, items_fail=1, status="ok"))
    sink.write(_stage_event(run_id="r3", wall_ms=50, items_ok=0, status="error"))
    sink.flush()
    report = build_stage_finished_report(db)
    assert report.events == 3
    assert report.runs == 3
    assert report.status_counts["ok"] == 2
    assert report.status_counts["error"] == 1
    analyze = report.by_stage["analyze"]
    assert analyze["items_ok_sum"] == 3
    assert analyze["items_fail_sum"] == 1
    assert analyze["wall_ms"]["min"] == 10
    assert analyze["wall_ms"]["max"] == 50
    assert analyze["wall_ms"]["p50"] == 30


def test_version_grouping(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    sink = SidecarSqliteSink(db)
    sink.write(
        _stage_event(run_id="a", app_version="0.1.0", analyzer_version="a1", git_sha="g1")
    )
    sink.write(
        _stage_event(run_id="b", app_version="0.1.0", analyzer_version="a1", git_sha="g1")
    )
    sink.write(
        _stage_event(run_id="c", app_version="0.2.0", analyzer_version="a2", git_sha="g2")
    )
    sink.flush()
    report = build_stage_finished_report(db)
    versions = report.by_app
    assert len(versions) == 2
    keys = {(v["app_version"], v["analyzer_version"], v["git_sha"]) for v in versions}
    assert ("0.1.0", "a1", "g1") in keys
    assert ("0.2.0", "a2", "g2") in keys


def test_malformed_payload_counted(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    sink = SidecarSqliteSink(db)
    sink.write(_stage_event(run_id="good", wall_ms=11))
    sink.flush()
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO events (
                occurred_at, event_name, domain, privacy_class,
                run_id, session_id, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-09-30T20:15:00.123Z",
                "pipeline.stage_finished",
                "pipeline",
                "export_safe",
                "bad",
                None,
                "{not-json",
            ),
        )
        conn.commit()
    report = build_stage_finished_report(db)
    assert report.events == 1
    assert report.invalid >= 1
    assert report.by_stage["analyze"]["wall_ms"]["min"] == 11


def test_unknown_event_skipped(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    sink = SidecarSqliteSink(db)
    sink.write(_stage_event(run_id="good", wall_ms=9))
    sink.flush()
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO events (
                occurred_at, event_name, domain, privacy_class,
                run_id, session_id, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-09-30T20:15:00.123Z",
                "search.query_finished",
                "search",
                "export_safe",
                "other",
                None,
                json.dumps({"event_name": "search.query_finished"}),
            ),
        )
        conn.commit()
    report = build_stage_finished_report(db)
    assert report.events == 1
    assert report.skipped_unknown >= 1
    assert report.by_stage["analyze"]["wall_ms"]["max"] == 9


def test_privacy_no_forbidden_fields_in_output(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    sink = SidecarSqliteSink(db)
    sink.write(_stage_event())
    sink.flush()
    report = build_stage_finished_report(db)
    blob = json.dumps(report_to_dict(report)) + "\n" + format_report_text(report)
    for needle in ("sample_id", "filename", "library_root", "C:\\", "/Users/", "tone.wav"):
        assert needle not in blob
    assert "db_path" not in report_to_dict(report)


def test_reader_is_read_only(tmp_path: Path) -> None:
    db = tmp_path / "measurement.db"
    sink = SidecarSqliteSink(db)
    sink.write(_stage_event(run_id="r1"))
    sink.flush()
    before = db.read_bytes()
    mtime = db.stat().st_mtime_ns
    _ = build_stage_finished_report(db)
    after = db.read_bytes()
    assert after == before
    assert db.stat().st_mtime_ns == mtime


def test_report_does_not_change_measurement_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_MODE", "off")
    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_DB_PATH", str(tmp_path / "measurement.db"))
    assert resolve_measurement_mode(env=dict(os.environ)) is MeasurementMode.OFF
    _ = build_stage_finished_report(tmp_path / "measurement.db")
    assert os.environ.get("SAMPLE_BRAIN_MEASUREMENT_MODE") == "off"
    assert resolve_measurement_mode(env=dict(os.environ)) is MeasurementMode.OFF


def test_report_modules_have_no_provider_imports() -> None:
    forbidden = {"mixpanel", "requests", "httpx", "urllib3", "aiohttp"}
    found: set[str] = set()
    for path in MEASUREMENT_PKG.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in forbidden:
                        found.add(root)
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in forbidden:
                    found.add(root)
    assert found == set()


def test_cli_measurement_report_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    import src.cli as cli

    db = tmp_path / "measurement.db"
    sink = SidecarSqliteSink(db)
    sink.write(_stage_event(wall_ms=15, items_ok=4))
    sink.flush()
    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_DB_PATH", str(db))
    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_MODE", "off")
    monkeypatch.setattr(sys, "argv", ["sample-brain", "measurement", "report", "--json"])
    cli.main()
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "ok"
    assert payload["events"] == 1
    assert payload["by_stage"]["analyze"]["wall_ms"]["min"] == 15
    assert "db_path" not in payload
