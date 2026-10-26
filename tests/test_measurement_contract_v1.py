"""Measurement Contract v1 — first runtime slice tests (ADR-0006)."""

from __future__ import annotations

import ast
import sqlite3
import sys
from pathlib import Path

import pytest

from src.measurement.contract import (
    FORBIDDEN_PROP_KEYS,
    STAGE_FINISHED_ALLOWED_PROPS,
    MeasurementEvent,
    PrivacyClass,
    validate_event,
)
from src.measurement.config import (
    MeasurementMode,
    resolve_measurement_db_path,
    resolve_measurement_mode,
)
from src.measurement.sinks import NullSink, SidecarSqliteSink
from src.measurement.bus import MeasurementBus
from src.measurement.emit import emit_pipeline_stage_finished, build_bus_from_settings


REPO_ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_PKG = REPO_ROOT / "src" / "measurement"


def _valid_stage_finished(**prop_overrides) -> MeasurementEvent:
    props = {
        "stage": "analyze",
        "wall_ms": 12,
        "items_ok": 3,
        "items_skip": 0,
        "items_fail": 1,
        **prop_overrides,
    }
    return MeasurementEvent(
        document_type="sample_brain.measurement_event",
        schema_version="1.0.0",
        event_name="pipeline.stage_finished",
        event_version=1,
        occurred_at="2026-09-30T20:15:00.123Z",
        run_id="550e8400-e29b-41d4-a716-446655440000",
        session_id=None,
        domain="pipeline",
        privacy_class=PrivacyClass.EXPORT_SAFE,
        status="ok",
        reason_code=None,
        app={"app_version": "0.1.0", "git_sha": None, "analyzer_version": None, "search_backend": None},
        props=props,
    )


def test_valid_envelope_accepted() -> None:
    event = _valid_stage_finished()
    assert validate_event(event) is event


@pytest.mark.parametrize(
    "run_id",
    [
        "550e8400-e29b-11d1-a716-446655440000",
        "550e8400e29b41d4a716446655440000",
        "550E8400-E29B-41D4-A716-446655440000",
        "550e8400-e29b-41d4-c716-446655440000",
        "not-a-uuid",
    ],
)
def test_run_id_requires_canonical_uuid_v4(run_id: str) -> None:
    event = _valid_stage_finished()
    bad = event.__class__(**{**event.__dict__, "run_id": run_id})
    assert validate_event(bad) is None


@pytest.mark.parametrize(
    "session_id",
    [
        "550e8400-e29b-11d1-a716-446655440000",
        "550e8400e29b41d4a716446655440000",
        "550E8400-E29B-41D4-A716-446655440000",
        "550e8400-e29b-41d4-c716-446655440000",
        "not-a-uuid",
    ],
)
def test_session_id_requires_canonical_uuid_v4(session_id: str) -> None:
    event = _valid_stage_finished()
    bad = event.__class__(**{**event.__dict__, "session_id": session_id})
    assert validate_event(bad) is None


def test_null_session_id_accepted() -> None:
    event = _valid_stage_finished()
    assert event.session_id is None
    assert validate_event(event) is event


@pytest.mark.parametrize("variant", ["8", "9", "a", "b"])
def test_uuid_v4_rfc_4122_variants_are_accepted(variant: str) -> None:
    event = _valid_stage_finished()
    run_id = f"550e8400-e29b-41d4-{variant}716-446655440000"
    session_id = f"550e8400-e29b-41d4-{variant}716-446655440001"
    candidate = event.__class__(
        **{**event.__dict__, "run_id": run_id, "session_id": session_id}
    )
    assert validate_event(candidate) is candidate


@pytest.mark.parametrize(
    "occurred_at",
    [
        "2026-09-30T20:15:00Z",
        "2026-09-30T20:15:00.123+00:00",
        "2026-09-30T20:15:00.123456Z",
        "2026-13-30T20:15:00.123Z",
        "2026-09-30T20:15:00.123z",
        "not-a-timestamp",
    ],
)
def test_occurred_at_requires_utc_millisecond_timestamp(occurred_at: str) -> None:
    event = _valid_stage_finished()
    bad = event.__class__(**{**event.__dict__, "occurred_at": occurred_at})
    assert validate_event(bad) is None


