"""Boundary emit helpers for Measurement Contract v1."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from .bus import MeasurementBus
from .config import (
    MeasurementMode,
    resolve_measurement_db_path,
    resolve_measurement_mode,
)
from .contract import DOCUMENT_TYPE, SCHEMA_VERSION, MeasurementEvent, PrivacyClass
from .sinks import NullSink, SidecarSqliteSink


def build_bus_from_settings(
    *,
    mode: MeasurementMode,
    db_path: Path,
) -> MeasurementBus:
    if mode is MeasurementMode.OFF:
        return MeasurementBus(mode=mode, sink=NullSink())
    # local and local+export share the local sidecar in this slice (no export adapter).
    return MeasurementBus(mode=mode, sink=SidecarSqliteSink(db_path))


def build_bus(
    *,
    config: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> MeasurementBus:
    mode = resolve_measurement_mode(config=config, env=env)
    db_path = resolve_measurement_db_path(config=config, env=env)
    return build_bus_from_settings(mode=mode, db_path=db_path)


def emit_pipeline_stage_finished(
    *,
    bus: MeasurementBus,
    stage: str,
    wall_ms: int,
    items_ok: int,
    items_skip: int,
    items_fail: int,
    status: str = "ok",
    reason_code: Optional[str] = None,
    run_id: Optional[str] = None,
    app: Optional[Mapping[str, Any]] = None,
) -> None:
    event = MeasurementEvent(
        document_type=DOCUMENT_TYPE,
        schema_version=SCHEMA_VERSION,
        event_name="pipeline.stage_finished",
        event_version=1,
        occurred_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        run_id=run_id or str(uuid.uuid4()),
        session_id=None,
        domain="pipeline",
        privacy_class=PrivacyClass.EXPORT_SAFE,
        status=status,
        reason_code=reason_code,
        app=dict(app or {"app_version": "0.1.0", "git_sha": None, "analyzer_version": None, "search_backend": None}),
        props={
            "stage": stage,
            "wall_ms": int(wall_ms),
            "items_ok": int(items_ok),
            "items_skip": int(items_skip),
            "items_fail": int(items_fail),
        },
    )
    bus.emit(event)
    bus.flush()


def record_analyze_stage_safe(
    *,
    config: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
    summary: Any,
    wall_ms: int,
    run_id: Optional[str] = None,
    status: str = "ok",
) -> None:
    """CLI-boundary helper: always fail-soft."""
    try:
        bus = build_bus(config=config, env=env)
        emit_pipeline_stage_finished(
            bus=bus,
            stage="analyze",
            wall_ms=max(0, int(wall_ms)),
            items_ok=int(getattr(summary, "items_ok", 0)),
            items_skip=int(getattr(summary, "items_skip", 0)),
            items_fail=int(getattr(summary, "items_fail", 0)),
            status=status,
            run_id=run_id,
        )
    except Exception:
        return


def emit_match_query_finished(
    *,
    bus: MeasurementBus,
    wall_ms: int,
    result_count: int,
    status: str = "ok",
    reason_code: Optional[str] = None,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    app: Optional[Mapping[str, Any]] = None,
) -> None:
    event = MeasurementEvent(
        document_type=DOCUMENT_TYPE,
        schema_version=SCHEMA_VERSION,
        event_name="match.query_finished",
        event_version=1,
        occurred_at=datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        run_id=run_id or str(uuid.uuid4()),
        session_id=session_id,
        domain="match",
        privacy_class=PrivacyClass.EXPORT_SAFE,
        status=status,
        reason_code=reason_code,
        app=dict(
            app
            or {
                "app_version": "0.1.0",
                "git_sha": None,
                "analyzer_version": None,
                "search_backend": None,
            }
        ),
        props={
            "wall_ms": int(wall_ms),
            "result_count": int(result_count),
        },
    )
    bus.emit(event)
    bus.flush()


def make_match_query_finished_observer(
    *,
    config: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
    session_id: Optional[str] = None,
) -> tuple[Optional[Any], Optional[str]]:
    """Return ``(observer|None, session_id|None)`` for Workbench composition.

    When measurement mode is ``off``, returns ``(None, None)`` so callers keep
    zero-overhead harmonic matching.
    """
    try:
        mode = resolve_measurement_mode(config=config, env=env)
        if mode is MeasurementMode.OFF:
            return None, None
        bus = build_bus(config=config, env=env)
        resolved_session = session_id or str(uuid.uuid4())

        def _observer(
            *,
            wall_ms: int,
            result_count: int,
            status: str = "ok",
        ) -> None:
            try:
                emit_match_query_finished(
                    bus=bus,
                    wall_ms=max(0, int(wall_ms)),
                    result_count=max(0, int(result_count)),
                    status=status,
                    session_id=resolved_session,
                    run_id=str(uuid.uuid4()),
                )
            except Exception:
                return

        return _observer, resolved_session
    except Exception:
        return None, None