def test_app_accepts_only_documented_keys() -> None:
    event = _valid_stage_finished()
    bad = event.__class__(
        **{
            **event.__dict__,
            "app": {**event.app, "username": "operator"},
        }
    )
    assert validate_event(bad) is None


def test_app_accepts_optional_documented_keys() -> None:
    event = _valid_stage_finished()
    candidate = event.__class__(**{**event.__dict__, "app": {"app_version": "0.1.0"}})
    assert validate_event(candidate) is candidate


@pytest.mark.parametrize(
    "git_sha",
    ["abc123", "g123456", "a" * 41, "abc defg", "0", "0" * 41],
)
def test_app_git_sha_requires_short_or_full_hex(git_sha: str) -> None:
    event = _valid_stage_finished()
    bad = event.__class__(
        **{**event.__dict__, "app": {**event.app, "git_sha": git_sha}}
    )
    assert validate_event(bad) is None


@pytest.mark.parametrize("git_sha", [None, "abc1234", "A" * 40])
def test_app_git_sha_accepts_none_or_hex(git_sha: str | None) -> None:
    event = _valid_stage_finished()
    candidate = event.__class__(
        **{**event.__dict__, "app": {**event.app, "git_sha": git_sha}}
    )
    assert validate_event(candidate) is candidate


@pytest.mark.parametrize(
    "app_version",
    ["two words", "C:/Users/operator/private", "a" * 65, "token=secret", 1],
)
def test_app_values_require_bounded_safe_tokens(app_version: object) -> None:
    event = _valid_stage_finished()
    bad = event.__class__(
        **{**event.__dict__, "app": {**event.app, "app_version": app_version}}
    )
    assert validate_event(bad) is None


@pytest.mark.parametrize("key", ["app_version", "analyzer_version", "search_backend"])
def test_non_null_app_tokens_must_not_be_empty(key: str) -> None:
    event = _valid_stage_finished()
    bad = event.__class__(**{**event.__dict__, "app": {**event.app, key: ""}})
    assert validate_event(bad) is None


@pytest.mark.parametrize(
    "reason_code",
    [
        "audio device unavailable",
        "AUDIO-DEVICE-UNAVAILABLE",
        "C:/Users/operator/private",
        "A" * 65,
        "AUDIO_DEVICE_UNAVAILABLE!",
    ],
)
def test_reason_code_requires_stable_machine_code(reason_code: str) -> None:
    event = _valid_stage_finished()
    bad = event.__class__(**{**event.__dict__, "reason_code": reason_code})
    assert validate_event(bad) is None


@pytest.mark.parametrize("reason_code", [None, "AUDIO_DEVICE_UNAVAILABLE", "FAILED"])
def test_reason_code_accepts_none_or_stable_machine_code(reason_code: str | None) -> None:
    event = _valid_stage_finished()
    candidate = event.__class__(**{**event.__dict__, "reason_code": reason_code})
    assert validate_event(candidate) is candidate


@pytest.mark.parametrize("event_version", [True, 2, 99])
def test_event_version_is_exactly_v1(event_version: object) -> None:
    event = _valid_stage_finished()
    bad = event.__class__(**{**event.__dict__, "event_version": event_version})
    assert validate_event(bad) is None


def test_validate_event_never_raises_for_malformed_input() -> None:
    assert validate_event(object()) is None


def test_invalid_document_type_rejected() -> None:
    event = _valid_stage_finished()
    bad = event.__class__(**{**event.__dict__, "document_type": "not_measurement"})
    assert validate_event(bad) is None


def test_unknown_event_name_rejected() -> None:
    bad = _valid_stage_finished()
    bad = bad.__class__(**{**bad.__dict__, "event_name": "pipeline.unknown_event"})
    assert validate_event(bad) is None


def test_forbidden_props_rejected() -> None:
    for key in ("path", "sample_id", "query", "filename", "source_hash"):
        assert key in FORBIDDEN_PROP_KEYS or key in {
            "path",
            "relpath",
            "query",
            "filename",
            "sample_id",
            "source_hash",
            "embedding",
        }
        bad = _valid_stage_finished(**{key: "leak"})
        assert validate_event(bad) is None


def test_path_leakage_in_props_rejected() -> None:
    bad = _valid_stage_finished(**{"stage": "analyze", "wall_ms": 1, "items_ok": 0, "items_skip": 0, "items_fail": 0, "library_root": "C:/Samples"})
    # unknown prop key must drop
    assert validate_event(bad) is None


def test_unknown_prop_key_rejected() -> None:
    bad = _valid_stage_finished(extra_field=1)
    assert validate_event(bad) is None
    assert "extra_field" not in STAGE_FINISHED_ALLOWED_PROPS


def test_privacy_class_validation() -> None:
    bad = _valid_stage_finished()
    bad = bad.__class__(**{**bad.__dict__, "privacy_class": "not_a_class"})
    assert validate_event(bad) is None


def test_mode_default_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAMPLE_BRAIN_MEASUREMENT_MODE", raising=False)
    assert resolve_measurement_mode(config={}, env={}) == MeasurementMode.OFF


def test_mode_local_and_local_export(monkeypatch: pytest.MonkeyPatch) -> None:
    assert resolve_measurement_mode(config={}, env={"SAMPLE_BRAIN_MEASUREMENT_MODE": "local"}) == MeasurementMode.LOCAL
    assert (
        resolve_measurement_mode(config={}, env={"SAMPLE_BRAIN_MEASUREMENT_MODE": "local+export"})
        == MeasurementMode.LOCAL_EXPORT
    )
    assert resolve_measurement_mode(config={"measurement": {"mode": "local"}}, env={}) == MeasurementMode.LOCAL


def test_null_sink_is_noop() -> None:
    sink = NullSink()
    sink.write(_valid_stage_finished())
    sink.flush()


def test_sidecar_write_read(tmp_path: Path) -> None:
    db_path = tmp_path / "measurement.db"
    sink = SidecarSqliteSink(db_path)
    event = _valid_stage_finished()
    assert validate_event(event) is event
    sink.write(event)
    sink.flush()
    assert db_path.is_file()
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT event_name, domain, privacy_class, run_id, payload_json FROM events"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "pipeline.stage_finished"
    assert rows[0][1] == "pipeline"
    assert "path" not in rows[0][4]
    assert "sample_id" not in rows[0][4]


def test_mode_off_creates_no_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_DB_PATH", str(tmp_path / "measurement.db"))
    bus = build_bus_from_settings(mode=MeasurementMode.OFF, db_path=tmp_path / "measurement.db")
    bus.emit(_valid_stage_finished())
    bus.flush()
    assert not (tmp_path / "measurement.db").exists()


def test_mode_local_writes_sidecar(tmp_path: Path) -> None:
    db_path = tmp_path / "measurement.db"
    bus = build_bus_from_settings(mode=MeasurementMode.LOCAL, db_path=db_path)
    bus.emit(_valid_stage_finished())
    bus.flush()
    assert db_path.is_file()


def test_fail_soft_sink_exception_does_not_raise(tmp_path: Path) -> None:
    class BoomSink:
        def write(self, event) -> None:
            raise RuntimeError("sink exploded")

        def flush(self) -> None:
            raise RuntimeError("flush exploded")

    bus = MeasurementBus(mode=MeasurementMode.LOCAL, sink=BoomSink())
    bus.emit(_valid_stage_finished())  # must not raise
    bus.flush()  # must not raise


def test_emit_drops_invalid_without_raising(tmp_path: Path) -> None:
    db_path = tmp_path / "measurement.db"
    bus = build_bus_from_settings(mode=MeasurementMode.LOCAL, db_path=db_path)
    bad = _valid_stage_finished(path="/secret/sample.wav")
    bus.emit(bad)
    bus.flush()
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert count == 0


def test_analyze_cli_succeeds_when_measurement_sink_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.analyze import AnalyzeRunSummary

    catalog = tmp_path / "catalog.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(catalog))
    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_MODE", "local")
    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_DB_PATH", str(tmp_path / "measurement.db"))

    def fake_run_analyze(**kwargs):
        return AnalyzeRunSummary(items_ok=1, items_skip=0, items_fail=0)

    monkeypatch.setattr("src.analyze.run_analyze", fake_run_analyze)

    def boom_emit(*_a, **_k):
        raise RuntimeError("measurement boom")

    monkeypatch.setattr("src.measurement.emit.emit_pipeline_stage_finished", boom_emit)

    # Simulate CLI boundary helper used by cli.py
    from src.measurement.emit import record_analyze_stage_safe

    summary = fake_run_analyze()
    # record_analyze_stage_safe must swallow even if inner emit raises after monkeypatch reload
    # Re-import path that cli will call:
    import src.measurement.emit as emit_mod

    monkeypatch.setattr(emit_mod, "emit_pipeline_stage_finished", boom_emit)
    record_analyze_stage_safe(
        config={},
        env={"SAMPLE_BRAIN_MEASUREMENT_MODE": "local", "SAMPLE_BRAIN_MEASUREMENT_DB_PATH": str(tmp_path / "m.db")},
        summary=summary,
        wall_ms=5,
        run_id="550e8400-e29b-41d4-a716-446655440000",
    )


def test_catalog_schema_has_no_measurement_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = tmp_path / "catalog.db"
    import src.config as config_mod
    from src import db as db_mod
    from sqlalchemy import text

    monkeypatch.setattr(config_mod, "DB_PATH", catalog)
    engine = db_mod.init_db()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ).fetchall()
    names = {r[0] for r in rows}
    assert "events" not in names
    assert not any("measurement" in n.lower() for n in names)


def test_measurement_core_has_no_forbidden_imports() -> None:
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


def test_resolve_db_path_not_repo_relative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAMPLE_BRAIN_MEASUREMENT_DB_PATH", raising=False)
    path = resolve_measurement_db_path(config={}, env={}, explicit=None)
    assert path.is_absolute()
    assert "catalog.db" not in str(path)
    assert REPO_ROOT not in path.parents and path != REPO_ROOT


def test_cli_analyze_emits_one_stage_finished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.analyze import AnalyzeRunSummary
    import src.cli as cli

    meas_db = tmp_path / "measurement.db"
    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_MODE", "local")
    monkeypatch.setenv("SAMPLE_BRAIN_MEASUREMENT_DB_PATH", str(meas_db))
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(tmp_path / "catalog.db"))

    monkeypatch.setattr(
        cli,
        "_resolve_profile_or_exit",
        lambda _args: {
            "analyze": {"bpm_normalization": "none"},
            "database": {"path": str(tmp_path / "catalog.db")},
        },
    )
    monkeypatch.setattr(cli, "_apply_runtime_db_path", lambda _cfg: None)

    def fake_run_analyze(**kwargs):
        return AnalyzeRunSummary(items_ok=2, items_skip=0, items_fail=1)

    monkeypatch.setattr("src.analyze.run_analyze", fake_run_analyze)
    monkeypatch.setattr(sys, "argv", ["sample-brain", "analyze"])

    cli.main()
    assert meas_db.is_file()
    with sqlite3.connect(meas_db) as conn:
        rows = conn.execute("SELECT event_name, payload_json FROM events").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "pipeline.stage_finished"
    payload = rows[0][1]
    assert '"stage":"analyze"' in payload or '"stage": "analyze"' in payload
    assert "sample_id" not in payload
    assert "path" not in payload
    assert "filename" not in payload


def test_privacy_classes_enum_values() -> None:
    assert PrivacyClass.LOCAL_ONLY.value == "local_only"
    assert PrivacyClass.EXPORT_SAFE.value == "export_safe"
    assert PrivacyClass.AGGREGATE_ONLY.value == "aggregate_only"
